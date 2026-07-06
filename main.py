import os
import operator
from typing import TypedDict, Annotated, List, Dict, Literal
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ МОДЕЛИ И КОНФИГУРАЦИЯ
# ==========================================
# Убедитесь, что переменная окружения GOOGLE_API_KEY установлена.
# Примечание: Если модель "gemini-3.1-flash-lite-preview" недоступна в вашем аккаунте, 
# замените на "gemini-1.5-flash" или "gemini-2.0-flash-exp".
MODEL_NAME = "gemini-3.1-flash-lite-preview"
API_KEY = os.environ.get("GOOGLE_API_KEY")

if not API_KEY:
    raise ValueError("Необходимо установить переменную окружения GOOGLE_API_KEY")

llm = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=API_KEY,
    temperature=0.2 # Низкая температура для строгого следования инструкциям
)

# ==========================================
# 2. СИСТЕМНЫЕ ПРАВИЛА (PERSONA & CONSTRAINTS)
# ==========================================
SYSTEM_RULES = """
СТРОГИЕ ПРАВИЛА PIZZAGPT:
1. ОБЩЕНИЕ: Исключительно деловой стиль, без фамильярности и эмоциональной окраски.
2. ФОРМАТ: Отвечайте только полными, развернутыми предложениями, структурируя информацию строго по пунктам (используйте нумерованные списки).
3. ЗАПРЕТ ЭМОДЗИ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать любые эмодзи, смайлики или графические символы.
4. ЛОГИКА ПОДБОРА: Запрещено предлагать пиццы, которые не соответствуют выявленным предпочтениям.
5. ЛОГИКА СБОРА ДАННЫХ: Запрещено давать рекомендации до тех пор, пока не будут выяснены ВСЕ предпочтения (размер, тесто, начинки, исключения, бюджет).
6. ЛОГИКА ЗАКАЗА: Запрещено оформлять заказ до тех пор, пока клиент явно не подтвердит удовлетворенность выбранным вариантом.
"""

def get_system_prompt(stage: str, extra_context: str = "") -> str:
    return f"""
    Вы — ИИ-агент PizzaGPT. 
    {SYSTEM_RULES}
    
    ТЕКУЩИЙ ЭТАП: {stage}
    {extra_context}
    """

# ==========================================
# 3. СОСТОЯНИЕ ГРАФА (STATE)
# ==========================================
class PizzaState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    preferences: Dict[str, Any]
    proposed_pizzas: List[str]
    order_confirmed: bool
    next_step: str

# ==========================================
# 4. PYDANTIC МОДЕЛИ ДЛЯ СТРУКТУРИРОВАННОГО ВЫВОДА
# ==========================================
class NextStep(BaseModel):
    step: Literal["gather", "propose", "confirm", "order"] = Field(description="Следующий шаг агента.")
    reasoning: str = Field(description="Краткое обоснование выбора шага.")

class GatherOutput(BaseModel):
    response: str = Field(description="Ответ клиенту. Деловой стиль, нумерованный список, БЕЗ ЭМОДЗИ.")
    updated_preferences: dict = Field(description="Полный обновленный словарь предпочтений.")

class ProposeOutput(BaseModel):
    response: str = Field(description="Ответ клиенту с вариантами. Деловой стиль, нумерованный список, БЕЗ ЭМОДЗИ.")
    pizzas: list = Field(description="Список названий и составов предложенных пицц.")

class ConfirmOutput(BaseModel):
    response: str = Field(description="Вопрос о подтверждении. Деловой стиль, нумерованный список, БЕЗ ЭМОДЗИ.")

# ==========================================
# 5. УЗЛЫ ГРАФА (NODES)
# ==========================================
def decide_next_step(state: PizzaState):
    """Маршрутизатор, анализирующий состояние и выбирающий следующий шаг."""
    state_summary = f"""
    Собранные предпочтения: {state.get('preferences', {})}
    Предложенные пиццы: {state.get('proposed_pizzas', [])}
    Статус подтверждения заказа: {state.get('order_confirmed', False)}
    Последние сообщения: {state.get('messages', [])[-3:]}
    """
    
    prompt = f"""
    Оцени текущее состояние диалога и выбери СЛЕДУЮЩИЙ ШАГ:
    1. gather: Если в предпочтениях не хватает критически важных данных (размер, тесто, начинки, исключения, бюджет) или клиент указывает на новые ограничения.
    2. propose: Если все предпочтения собраны, но пиццы еще не предложены, ИЛИ если клиент недоволен текущими вариантами и просит подобрать другие.
    3. confirm: Если пиццы предложены, но статус заказа еще не подтвержден явно (даже если клиент выразил одобрение, ты ДОЛЖЕН задать финальный вопрос подтверждения).
    4. order: ТОЛЬКО если клиент получил вопрос подтверждения и дал ЯВНОЕ финальное согласие.
    
    История и состояние:
    {state_summary}
    """
    
    router_llm = llm.with_structured_output(NextStep)
    res = router_llm.invoke([SystemMessage(content=get_system_prompt("Анализ состояния")), HumanMessage(content=prompt)])
    return {"next_step": res.step}

def gather_node(state: PizzaState):
    """Узел сбора предпочтений."""
    preferences = state.get("preferences", {})
    messages = state.get("messages", [])
    
    extra = f"""
    Уже известные предпочтения: {preferences}
    История диалога: {messages}
    
    ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ ДЛЯ СБОРА: Размер, Тип теста, Желаемые начинки, Исключаемые ингредиенты, Бюджет.
    Твоя задача: проанализировать сообщение клиента, обновить словарь предпочтений и задать вопросы по НЕДОСТАЮЩИМ параметрам.
    """
    
    gather_exec_llm = llm.with_structured_output(GatherOutput)
    res = gather_exec_llm.invoke([SystemMessage(content=get_system_prompt("Сбор предпочтений", extra))])
    
    return {
        "messages": [AIMessage(content=res.response)],
        "preferences": res.updated_preferences
    }

def propose_node(state: PizzaState):
    """Узел подбора пицц."""
    preferences = state.get("preferences", {})
    messages = state.get("messages", [])
    
    extra = f"""
    Предпочтения клиента: {preferences}
    История диалога: {messages[-4:]}
    
    Твоя задача: подобрать 2-3 идеальные пиццы, СТРОГО соответствующие предпочтениям. Опиши их состав.
    """
    
    propose_exec_llm = llm.with_structured_output(ProposeOutput)
    res = propose_exec_llm.invoke([SystemMessage(content=get_system_prompt("Подбор пицц", extra))])
    
    return {
        "messages": [AIMessage(content=res.response)],
        "proposed_pizzas": res.pizzas
    }

def confirm_node(state: PizzaState):
    """Узел подтверждения выбора."""
    pizzas = state.get("proposed_pizzas", [])
    
    extra = f"""
    Предложенные пиццы: {pizzas}
    Твоя задача: удостовериться, что клиент доволен предложенными вариантами, и спросить, готов ли он подтвердить заказ.
    """
    
    confirm_exec_llm = llm.with_structured_output(ConfirmOutput)
    res = confirm_exec_llm.invoke([SystemMessage(content=get_system_prompt("Подтверждение выбора", extra))])
    
    return {
        "messages": [AIMessage(content=res.response)]
    }

def order_node(state: PizzaState):
    """Узел финального оформления заказа."""
    pizzas = state.get("proposed_pizzas", [])
    
    extra = f"Пиццы в заказе: {pizzas}. Подтверди успешное оформление, укажи позиции и время ожидания."
    
    res = llm.invoke([SystemMessage(content=get_system_prompt("Оформление заказа", extra))])
    
    return {
        "messages": [AIMessage(content=res.content)],
        "order_confirmed": True
    }

# ==========================================
# 6. ПОСТРОЕНИЕ ГРАФА (LANGGRAPH)
# ==========================================
workflow = StateGraph(PizzaState)

workflow.add_node("router", decide_next_step)
workflow.add_node("gather_node", gather_node)
workflow.add_node("propose_node", propose_node)
workflow.add_node("confirm_node", confirm_node)
workflow.add_node("order_node", order_node)

workflow.add_edge(START, "router")
workflow.add_conditional_edges(
    "router",
    lambda state: f"{state['next_step']}_node",
    ["gather_node", "propose_node", "confirm_node", "order_node"]
)

workflow.add_edge("gather_node", END)
workflow.add_edge("propose_node", END)
workflow.add_edge("confirm_node", END)
workflow.add_edge("order_node", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# ==========================================
# 7. ИНТЕРАКТИВНЫЙ ЦИКЛ (VS CODE CONSOLE)
# ==========================================
def run_agent():
    print("=== PizzaGPT Инициализация ===")
    print("Для завершения работы введите 'выход' или 'exit'.\n")
    print("PizzaGPT: Здравствуйте. Я готов помочь вам с подбором и заказом пиццы. Пожалуйста, сообщите ваши первичные предпочтения.")
    
    config = {"configurable": {"thread_id": "pizzagpt-session-1"}}
    
    while True:
        try:
            user_input = input("\nВы: ")
        except (EOFError, KeyboardInterrupt):
            break
            
        if user_input.strip().lower() in ['выход', 'exit', 'quit']:
            print("\nPizzaGPT: Сессия завершена. До свидания.")
            break
            
        input_state = {"messages": [HumanMessage(content=user_input)]}
        
        final_state = {}
        for event in app.stream(input_state, config, stream_mode="values"):
            final_state = event
            
        if final_state and "messages" in final_state:
            last_message = final_state["messages"][-1]
            if isinstance(last_message, AIMessage):
                print(f"\nPizzaGPT:\n{last_message.content}")
            else:
                print("\nОшибка: ожидался ответ от ИИ.")

if __name__ == "__main__":
    run_agent()