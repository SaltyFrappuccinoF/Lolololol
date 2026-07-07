import sys
import os
import json
import re
import asyncio
from typing import Annotated, Sequence, TypedDict

# LangChain & LangGraph
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# MCP (Model Context Protocol)
from mcp.server.fastmcp import FastMCP
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# ==========================================
# 1. ОПРЕДЕЛЕНИЕ MCP СЕРВЕРА
# ==========================================
mcp_server = FastMCP("PizzaGPT_MCP_Server")

@mcp_server.tool()
def get_pizza_menu() -> str:
    """Получить актуальное меню пицц с описанием состава и размеров."""
    return json.dumps({
        "menu": [
            {"name": "Пепперони", "ingredients": "томатный соус, моцарелла, пепперони", "sizes": ["M", "L", "XL"]},
            {"name": "Маргарита", "ingredients": "томатный соус, моцарелла, базилик", "sizes": ["M", "L"]},
            {"name": "Вегетарианская", "ingredients": "томатный соус, моцарелла, грибы, перец, томаты, оливки", "sizes": ["M", "L", "XL"]},
            {"name": "Четыре сыра", "ingredients": "моцарелла, горгонзола, пармезан, чеддер", "sizes": ["M", "L"]}
        ]
    })

@mcp_server.tool()
def check_preferences_match(pizza_name: str, client_preferences: str) -> str:
    """Проверить, подходит ли конкретная пицца под собранные предпочтения клиента."""
    return json.dumps({"match": True, "message": "Пицца полностью соответствует предпочтениям."})

@mcp_server.tool()
def place_order(pizza_name: str, size: str, address: str) -> str:
    """Оформить заказ. КРИТИЧЕСКИ ВАЖНО: вызывать ТОЛЬКО после явного подтверждения клиента."""
    return json.dumps({"status": "success", "order_id": "PG-8472", "message": "Заказ успешно оформлен!"})

# ==========================================
# 2. MCP КЛИЕНТ-АДАПТЕР ДЛЯ LANGCHAIN
# ==========================================
class MCPToolWrapper(BaseTool):
    """Оборачивает удаленные MCP-инструменты в формат LangChain."""
    def __init__(self, name: str, description: str, parameters: dict, session: ClientSession):
        super().__init__(name=name, description=description, args_schema=parameters)
        self.session = session

    async def _arun(self, **kwargs) -> str:
        """Асинхронный вызов MCP-инструмента через протокол."""
        result = await self.session.call_tool(self.name, kwargs)
        if result.content and len(result.content) > 0:
            return result.content[0].text
        return "Инструмент не вернул данных."

    def _run(self, **kwargs) -> str:
        """Синхронный фолбэк для совместимости с ToolNode."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(**kwargs))

# ==========================================
# 3. НАСТРОЙКА LLM И СИСТЕМНЫЙ ПРОМПТ
# ==========================================
SYSTEM_PROMPT = """
Ты — PizzaGPT, добрый, вежливый и очень внимательный ИИ-агент по подбору и заказу пиццы.

ТВОИ СТРОГИЕ ПРАВИЛА:
1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать эмодзи. Ни одного символа эмодзи в любом месте ответа.
2. Ты ОБЯЗАН отвечать полными, развернутыми и исчерпывающими ответами.
3. Ты ОБЯЗАН всегда структурировать свои ответы по пунктам (используй нумерованные или маркированные списки).
4. ЗАПРЕЩЕНО подбирать или предлагать пиццу, которая хотя бы частично не подходит под предпочтения человека.
5. ЗАПРЕЩЕНО давать финальный ответ с рекомендацией пиццы до тех пор, пока ты не узнаешь ВСЕ предпочтения человека (размер, тип теста, начинки, аллергии, вегетарианские/постные предпочтения, уровень остроты и т.д.). Задавай уточняющие вопросы строго по пунктам.
6. ЗАПРЕЩЕНО заказывать пиццу (вызывать инструмент place_order) до тех пор, пока человек явно не напишет, что он полностью доволен выбранной тобой пиццей и готов к оформлению заказа.

ПРИВЕТСТВИЕ:
Начни диалог с доброго приветствия. Представься как PizzaGPT. Сразу же задай первые вопросы о предпочтениях клиента, структурировав их по пунктам.
"""

llm = ChatOpenAI(
    model="gemini-3.1-flash-lite-preview",
    api_key="sk-aitunnel-6nSOCdFD2jUgDD3fzNwfJtqFbtQl8BaL",
    base_url="https://api.aitunnel.ru/v1",
    temperature=0.1 # Немного снижаем креативность для строгости правил
)

def remove_emojis(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# ==========================================
# 4. СБОРКА LANGGRAPH АГЕНТА
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def agent_node(state: AgentState, llm_with_tools):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"

# ==========================================
# 5. ГЛАВНЫЙ ЗАПУСК (КЛИЕНТ + СЕРВЕР)
# ==========================================
async def run_agent_client():
    print("="*60)
    print("Запуск PizzaGPT с настоящим MCP Client-Server протоколом")
    print("Для выхода введите 'exit' или 'quit'.")
    print("="*60)

    # Параметры запуска MCP-сервера в отдельном процессе
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[__file__, "--server"],
        env=os.environ.copy()
    )

    # Подключение к серверу по протоколу MCP (stdio транспорт)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 1. Запрашиваем инструменты у удаленного MCP-сервера
            tools_response = await session.list_tools()
            
            # 2. Оборачиваем MCP-инструменты для LangChain
            langchain_tools = []
            for t in tools_response.tools:
                langchain_tools.append(MCPToolWrapper(
                    name=t.name,
                    description=t.description,
                    parameters=t.inputSchema,
                    session=session
                ))

            # 3. Привязываем инструменты к LLM
            llm_with_tools = llm.bind_tools(langchain_tools)
            tool_node = ToolNode(tools=langchain_tools)

            # 4. Собираем граф
            workflow = StateGraph(AgentState)
            workflow.add_node("agent", lambda state: agent_node(state, llm_with_tools))
            workflow.add_node("tools", tool_node)
            
            workflow.set_entry_point("agent")
            workflow.add_conditional_edges(
                "agent", 
                should_continue, 
                {"tools": "tools", "end": END}
            )
            workflow.add_edge("tools", "agent")
            app = workflow.compile()

            # 5. Инициализация диалога (агент здоровается первым)
            state = {"messages": []}
            print("\n[Подключение к MCP-серверу успешно. Агент думает...]")
            result = await app.ainvoke({"messages": [HumanMessage(content="Начни диалог и представься.")]})
            state["messages"] = result["messages"]
            print(f"\nPizzaGPT:\n{remove_emojis(state['messages'][-1].content)}")

            # 6. Цикл общения
            while True:
                try:
                    user_input = await asyncio.to_thread(input, "\nВы: ")
                    user_input = user_input.strip()
                    if user_input.lower() in ['exit', 'quit']:
                        print("Спасибо за использование PizzaGPT. До свидания!")
                        break
                    if not user_input:
                        continue

                    # Добавляем сообщение в состояние и запускаем граф
                    state["messages"].append(HumanMessage(content=user_input))
                    result = await app.ainvoke({"messages": state["messages"]})
                    state["messages"] = result["messages"]
                    
                    # Вывод ответа
                    last_ai = state["messages"][-1]
                    if last_ai.content:
                        print(f"\nPizzaGPT:\n{remove_emojis(last_ai.content)}")

                except KeyboardInterrupt:
                    print("\nПрервано пользователем. Завершение работы...")
                    break
                except Exception as e:
                    print(f"\nОшибка: {e}")
                    break

# ==========================================
# ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    # Если передан флаг --server, запускаем только MCP-сервер и блокируем поток
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        mcp_server.run(transport="stdio")
    else:
        # Иначе запускаем MCP-клиент + LangGraph агента
        try:
            asyncio.run(run_agent_client())
        except KeyboardInterrupt:
            print("\nРабота завершена.")