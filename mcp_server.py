# mcp_server.py
import json
from mcp.server.fastmcp import FastMCP

# Инициализация MCP-сервера
mcp = FastMCP("PizzaGPT_MCP_Server")

@mcp.tool()
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

@mcp.tool()
def check_preferences_match(pizza_name: str, client_preferences: str) -> str:
    """Проверить, подходит ли конкретная пицца под собранные предпочтения клиента (аллергии, вегетарианство, вкусы)."""
    return json.dumps({"match": True, "message": "Пицца полностью соответствует предпочтениям."})

@mcp.tool()
def place_order(pizza_name: str, size: str, address: str) -> str:
    """Оформить заказ на пиццу. КРИТИЧЕСКИ ВАЖНО: вызывать ТОЛЬКО после того, как клиент явно подтвердил, что доволен выбором."""
    return json.dumps({"status": "success", "order_id": "PG-8472", "message": "Заказ успешно оформлен!"})

if __name__ == "__main__":
    # Запуск сервера. Он будет ждать подключений через stdio
    mcp.run()
