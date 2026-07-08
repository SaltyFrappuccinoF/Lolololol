// История чата
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
