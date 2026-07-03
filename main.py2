import random
import time

class FriendlyBot:
    def __init__(self):
        self.greetings = ["Привет!", "Здравствуй!", "Хей! Рад тебя видеть!", "Добрый день!"]
        self.farewells = ["До свидания!", "Пока! Было приятно пообщаться!", "Увидимся!", "Всего хорошего!"]
        self.mood_responses = ["У меня всё отлично, спасибо что спрашиваешь! А у тебя как дела?", 
                              "Чувствую себя прекрасно! Готов помочь тебе!", 
                              "Замечательно! Рад нашему общению!"]
        self.help_responses = ["Конечно, я с радостью помогу!", "Спрашивай что угодно!", 
                              "Я здесь, чтобы помочь тебе!"]
        self.unknown_responses = ["Интересно! Расскажи подробнее?", "Ого! А что дальше?", 
                                 "Понимаю! Это здорово!", "Расскажи мне больше об этом!"]
        
    def get_response(self, user_input):
        user_input = user_input.lower()
        
        if any(word in user_input for word in ["привет", "здравствуй", "хай", "hello", "hi"]):
            return random.choice(self.greetings)
        elif any(word in user_input for word in ["пока", "до свидания", "bye", "прощай"]):
            return random.choice(self.farewells)
        elif any(word in user_input for word in ["как дела", "как ты", "настроение"]):
            return random.choice(self.mood_responses)
        elif any(word in user_input for word in ["помощь", "помоги", "help"]):
            return random.choice(self.help_responses)
        elif "?" in user_input:
            return "Хороший вопрос! Давай подумаем вместе над этим."
        else:
            return random.choice(self.unknown_responses)
    
    def chat(self):
        print("🤖 Привет! Я дружелюбный бот. Напиши 'выход' чтобы закончить общение.")
        print("-" * 50)
        
        while True:
            user_input = input("\nТы: ").strip()
            
            if user_input.lower() in ["выход", "exit", "quit", "пока"]:
                print("\n🤖 " + random.choice(self.farewells))
                break
            
            if user_input:
                time.sleep(0.5)  # Небольшая пауза для естественности
                print(f"\n🤖 Бот: {self.get_response(user_input)}")
            else:
                print("Пожалуйста, напиши что-нибудь!")

if __name__ == "__main__":
    bot = FriendlyBot()
    bot.chat()