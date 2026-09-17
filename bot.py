import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from config import BOT_TOKEN
from database import (
    get_or_create_user,
    get_question,
    get_random_question,
    get_user,
    init_db,
    set_subject,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    await message.answer("Секунду…", reply_markup=ReplyKeyboardRemove())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Математика", callback_data="subj_math")],
        [InlineKeyboardButton(text="📖 Русский язык", callback_data="subj_rus")],
    ])
    await message.answer(
        "Привет! Я помогу подготовиться к ЕГЭ/ОГЭ.\nВыбери предмет 👇",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("subj_"))
async def choose_subject(call: CallbackQuery):
    subject = call.data.replace("subj_", "")
    await set_subject(call.from_user.id, subject)
    name = "Математика" if subject == "math" else "Русский язык"
    await call.message.edit_text(
        f"Отлично! Твой предмет: {name}.\n\n"
        f"Нажми /train, чтобы получить вопрос."
    )
    await call.answer()


@dp.message(Command("train"))
async def cmd_train(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.subject:
        await message.answer("Сначала выбери предмет командой /start")
        return

    q = await get_random_question(user.subject)
    if not q:
        await message.answer("Пока нет вопросов по этому предмету.")
        return

    text = (
        f"❓ {q.text}\n\n"
        f"A) {q.option_a}\n"
        f"B) {q.option_b}\n"
        f"C) {q.option_c}\n"
        f"D) {q.option_d}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="A", callback_data=f"ans_{q.id}_A"),
            InlineKeyboardButton(text="B", callback_data=f"ans_{q.id}_B"),
        ],
        [
            InlineKeyboardButton(text="C", callback_data=f"ans_{q.id}_C"),
            InlineKeyboardButton(text="D", callback_data=f"ans_{q.id}_D"),
        ],
    ])
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("ans_"))
async def check_answer(call: CallbackQuery):
    parts = call.data.split("_")
    qid = int(parts[1])
    chosen = parts[2]

    q = await get_question(qid)
    if not q:
        await call.answer("Вопрос не найден", show_alert=True)
        return

    if q.correct.upper() == chosen.upper():
        head = "✅ Правильно!"
    else:
        head = f"❌ Неправильно. Верный ответ: {q.correct}"

    body = f"\n\n💡 Разбор: {q.explanation}" if q.explanation else ""
    await call.message.edit_text(f"{head}{body}")
    await call.answer()


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    
