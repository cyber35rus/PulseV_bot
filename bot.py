import os
import telebot
from telebot import types

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_message(message):
    # Создаем кнопки
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("👋 Поздороваться")
    btn2 = types.KeyboardButton("❓ Задать вопрос")
    markup.add(btn1, btn2)
    
    bot.send_message(message.chat.id, 
                     f"Привет, {message.from_user.first_name}! Я твой новый бот. Выбери действие:", 
                     reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "👋 Поздороваться":
        bot.send_message(message.chat.id, "Привет! Рад тебя видеть 😊")
    elif message.text == "❓ Задать вопрос":
        bot.send_message(message.chat.id, "Напиши свой вопрос, и я отвечу (пока что эхом).")
    else:
        bot.send_message(message.chat.id, f"Ты написал: {message.text}")

bot.infinity_polling()
