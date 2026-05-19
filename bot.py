from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import asyncio
import requests
import threading
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


BOT_TOKEN = os.getenv("BOT_TOKEN")
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

ALLOWED_USERS = [
    710946099,
]

KYIV_TZ = ZoneInfo("Europe/Kyiv")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message):
            if event.from_user.id not in ALLOWED_USERS:
                await event.answer("⛔ У вас немає доступу до цього бота.")
                return
        return await handler(event, data)


dp.message.middleware(AccessMiddleware())


menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🕘 Зміна")],
        [KeyboardButton(text="🍸 Меню")],
        [KeyboardButton(text="⚠️ Залишки")],
        [KeyboardButton(text="📚 Архів змін")],
        [KeyboardButton(text="🧾 Продажі")],
    ],
    resize_keyboard=True
)

shift_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔓 Відкрити зміну")],
        [KeyboardButton(text="🔒 Закрити зміну")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)

stock_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚠️ Критичні залишки")],
        [KeyboardButton(text="📋 Усі залишки")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)


DAILY_CLEANING = [
    "Написати в чат про відкриття",
    "Провітрити та перевірити техніку",
    "Пилосос та помити підлогу",
    "Помити вбиральню",
    "Перевірити рушники та бумагу",
    "Протерти та розкласти двір",
    "Винести сміття",
    "Перевірити та підготувати кордіали",
    "Перевірити лимон, апельсин, огірок, соломку",
    "Помити стопери та перевірити рушники",
    "Заповнити вітрину",
    "Наповнити прикраси",
    "Перевірити поверхні та полички",
]

CLEANING_BY_DAY = {
    0: ["Промити антижиром раковини", "Помити сушарку", "Вимити барну поверхню та стопери"],
    1: ["Витерти поверхні у дворі", "Помити попільнички", "Підмести двір"],
    2: ["Протерти холодильники", "Протерти поверхні на складі", "Скласти список замовлення"],
    3: ["Вимити ванну", "Долити настоянки", "Зробити заготовку цукру"],
    4: ["Помити барні інструменти", "Підмести двір", "Поставити свічки у двір"],
    5: ["Підготувати бар до інтенсивного дня", "Купити необхідне в маркеті"],
    6: ["Зробити список замовлення", "Перевірити алкоголь", "Перевірити сиропи"],
}


class ReportMode(StatesGroup):
    waiting_open_report = State()
    waiting_close_report = State()


def get_cleaning_text():
    today = datetime.now(KYIV_TZ).weekday()

    text = "🧹 Памʼятка по прибиранню:\n\nЩодня:\n"

    for task in DAILY_CLEANING:
        text += f"— {task}\n"

    text += "\nСьогодні:\n"

    for task in CLEANING_BY_DAY.get(today, []):
        text += f"— {task}\n"

    return text


def get_morning_message():
    return (
        "Доброго ранку 🍸\n\n"
        "⚠️ Що закінчується:\n"
        "— дивись кнопку ⚠️ Залишки\n\n"
        f"{get_cleaning_text()}"
    )


async def send_morning_message():
    if CHAT_ID:
        await bot.send_message(CHAT_ID, get_morning_message())


def get_transactions_list(transactions_data):
    response = transactions_data.get("response", {})

    if isinstance(response, list):
        return [x for x in response if isinstance(x, dict) and x.get("transaction_id")]

    if isinstance(response, dict):
        transactions = []

        if "data" in response and isinstance(response["data"], list):
            return [x for x in response["data"] if isinstance(x, dict) and x.get("transaction_id")]

        for value in response.values():
            if isinstance(value, dict) and value.get("transaction_id"):
                transactions.append(value)
            elif isinstance(value, list):
                transactions.extend(
                    x for x in value
                    if isinstance(x, dict) and x.get("transaction_id")
                )

        return transactions

    return []


def build_product_maps(menu_data):
    product_map = {}
    modification_map = {}

    for item in menu_data.get("response", []):
        product_id = str(item.get("product_id"))
        product_name = item.get("product_name", "Без назви")

        product_map[product_id] = product_name

        for mod in item.get("modifications", []):
            mod_id = str(mod.get("modificator_id"))
            mod_name = mod.get("modificator_name", "")

            if mod_id and mod_name:
                if mod_name.lower().startswith("пиво mova"):
                    full_name = mod_name
                elif product_name.lower() in mod_name.lower():
                    full_name = mod_name
                else:
                    full_name = f"{product_name} {mod_name}"

                modification_map[f"{product_id}:{mod_id}"] = full_name

    return product_map, modification_map


def get_full_product_name(product, product_map, modification_map):
    product_id = str(product.get("product_id"))
    modification_id = str(product.get("modification_id", "0"))

    base_name = product_map.get(product_id, f"ID {product_id}")

    if modification_id and modification_id != "0":
        return modification_map.get(f"{product_id}:{modification_id}", base_name)

    return base_name


def get_leftovers_from_poster():
    url = (
        f"https://joinposter.com/api/storage.getStorageLeftovers"
        f"?token={POSTER_TOKEN}"
    )

    data = requests.get(url).json()
    return data.get("response", [])


@dp.message(Command("start", "старт"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Бар бот працює 🍸", reply_markup=menu_keyboard)


@dp.message(Command("id"))
async def user_id(message: types.Message):
    await message.answer(
        f"User ID: {message.from_user.id}\n"
        f"Chat ID: {message.chat.id}"
    )


@dp.message(lambda message: message.text == "⬅️ Назад")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Головне меню:", reply_markup=menu_keyboard)


@dp.message(lambda message: message.text == "🕘 Зміна")
async def shift_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Оберіть дію зі зміною:", reply_markup=shift_keyboard)


@dp.message(lambda message: message.text == "🔓 Відкрити зміну")
async def open_shift_template(message: types.Message, state: FSMContext):
    await state.clear()

    today = datetime.now(KYIV_TZ).strftime("%d/%m/%Y")

    template = (
        "Скопіюй, заповни і відправ одним повідомленням:\n\n"
        f"🔓 Відкриття зміни\n"
        f"Дата: {today}\n\n"
        f"Розмін:\n"
        f"Сейф:\n"
        f"Коментар:"
    )

    await message.answer(template)
    await state.set_state(ReportMode.waiting_open_report)


@dp.message(ReportMode.waiting_open_report)
async def save_open_report(message: types.Message, state: FSMContext):
    user = message.from_user.full_name
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")
    report_text = message.caption if message.caption else message.text

    await message.answer(
        f"✅ Відкриття зміни прийнято\n"
        f"Хто відкрив: {user}\n"
        f"Час: {time_now}\n\n"
        f"{report_text}"
    )

    if message.photo:
        await message.answer_photo(
            message.photo[-1].file_id,
            caption="📸 Фото до відкриття"
        )

    archive = load_shift_archive()

    archive.append({
        "type": "open",
        "user": user,
        "time": time_now,
        "date": datetime.now(KYIV_TZ).strftime("%m-%d-%Y"),
        "text": report_text
    })

    save_shift_archive(archive)

    await message.answer(get_cleaning_text())

    await state.clear()

@dp.message(lambda message: message.text == "🔒 Закрити зміну")
async def close_shift_template(message: types.Message, state: FSMContext):
    await state.clear()

    today = datetime.now(KYIV_TZ).strftime("%d/%m/%Y")

    template = (
        "Скопіюй, заповни і відправ одним повідомленням.\n"
        "Фото чека можна прикріпити до цього ж повідомлення.\n\n"
        f"🔒 Закриття зміни\n"
        f"Дата: {today}\n\n"
        f"Готівка:\n"
        f"Термінал:\n"
        f"Сейф / розмін:\n\n"
        f"ЗП:\n\n"
        f"Витрати:\n\n"
        f"Нотатки:\n\n"
        f"Замовити:"
    )

    await message.answer(template)
    await state.set_state(ReportMode.waiting_close_report)


@dp.message(ReportMode.waiting_close_report)
async def save_close_report(message: types.Message, state: FSMContext):
    user = message.from_user.full_name
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")
    report_text = message.caption if message.caption else message.text
    photo_status = "додано" if message.photo else "немає"

    await message.answer(
        f"✅ Закриття зміни прийнято\n"
        f"Хто закрив: {user}\n"
        f"Час: {time_now}\n"
        f"Фото чека: {photo_status}\n\n"
        f"{report_text}"
    )

    if message.photo:
        await message.answer_photo(
            message.photo[-1].file_id,
            caption="🧾 Фото чека"
        )

    archive = load_shift_archive()

    archive.append({
        "type": "close",
        "user": user,
        "time": time_now,
        "date": datetime.now(KYIV_TZ).strftime("%m-%d-%Y"),
        "text": report_text
    })

    save_shift_archive(archive)

    await state.clear()


@dp.message(lambda message: message.text == "🍸 Меню")
@dp.message(Command("меню"))
async def products(message: types.Message):
    url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"

    try:
        data = requests.get(url).json()

        if "response" not in data:
            await message.answer(f"❌ Помилка Poster:\n{data}")
            return

        grouped = {}

        for item in data["response"]:
            name = item.get("product_name", "Без назви")
            category = item.get("category_name") or "Без категорії"

            grouped.setdefault(category, []).append(name)

        text = "🍸 Меню Poster:\n"

        for category in sorted(grouped.keys()):
            text += f"\n📂 {category}:\n"

            for name in grouped[category]:
                text += f"— {name}\n"

        for i in range(0, len(text), 3500):
            await message.answer(text[i:i + 3500])

    except Exception as e:
        await message.answer(f"Помилка меню: {e}")


@dp.message(lambda message: message.text == "⚠️ Залишки")
async def stock_menu(message: types.Message):
    await message.answer("Оберіть тип залишків:", reply_markup=stock_keyboard)


def normalize_unit(unit):
    unit = str(unit).strip().lower()

    replacements = {
        "р": "шт.",
        "p": "шт.",
        "l": "л.",
        "kg": "кг",
    }

    return replacements.get(unit, unit)

def load_shift_archive():
    try:
        with open("shift_archive.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return []


def save_shift_archive(data):
    with open("shift_archive.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


@dp.message(lambda message: message.text == "⚠️ Критичні залишки")
async def critical_stock(message: types.Message):
    try:
        leftovers = get_leftovers_from_poster()

        critical = []

        for item in leftovers:
            name = item.get("ingredient_name", "Без назви")
            amount = round(float(item.get("ingredient_left", 0)), 2)
            unit = normalize_unit(item.get("ingredient_unit", ""))
            limit_value = round(float(item.get("limit_value", 0)), 2)

            if amount <= 0:
                critical.append(f"🚨 {name}: {amount:g} {unit}")
            elif limit_value > 0 and amount <= limit_value:
                critical.append(f"⚠️ {name}: {amount:g} {unit} / мін {limit_value:g} {unit}")

        if not critical:
            await message.answer("✅ Критичних залишків немає.")
            return

        text = "⚠️ Критичні залишки:\n\n" + "\n".join(critical)

        for i in range(0, len(text), 3500):
            await message.answer(text[i:i + 3500])

    except Exception as e:
        await message.answer(f"Помилка залишків: {e}")


@dp.message(lambda message: message.text == "📋 Усі залишки")
async def all_stock(message: types.Message):
    try:
        leftovers = get_leftovers_from_poster()

        items = []

        for item in leftovers:
            name = item.get("ingredient_name", "Без назви")
            amount = round(float(item.get("ingredient_left", 0)), 2)
            unit = normalize_unit(item.get("ingredient_unit", ""))

            if amount == 0:
                continue

            items.append(f"— {name}: {amount:g} {unit}")

        if not items:
            await message.answer("Склад порожній.")
            return

        text = "📋 Усі залишки:\n\n" + "\n".join(items)

        for i in range(0, len(text), 3500):
            await message.answer(text[i:i + 3500])

    except Exception as e:
        await message.answer(f"Помилка залишків: {e}")


@dp.message(lambda message: message.text == "🧾 Продажі")
@dp.message(Command("sales"))
async def sales(message: types.Message):

    if message.text.startswith("/sales"):
        parts = message.text.split()

        if len(parts) > 1:
            input_date = parts[1]

            try:
                parsed_date = datetime.strptime(input_date, "%m-%d-%Y")
                poster_date = parsed_date.strftime("%Y-%m-%d")
                display_date = input_date

            except:
                poster_date = input_date
                display_date = input_date

        else:
            poster_date = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")
            display_date = datetime.now(KYIV_TZ).strftime("%m-%d-%Y")

    else:
        poster_date = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")
        display_date = datetime.now(KYIV_TZ).strftime("%m-%d-%Y")

    transactions_url = (
        f"https://joinposter.com/api/transactions.getTransactions"
        f"?token={POSTER_TOKEN}"
        f"&date_from={poster_date}"
        f"&date_to={poster_date}"
        f"&page=1"
        f"&per_page=100"
    )

    menu_url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"

    try:
        transactions_data = requests.get(transactions_url).json()
        menu_data = requests.get(menu_url).json()

        product_map, modification_map = build_product_maps(menu_data)
        transactions = get_transactions_list(transactions_data)

        text = f"🧾 Продажі за {display_date}:\n\n"
        found = False

        for transaction in transactions:
            transaction_id = transaction.get("transaction_id")
            raw_date = transaction.get("date_close", "")

            try:
                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                date_close = parsed_date.strftime("%m-%d-%Y %H:%M")
            except:
                date_close = raw_date

            text += f"Чек #{transaction_id} — {date_close}\n"

            for product in transaction.get("products", []):
                if not isinstance(product, dict):
                    continue

                quantity = product.get("num", 1)
                full_name = get_full_product_name(product, product_map, modification_map)

                text += f"— {full_name} × {quantity}\n"

            text += "\n"
            found = True

        if not found:
            await message.answer(f"Продажів за {display_date} поки не знайдено.")
            return

        for i in range(0, len(text), 3500):
            await message.answer(text[i:i + 3500])

    except Exception as e:
        await message.answer(f"Помилка продажів: {e}")

@dp.message(lambda message: message.text == "📚 Архів змін")
async def shift_archive(message: types.Message):
    archive = load_shift_archive()

    if not archive:
        await message.answer("Архів змін поки порожній.")
        return

    last_items = archive[-10:]

    text = "📚 Останні зміни:\n\n"

    for item in reversed(last_items):
        shift_type = "🔓 Відкриття" if item["type"] == "open" else "🔒 Закриття"

        text += (
            f"{shift_type}\n"
            f"Дата: {item['date']}\n"
            f"Час: {item['time']}\n"
            f"Хто: {item['user']}\n"
            f"{item['text']}\n\n"
        )

    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

    scheduler.add_job(send_morning_message, "cron", day_of_week="mon-fri", hour=16, minute=0)
    scheduler.add_job(send_morning_message, "cron", day_of_week="sat-sun", hour=14, minute=0)

    scheduler.start()

    print("Бот запущений 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    asyncio.run(main())