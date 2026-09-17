import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardRemove,
)

from config import ADMIN_IDS, BOT_TOKEN
from database import (
    activate_subscription,
    check_and_increment_daily,
    count_questions,
    create_referral,
    get_or_create_user,
    get_question,
    get_random_question,
    get_user,
    init_db,
    reward_referrer_if_pending,
    seed_questions,
    set_subject,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DAILY_LIMIT = 20
PRICE_MONTH_STARS = 299
PRICE_YEAR_STARS = 2390
REFERRAL_REWARD_DAYS = 7

_bot_username = None


async def get_bot_username():
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username
    return _bot_username


def referral_link(user_id, bot_username):
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Парсим deep-link вида /start ref_12345
    parts = message.text.split(maxsplit=1)
    referrer_id = None
    if len(parts) > 1:
        payload = parts[1].strip()
        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload.replace("ref_", ""))
            except ValueError:
                referrer_id = None

    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    if referrer_id:
        created = await create_referral(message.from_user.id, referrer_id)
        if created:
            try:
                await bot.send_message(
                    referrer_id,
                    "🎁 По твоей ссылке пришёл новый друг! "
                    "Как только он решит первый вопрос — ты получишь +7 дней Premium.",
                )
            except Exception:
                pass

    await message.answer("Секунду…", reply_markup=ReplyKeyboardRemove())

    if user and user.subject:
        name = "Математика" if user.subject == "math" else "Русский язык"
        status = "💎 Premium" if user.role == "premium" else f"🆓 Free ({DAILY_LIMIT}/день)"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Тренировка", callback_data="do_train")],
            [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="show_ref")],
            [InlineKeyboardButton(text="🔄 Сменить предмет", callback_data="change_subj")],
            [InlineKeyboardButton(text="💎 Подписка", callback_data="show_subs")],
        ])
        await message.answer(
            f"С возвращением! Твой предмет: {name}.\nСтатус: {status}\n\n"
            f"Жми /train или кнопку ниже 👇",
            reply_markup=kb,
        )
        return

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
        f"Бесплатный лимит: {DAILY_LIMIT} вопросов в день.\n"
        f"Нажми /train, чтобы получить вопрос."
    )
    await call.answer()


@dp.callback_query(F.data == "do_train")
async def do_train(call: CallbackQuery):
    await call.answer()
    await cmd_train(call.message)


@dp.callback_query(F.data == "change_subj")
async def change_subj(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Математика", callback_data="subj_math")],
        [InlineKeyboardButton(text="📖 Русский язык", callback_data="subj_rus")],
    ])
    await call.message.edit_text("Выбери новый предмет:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "show_ref")
async def show_ref(call: CallbackQuery):
    username = await get_bot_username()
    link = referral_link(call.from_user.id, username)
    await call.message.answer(
        f"🎁 Твоя реферальная ссылка:\n\n{link}\n\n"
        f"За каждого друга, который решит хотя бы один вопрос, "
        f"ты получаешь +{REFERRAL_REWARD_DAYS} дней Premium."
    )
    await call.answer()


@dp.message(Command("ref"))
async def cmd_ref(message: Message):
    username = await get_bot_username()
    link = referral_link(message.from_user.id, username)
    await message.answer(
        f"🎁 Твоя реферальная ссылка:\n\n{link}\n\n"
        f"За каждого друга, который решит хотя бы один вопрос, "
        f"ты получаешь +{REFERRAL_REWARD_DAYS} дней Premium."
    )


@dp.message(Command("train"))
async def cmd_train(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.subject:
        await message.answer("Сначала выбери предмет командой /start")
        return

    allowed, count = await check_and_increment_daily(
        message.from_user.id, limit=DAILY_LIMIT
    )
    if not allowed:
        await show_subscription_offer(message, count)
        return

    # Награда пригласившему за первую активность приглашённого
    referrer = await reward_referrer_if_pending(message.from_user.id)
    if referrer:
        try:
            await bot.send_message(
                referrer.id,
                f"🎉 Твой друг решил первый вопрос! "
                f"Тебе начислено +{REFERRAL_REWARD_DAYS} дней Premium. "
                f"Подписка активна до {referrer.subscription_until.strftime('%d.%m.%Y')}.",
            )
        except Exception:
            pass
        await message.answer(
            f"🎁 Приятный бонус: твой друг пришёл по твоей ссылке — "
            f"он получил +{REFERRAL_REWARD_DAYS} дней Premium!"
        )

    q = await get_random_question(user.subject)
    if not q:
        await message.answer("Пока нет вопросов по этому предмету.")
        return

    text = (
        f"❓ {q.text}\n\n"
        f"A) {q.option_a}\n"
        f"B) {q.option_b}\n"
        f"C) {q.option_c}\n"
        f"D) {q.option_d}\n\n"
        f"<i>Вопрос {count}/{DAILY_LIMIT} на сегодня</i>"
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
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_subscription_offer(message: Message, count: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Месяц — {PRICE_MONTH_STARS}⭐", callback_data="buy_month")],
        [InlineKeyboardButton(
            text=f"Год — {PRICE_YEAR_STARS}⭐ (−40%)", callback_data="buy_year")],
    ])
    await message.answer(
        f"🔒 На сегодня лимит исчерпан: {count}/{DAILY_LIMIT}.\n\n"
        f"Оформи подписку — и занимайся без ограничений:",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "show_subs")
async def show_subs(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Месяц — {PRICE_MONTH_STARS}⭐", callback_data="buy_month")],
        [InlineKeyboardButton(
            text=f"Год — {PRICE_YEAR_STARS}⭐ (−40%)", callback_data="buy_year")],
    ])
    await call.message.answer(
        "Выбери подписку — оплата в Telegram Stars:",
        reply_markup=kb,
    )
    await call.answer()


@dp.callback_query(F.data == "buy_month")
async def buy_month(call: CallbackQuery):
    await send_sub_invoice(call, days=30, stars=PRICE_MONTH_STARS, title="Подписка на месяц")


@dp.callback_query(F.data == "buy_year")
async def buy_year(call: CallbackQuery):
    await send_sub_invoice(call, days=365, stars=PRICE_YEAR_STARS, title="Подписка на год")


async def send_sub_invoice(call: CallbackQuery, days: int, stars: int, title: str):
    prices = [LabeledPrice(label=title, amount=stars)]
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=title,
        description=f"Безлимитный доступ к тренировкам на {days} дней",
        payload=f"sub_{days}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    await call.answer()


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    try:
        days = int(payload.replace("sub_", ""))
    except ValueError:
        days = 30

    until = await activate_subscription(message.from_user.id, days)
    if until:
        await message.answer(
            f"✅ Оплата получена! Подписка активирована до "
            f"{until.strftime('%d.%m.%Y')}.\n\nЗанимайся без ограничений 🚀"
        )
    else:
        await message.answer("✅ Оплата получена, но пользователь не найден. Напиши в поддержку.")


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


@dp.message(Command("sub"))
async def cmd_sub(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Месяц — {PRICE_MONTH_STARS}⭐", callback_data="buy_month")],
        [InlineKeyboardButton(
            text=f"Год — {PRICE_YEAR_STARS}⭐ (−40%)", callback_data="buy_year")],
    ])
    await message.answer("Выбери подписку:", reply_markup=kb)


@dp.message(Command("reload"))
async def cmd_reload(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Команда доступна только администратору.")
        return
    await seed_questions(force=True)
    total = await count_questions()
    await message.answer(f"✅ Вопросы перезагружены. Всего в базе: {total}")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    total = await count_questions()
    await message.answer(f"📊 В базе вопросов: {total}")


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
