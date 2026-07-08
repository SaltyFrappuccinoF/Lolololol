# app.py
import sys
import os
import json
import re
import asyncio
from typing import Annotated, Sequence, TypedDict
from flask import Flask, render_template, request, jsonify

# LangChain & LangGraph
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# MCP
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# ==========================================
# 1. МЕНЮ ПИЦЦ (ДЛЯ КАТЕГОРИЙ)
# ==========================================
PIZZA_MENU = {
    "meat": {
        "name": "Мясные пиццы",
        "icon": "🍖",
        "pizzas": [
            {
                "name": "Пепперони",
                "description": "Классическая пицца с пикантной колбасой пепперони и тягучей моцареллой на томатном соусе.",
                "price": "599 ₽",
                "sizes": ["M (25 см)", "L (30 см)", "XL (35 см)"],
                "image": "https://images.unsplash.com/photo-1628840042765-356cda0d8047?w=400"
            }
        ]
    },
    "veg": {
        "name": "Вегетарианские пиццы",
        "icon": "🥬",
        "pizzas": [
            {
                "name": "Вегетарианская",
                "description": "Сочетание свежих овощей: грибы, болгарский перец, томаты и оливки под слоем моцареллы.",
                "price": "549 ₽",
                "sizes": ["M (25 см)", "L (30 см)", "XL (35 см)"],
                "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=400"
            },
            {
                "name": "Маргарита",
                "description": "Традиционная итальянская пицца с томатным соусом, моцареллой и свежим базиликом.",
                "price": "449 ₽",
                "sizes": ["M (25 см)", "L (30 см)"],
                "image": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=400"
            }
        ]
    },
    "cheese": {
        "name": "Сырные пиццы",
        "icon": "🧀",
        "pizzas": [
            {
                "name": "Четыре сыра",
                "description": "Изысканное сочетание четырёх видов сыра: моцарелла, горгонзола, пармезан и чеддер.",
                "price": "649 ₽",
                "sizes": ["M (25 см)", "L (30 см)"],
                "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=400"
            }
        ]
    }
}

# ==========================================
# 2. MCP КЛИЕНТ-АДАПТЕР ДЛЯ LANGCHAIN
# ==========================================
class MCPToolWrapper(BaseTool):
    """Оборачивает удаленные MCP-инструменты в формат LangChain."""
    name: str
    description: str
    args_schema: dict
    session: ClientSession = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, name: str, description: str, parameters: dict, session: ClientSession):
        super().__init__(name=name, description=description, args_schema=parameters)
        self.session = session

    async def _arun(self, **kwargs) -> str:
        result = await self.session.call_tool(self.name, kwargs)
        if result.content and len(result.content) > 0:
            return result.content[0].text
        return "Инструмент не вернул данных."

    def _run(self, **kwargs) -> str:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._arun(**kwargs))
        finally:
            loop.close()

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
    temperature=0.1
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
# 4. LANGGRAPH АГЕНТ
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

class PizzaAgent:
    """Класс для управления агентом и его состоянием."""
    
    def __init__(self):
        self.session = None
        self.app = None
        self.mcp_read = None
        self.mcp_write = None
        self.mcp_cm = None
        self.session_cm = None
    
    async def initialize(self):
        """Инициализация MCP-клиента и сборка графа."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["mcp_server.py"],
            env=os.environ.copy()
        )
        
        self.mcp_cm = stdio_client(server_params)
        self.mcp_read, self.mcp_write = await self.mcp_cm.__aenter__()
        
        self.session_cm = ClientSession(self.mcp_read, self.mcp_write)
        self.session = await self.session_cm.__aenter__()
        await self.session.initialize()
        
        tools_response = await self.session.list_tools()
        
        langchain_tools = []
        for t in tools_response.tools:
            langchain_tools.append(MCPToolWrapper(
                name=t.name,
                description=t.description,
                parameters=t.inputSchema,
                session=self.session
            ))
        
        llm_with_tools = llm.bind_tools(langchain_tools)
        tool_node = ToolNode(tools=langchain_tools)
        
        def agent_node(state: AgentState):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        
        def should_continue(state: AgentState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return "end"
        
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
        workflow.add_edge("tools", "agent")
        
        self.app = workflow.compile()
    
    async def chat(self, user_message: str, history: list) -> tuple:
        """Отправить сообщение и получить ответ."""
        messages = [HumanMessage(content=user_message)] if not history else history + [HumanMessage(content=user_message)]
        
        result = await self.app.ainvoke({"messages": messages})
        new_history = result["messages"]
        
        last_ai = new_history[-1]
        response_text = remove_emojis(last_ai.content) if last_ai.content else ""
        
        return response_text, new_history
    
    async def get_greeting(self) -> tuple:
        """Получить приветствие от агента."""
        result = await self.app.ainvoke({"messages": [HumanMessage(content="Начни диалог и представься.")]})
        messages = result["messages"]
        last_ai = messages[-1]
        return remove_emojis(last_ai.content) if last_ai.content else "", messages
    
    async def close(self):
        """Закрытие соединений."""
        if self.session_cm:
            await self.session_cm.__aexit__(None, None, None)
        if self.mcp_cm:
            await self.mcp_cm.__aexit__(None, None, None)

# ==========================================
# 5. FLASK ПРИЛОЖЕНИЕ
# ==========================================
app = Flask(__name__)
app.secret_key = "pizzagpt_secret_key_2026"

pizza_agent = None

def get_agent():
    global pizza_agent
    if pizza_agent is None:
        pizza_agent = PizzaAgent()
        asyncio.run(pizza_agent.initialize())
    return pizza_agent

def run_async(coro):
    """Запуск асинхронной функции в синхронном Flask."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

@app.route("/")
def index():
    """Главная страница с категориями."""
    return render_template("index.html", categories=PIZZA_MENU)

@app.route("/category/<category_key>")
def category(category_key):
    """Страница категории пицц."""
    if category_key not in PIZZA_MENU:
        return jsonify({"error": "Категория не найдена"}), 404
    return render_template("index.html", categories=PIZZA_MENU, current_category=category_key)

@app.route("/api/menu")
def api_menu():
    """API для получения меню."""
    return jsonify(PIZZA_MENU)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """API для общения с ботом."""
    data = request.json
    user_message = data.get("message", "").strip()
    history_json = data.get("history", [])
    
    if not user_message:
        return jsonify({"error": "Пустое сообщение"}), 400
    
    try:
        agent = get_agent()
        
        history = []
        for msg in history_json:
            if msg["role"] == "user":
                history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                history.append(AIMessage(content=msg["content"]))
        
        response_text, new_history = run_async(agent.chat(user_message, history))
        
        new_history_json = []
        for msg in new_history:
            if isinstance(msg, HumanMessage):
                new_history_json.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.content:
                new_history_json.append({"role": "assistant", "content": msg.content})
        
        return jsonify({
            "response": response_text,
            "history": new_history_json
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/greeting")
def api_greeting():
    """API для получения приветствия."""
    try:
        agent = get_agent()
        greeting, history = run_async(agent.get_greeting())
        
        history_json = []
        for msg in history:
            if isinstance(msg, HumanMessage):
                history_json.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.content:
                history_json.append({"role": "assistant", "content": msg.content})
        
        return jsonify({
            "greeting": greeting,
            "history": history_json
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("Инициализация PizzaGPT агента...")
    get_agent()
    print("Агент готов к работе!")
    
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
