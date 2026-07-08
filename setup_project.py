#!/usr/bin/env python3
"""
Скрипт для автоматической установки проекта PizzaGPT
Создаёт все необходимые папки и файлы
"""

import os
import sys

def create_directory(path):
    """Создаёт директорию, если она не существует."""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"✓ Создана папка: {path}")
    else:
        print(f"✓ Папка уже существует: {path}")

def create_file(path, content):
    """Создаёт файл с указанным содержимым."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ Создан файл: {path}")

def setup_project():
    """Основная функция установки проекта."""
    print("="*60)
    print("Установка проекта PizzaGPT")
    print("="*60)
    print()
    
    # 1. Создание папок
    print("Создание структуры папок...")
    create_directory("templates")
    create_directory("static")
    print()
    
    # 2. Создание mcp_server.py
    print("Создание MCP-сервера...")
    mcp_server_content = """# mcp_server.py
import json
from mcp.server.fastmcp import FastMCP

# Инициализация MCP-сервера
mcp = FastMCP("PizzaGPT_MCP_Server")

@mcp.tool()
def get_pizza_menu() -> str:
    \"\"\"Получить актуальное меню пицц с описанием состава и размеров.\"\"\"
    return json.dumps({
        "menu": [
            {"name": "Пепперони", "ingredients": "томатный соус, моцарелла, пепперони", "sizes": ["M", "L", "XL"]},
            {"name": "Маргарита", "ingredients": "томатный соус, моцарелла, базилик", "sizes": ["M", "L"]},
            {"name": "Вегетарианская", "ingredients": "томатный соус, моцарелла, грибы, перец, томаты, оливки", "sizes": ["M", "L", "XL"]},
            {"name": "Четыре сыра", "ingredients": "моцарелла, горгонзола, пармезан, чеддер", "sizes": ["M", "L"]}
        ]
    })

@mcp.tool()
def check_preferences_match(pizza_name: str, client_preferences: str) -> str:
    \"\"\"Проверить, подходит ли конкретная пицца под собранные предпочтения клиента (аллергии, вегетарианство, вкусы).\"\"\"
    return json.dumps({"match": True, "message": "Пицца полностью соответствует предпочтениям."})

@mcp.tool()
def place_order(pizza_name: str, size: str, address: str) -> str:
    \"\"\"Оформить заказ на пиццу. КРИТИЧЕСКИ ВАЖНО: вызывать ТОЛЬКО после того, как клиент явно подтвердил, что доволен выбором.\"\"\"
    return json.dumps({"status": "success", "order_id": "PG-8472", "message": "Заказ успешно оформлен!"})

if __name__ == "__main__":
    # Запуск сервера. Он будет ждать подключений через stdio
    mcp.run()
"""
    create_file("mcp_server.py", mcp_server_content)
    print()
    
    # 3. Создание app.py
    print("Создание Flask-приложения...")
    app_content = """# app.py
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
    \"\"\"Оборачивает удаленные MCP-инструменты в формат LangChain.\"\"\"
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
SYSTEM_PROMPT = \"\"\"
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
\"\"\"

llm = ChatOpenAI(
    model="gemini-3.1-flash-lite-preview",
    api_key="sk-aitunnel-6nSOCdFD2jUgDD3fzNwfJtqFbtQl8BaL",
    base_url="https://api.aitunnel.ru/v1",
    temperature=0.1
)

def remove_emojis(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\\U0001F600-\\U0001F64F"
        "\\U0001F300-\\U0001F5FF"
        "\\U0001F680-\\U0001F6FF"
        "\\U0001F1E0-\\U0001F1FF"
        "\\U00002702-\\U000027B0"
        "\\U000024C2-\\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# ==========================================
# 4. LANGGRAPH АГЕНТ
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

class PizzaAgent:
    \"\"\"Класс для управления агентом и его состоянием.\"\"\"
    
    def __init__(self):
        self.session = None
        self.app = None
        self.mcp_read = None
        self.mcp_write = None
        self.mcp_cm = None
        self.session_cm = None
    
    async def initialize(self):
        \"\"\"Инициализация MCP-клиента и сборка графа.\"\"\"
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
        \"\"\"Отправить сообщение и получить ответ.\"\"\"
        messages = [HumanMessage(content=user_message)] if not history else history + [HumanMessage(content=user_message)]
        
        result = await self.app.ainvoke({"messages": messages})
        new_history = result["messages"]
        
        last_ai = new_history[-1]
        response_text = remove_emojis(last_ai.content) if last_ai.content else ""
        
        return response_text, new_history
    
    async def get_greeting(self) -> tuple:
        \"\"\"Получить приветствие от агента.\"\"\"
        result = await self.app.ainvoke({"messages": [HumanMessage(content="Начни диалог и представься.")]})
        messages = result["messages"]
        last_ai = messages[-1]
        return remove_emojis(last_ai.content) if last_ai.content else "", messages
    
    async def close(self):
        \"\"\"Закрытие соединений.\"\"\"
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
    \"\"\"Запуск асинхронной функции в синхронном Flask.\"\"\"
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
    \"\"\"Главная страница с категориями.\"\"\"
    return render_template("index.html", categories=PIZZA_MENU)

@app.route("/category/<category_key>")
def category(category_key):
    \"\"\"Страница категории пицц.\"\"\"
    if category_key not in PIZZA_MENU:
        return jsonify({"error": "Категория не найдена"}), 404
    return render_template("index.html", categories=PIZZA_MENU, current_category=category_key)

@app.route("/api/menu")
def api_menu():
    \"\"\"API для получения меню.\"\"\"
    return jsonify(PIZZA_MENU)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    \"\"\"API для общения с ботом.\"\"\"
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
    \"\"\"API для получения приветствия.\"\"\"
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
"""
    create_file("app.py", app_content)
    print()
    
    # 4. Создание templates/index.html
    print("Создание HTML-шаблона...")
    html_content = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PizzaGPT - Умный подбор пиццы</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <!-- Шапка сайта -->
    <header class="header">
        <div class="container">
            <div class="logo">
                <span class="logo-icon">P</span>
                <h1>PizzaGPT</h1>
            </div>
            <nav class="nav">
                <a href="/" class="nav-link">Главная</a>
                <a href="#chat" class="nav-link">Чат с ботом</a>
            </nav>
        </div>
    </header>

    <!-- Главный баннер -->
    <section class="hero">
        <div class="container">
            <h2>Добро пожаловать в мир идеальной пиццы</h2>
            <p>Наш ИИ-помощник подберёт для вас пиццу по вашим предпочтениям</p>
        </div>
    </section>

    <!-- Категории пицц -->
    <section class="categories">
        <div class="container">
            <h3 class="section-title">Выберите категорию</h3>
            <div class="category-grid">
                {% for key, category in categories.items() %}
                <a href="/category/{{ key }}" class="category-card {% if current_category == key %}active{% endif %}">
                    <div class="category-icon">{{ category.icon }}</div>
                    <h4>{{ category.name }}</h4>
                    <p>{{ category.pizzas|length }} {{ 'пицца' if category.pizzas|length == 1 else 'пиццы' if category.pizzas|length < 5 else 'пицц' }}</p>
                </a>
                {% endfor %}
            </div>
        </div>
    </section>

    <!-- Список пицц в категории -->
    {% if current_category %}
    <section class="pizza-list">
        <div class="container">
            <h3 class="section-title">{{ categories[current_category].name }}</h3>
            <div class="pizza-grid">
                {% for pizza in categories[current_category].pizzas %}
                <div class="pizza-card">
                    <div class="pizza-image" style="background-image: url('{{ pizza.image }}');"></div>
                    <div class="pizza-info">
                        <h4>{{ pizza.name }}</h4>
                        <p class="pizza-description">{{ pizza.description }}</p>
                        <div class="pizza-sizes">
                            {% for size in pizza.sizes %}
                            <span class="size-badge">{{ size }}</span>
                            {% endfor %}
                        </div>
                        <div class="pizza-footer">
                            <span class="pizza-price">{{ pizza.price }}</span>
                            <button class="btn-order" onclick="askBotAboutPizza('{{ pizza.name }}')">Спросить у бота</button>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}

    <!-- Чат с ботом -->
    <section class="chat-section" id="chat">
        <div class="container">
            <h3 class="section-title">Чат с PizzaGPT</h3>
            <div class="chat-container">
                <div class="chat-messages" id="chatMessages">
                    <div class="message bot-message loading">
                        <div class="message-avatar">P</div>
                        <div class="message-content">
                            <div class="typing-indicator">
                                <span></span><span></span><span></span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="chat-input-container">
                    <input type="text" id="chatInput" class="chat-input" placeholder="Напишите сообщение боту..." onkeypress="handleKeyPress(event)">
                    <button class="send-button" onclick="sendMessage()">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    </section>

    <!-- Подвал -->
    <footer class="footer">
        <div class="container">
            <p>&copy; 2026 PizzaGPT. Все права защищены.</p>
        </div>
    </footer>

    <script src="{{ url_for('static', filename='script.js') }}"></script>
</body>
</html>
"""
    create_file("templates/index.html", html_content)
    print()
    
    # 5. Создание static/style.css
    print("Создание CSS-стилей...")
    css_content = """/* ==========================================
   ОБЩИЕ СТИЛИ
   ========================================== */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --primary-red: #D32F2F;
    --dark-red: #B71C1C;
    --primary-yellow: #FFC107;
    --light-yellow: #FFECB3;
    --cream: #FFF8E1;
    --dark: #2C1810;
    --gray: #757575;
    --light-gray: #F5F5F5;
    --white: #FFFFFF;
    --shadow: 0 4px 20px rgba(211, 47, 47, 0.15);
    --shadow-hover: 0 8px 30px rgba(211, 47, 47, 0.25);
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, var(--cream) 0%, var(--light-yellow) 100%);
    color: var(--dark);
    line-height: 1.6;
    min-height: 100vh;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

/* ==========================================
   ШАПКА
   ========================================== */
.header {
    background: linear-gradient(135deg, var(--primary-red) 0%, var(--dark-red) 100%);
    color: var(--white);
    padding: 20px 0;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    position: sticky;
    top: 0;
    z-index: 100;
}

.header .container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo {
    display: flex;
    align-items: center;
    gap: 15px;
}

.logo-icon {
    width: 50px;
    height: 50px;
    background: var(--primary-yellow);
    color: var(--dark-red);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    font-weight: bold;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
}

.logo h1 {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 1px;
}

.nav {
    display: flex;
    gap: 30px;
}

.nav-link {
    color: var(--white);
    text-decoration: none;
    font-weight: 500;
    font-size: 16px;
    transition: var(--transition);
    position: relative;
    padding: 5px 0;
}

.nav-link::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 0;
    height: 2px;
    background: var(--primary-yellow);
    transition: var(--transition);
}

.nav-link:hover::after {
    width: 100%;
}

/* ==========================================
   БАННЕР
   ========================================== */
.hero {
    background: linear-gradient(135deg, rgba(211, 47, 47, 0.9), rgba(183, 28, 28, 0.9)),
                url('https://images.unsplash.com/photo-1513104890138-7c749659a591?w=1200') center/cover;
    color: var(--white);
    padding: 80px 0;
    text-align: center;
}

.hero h2 {
    font-size: 42px;
    margin-bottom: 15px;
    font-weight: 700;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
}

.hero p {
    font-size: 20px;
    opacity: 0.95;
}

/* ==========================================
   СЕКЦИИ
   ========================================== */
section {
    padding: 60px 0;
}

.section-title {
    font-size: 32px;
    color: var(--dark-red);
    text-align: center;
    margin-bottom: 40px;
    font-weight: 700;
    position: relative;
    padding-bottom: 15px;
}

.section-title::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 80px;
    height: 4px;
    background: linear-gradient(90deg, var(--primary-yellow), var(--primary-red));
    border-radius: 2px;
}

/* ==========================================
   КАРТОЧКИ КАТЕГОРИЙ
   ========================================== */
.category-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 30px;
    max-width: 1000px;
    margin: 0 auto;
}

.category-card {
    background: var(--white);
    border-radius: 20px;
    padding: 40px 30px;
    text-align: center;
    text-decoration: none;
    color: var(--dark);
    box-shadow: var(--shadow);
    transition: var(--transition);
    border: 3px solid transparent;
    cursor: pointer;
}

.category-card:hover {
    transform: translateY(-10px);
    box-shadow: var(--shadow-hover);
    border-color: var(--primary-yellow);
}

.category-card.active {
    border-color: var(--primary-red);
    background: linear-gradient(135deg, var(--white) 0%, var(--light-yellow) 100%);
}

.category-icon {
    font-size: 64px;
    margin-bottom: 20px;
    display: block;
}

.category-card h4 {
    font-size: 24px;
    color: var(--dark-red);
    margin-bottom: 10px;
    font-weight: 700;
}

.category-card p {
    color: var(--gray);
    font-size: 16px;
}

/* ==========================================
   КАРТОЧКИ ПИЦЦ
   ========================================== */
.pizza-list {
    background: var(--white);
}

.pizza-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 30px;
}

.pizza-card {
    background: var(--white);
    border-radius: 20px;
    overflow: hidden;
    box-shadow: var(--shadow);
    transition: var(--transition);
    border: 2px solid var(--light-yellow);
}

.pizza-card:hover {
    transform: translateY(-5px);
    box-shadow: var(--shadow-hover);
    border-color: var(--primary-red);
}

.pizza-image {
    height: 200px;
    background-size: cover;
    background-position: center;
    background-color: var(--light-yellow);
}

.pizza-info {
    padding: 25px;
}

.pizza-info h4 {
    font-size: 22px;
    color: var(--dark-red);
    margin-bottom: 10px;
    font-weight: 700;
}

.pizza-description {
    color: var(--gray);
    font-size: 14px;
    margin-bottom: 15px;
    line-height: 1.5;
}

.pizza-sizes {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 20px;
}

.size-badge {
    background: var(--light-yellow);
    color: var(--dark-red);
    padding: 5px 12px;
    border-radius: 15px;
    font-size: 12px;
    font-weight: 600;
}

.pizza-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 15px;
    border-top: 1px solid var(--light-gray);
}

.pizza-price {
    font-size: 24px;
    font-weight: 700;
    color: var(--primary-red);
}

.btn-order {
    background: linear-gradient(135deg, var(--primary-red) 0%, var(--dark-red) 100%);
    color: var(--white);
    border: none;
    padding: 10px 20px;
    border-radius: 25px;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    font-size: 14px;
}

.btn-order:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 15px rgba(211, 47, 47, 0.4);
}

/* ==========================================
   ЧАТ
   ========================================== */
.chat-section {
    background: linear-gradient(135deg, var(--cream) 0%, var(--light-yellow) 100%);
}

.chat-container {
    max-width: 800px;
    margin: 0 auto;
    background: var(--white);
    border-radius: 25px;
    box-shadow: var(--shadow);
    overflow: hidden;
    border: 2px solid var(--primary-yellow);
}

.chat-messages {
    height: 500px;
    overflow-y: auto;
    padding: 30px;
    background: linear-gradient(180deg, var(--white) 0%, var(--cream) 100%);
}

.chat-messages::-webkit-scrollbar {
    width: 8px;
}

.chat-messages::-webkit-scrollbar-track {
    background: var(--light-gray);
}

.chat-messages::-webkit-scrollbar-thumb {
    background: var(--primary-red);
    border-radius: 4px;
}

.message {
    display: flex;
    gap: 15px;
    margin-bottom: 20px;
    animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.user-message {
    flex-direction: row-reverse;
}

.message-avatar {
    width: 45px;
    height: 45px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 20px;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.bot-message .message-avatar {
    background: linear-gradient(135deg, var(--primary-red) 0%, var(--dark-red) 100%);
    color: var(--white);
}

.user-message .message-avatar {
    background: linear-gradient(135deg, var(--primary-yellow) 0%, #FFA000 100%);
    color: var(--dark);
}

.message-content {
    max-width: 70%;
    padding: 15px 20px;
    border-radius: 18px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-wrap: break-word;
}

.bot-message .message-content {
    background: var(--light-gray);
    color: var(--dark);
    border-top-left-radius: 4px;
}

.user-message .message-content {
    background: linear-gradient(135deg, var(--primary-red) 0%, var(--dark-red) 100%);
    color: var(--white);
    border-top-right-radius: 4px;
}

/* Индикатор печати */
.typing-indicator {
    display: flex;
    gap: 5px;
    padding: 5px 0;
}

.typing-indicator span {
    width: 8px;
    height: 8px;
    background: var(--primary-red);
    border-radius: 50%;
    animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
    animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
    animation-delay: 0.4s;
}

@keyframes typing {
    0%, 60%, 100% {
        transform: translateY(0);
        opacity: 0.4;
    }
    30% {
        transform: translateY(-10px);
        opacity: 1;
    }
}

/* Поле ввода */
.chat-input-container {
    display: flex;
    padding: 20px;
    background: var(--white);
    border-top: 2px solid var(--light-yellow);
    gap: 10px;
}

.chat-input {
    flex: 1;
    padding: 15px 20px;
    border: 2px solid var(--light-yellow);
    border-radius: 25px;
    font-size: 16px;
    outline: none;
    transition: var(--transition);
    font-family: inherit;
}

.chat-input:focus {
    border-color: var(--primary-red);
    box-shadow: 0 0 0 3px rgba(211, 47, 47, 0.1);
}

.send-button {
    width: 55px;
    height: 55px;
    background: linear-gradient(135deg, var(--primary-red) 0%, var(--dark-red) 100%);
    color: var(--white);
    border: none;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: var(--transition);
    flex-shrink: 0;
}

.send-button:hover {
    transform: scale(1.1) rotate(15deg);
    box-shadow: 0 4px 15px rgba(211, 47, 47, 0.4);
}

.send-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* ==========================================
   ПОДВАЛ
   ========================================== */
.footer {
    background: var(--dark);
    color: var(--white);
    text-align: center;
    padding: 30px 0;
    margin-top: 40px;
}

/* ==========================================
   АДАПТИВНОСТЬ
   ========================================== */
@media (max-width: 768px) {
    .header .container {
        flex-direction: column;
        gap: 15px;
    }
    
    .hero h2 {
        font-size: 28px;
    }
    
    .hero p {
        font-size: 16px;
    }
    
    .section-title {
        font-size: 24px;
    }
    
    .chat-messages {
        height: 400px;
    }
    
    .message-content {
        max-width: 85%;
    }
}
"""
    create_file("static/style.css", css_content)
    print()
    
    # 6. Создание static/script.js
    print("Создание JavaScript...")
    js_content = """// История чата
let chatHistory = [];

// Загрузка приветствия при загрузке страницы
window.addEventListener('DOMContentLoaded', async () => {
    await loadGreeting();
});

// Загрузка приветствия от бота
async function loadGreeting() {
    try {
        const response = await fetch('/api/greeting');
        const data = await response.json();
        
        if (data.greeting) {
            chatHistory = data.history || [];
            addMessage(data.greeting, 'bot');
        }
    } catch (error) {
        console.error('Ошибка загрузки приветствия:', error);
        addMessage('Здравствуйте! Я PizzaGPT. Чем могу помочь?', 'bot');
    }
}

// Отправка сообщения
async function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Добавляем сообщение пользователя
    addMessage(message, 'user');
    input.value = '';
    
    // Показываем индикатор печати
    showTypingIndicator();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                history: chatHistory
            })
        });
        
        const data = await response.json();
        
        // Убираем индикатор печати
        hideTypingIndicator();
        
        if (data.response) {
            chatHistory = data.history || [];
            addMessage(data.response, 'bot');
        } else if (data.error) {
            addMessage('Извините, произошла ошибка. Попробуйте ещё раз.', 'bot');
        }
    } catch (error) {
        hideTypingIndicator();
        console.error('Ошибка отправки:', error);
        addMessage('Извините, не удалось связаться с сервером.', 'bot');
    }
}

// Обработка нажатия Enter
function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

// Добавление сообщения в чат
function addMessage(text, sender) {
    const messagesContainer = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'bot' ? 'P' : 'Я';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text;
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    messagesContainer.appendChild(messageDiv);
    
    // Прокрутка вниз
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Показ индикатора печати
function showTypingIndicator() {
    const messagesContainer = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot-message loading';
    typingDiv.id = 'typingIndicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = 'P';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(content);
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Скрытие индикатора печати
function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Функция для кнопки "Спросить у бота"
function askBotAboutPizza(pizzaName) {
    const input = document.getElementById('chatInput');
    input.value = `Расскажи подробнее о пицце "${pizzaName}" и помоги мне её заказать.`;
    
    // Прокрутка к чату
    document.getElementById('chat').scrollIntoView({ behavior: 'smooth' });
    
    // Фокус на поле ввода
    setTimeout(() => {
        input.focus();
    }, 500);
}
"""
    create_file("static/script.js", js_content)
    print()
    
    # 7. Создание requirements.txt
    print("Создание requirements.txt...")
    requirements_content = """flask
langgraph
langchain
langchain-openai
mcp
pydantic
openai
"""
    create_file("requirements.txt", requirements_content)
    print()
    
    # Завершение
    print("="*60)
    print("✓ Проект PizzaGPT успешно установлен!")
    print("="*60)
    print()
    print("Структура проекта:")
    print("  ├── app.py                 (Flask-сервер + агент)")
    print("  ├── mcp_server.py          (MCP-сервер)")
    print("  ├── requirements.txt       (Зависимости)")
    print("  ├── templates/")
    print("  │   └── index.html         (HTML-шаблон)")
    print("  └── static/")
    print("      ├── style.css          (Стили)")
    print("      └── script.js          (JavaScript)")
    print()
    print("Для запуска проекта:")
    print("  1. Установите зависимости:")
    print("     pip install -r requirements.txt")
    print()
    print("  2. Запустите приложение:")
    print("     python app.py")
    print()
    print("  3. Откройте браузер:")
    print("     http://localhost:5000")
    print()

if __name__ == "__main__":
    setup_project()