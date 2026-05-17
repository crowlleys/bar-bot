from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
import requests
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

ALLOWED_USERS = [
    710946099,  # твій Telegram ID
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

KYIV_TZ = ZoneInfo("Europe/Kyiv")

menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🕘 Зміна")],
        [KeyboardButton(text="🍸 Меню")],
        [KeyboardButton(text="⚠️ Залишки")],
        [KeyboardButton(text="🧹 Прибирання")],
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
        [KeyboardButton(text="⚠️ Залишки")],
        [KeyboardButton(text="📋 Усі залишки")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)

STOCK_SETTINGS = {
    "Label 5": {"unit": "мл", "min": 500},
    "Ром Botafogo Малина": {"unit": "мл", "min": 500},
    "Тонік Рожевий": {"unit": "шт", "min": 6},
    "Кіш з мʼясом або лососем": {"unit": "шт", "min": 2},
    "Кіш без мʼяса": {"unit": "шт", "min": 2},
    "Coca-Cola 0,33": {"unit": "шт", "min": 5},
    "Coca-Cola zero 0,33": {"unit": "шт", "min": 5},
    "Пиво Mova IPA (світле)": {"unit": "шт", "min": 3},
    "Пиво Mova Amber Ale (світле, медове)": {"unit": "шт", "min": 3},
    "Пиво Mova Stout Oаtmeal (темне)": {"unit": "шт", "min": 3},
    "Пиво Mova Blanche (світле нефільтроване)": {"unit": "шт", "min": 3},
    "Пиво Mova світле б/а": {"unit": "шт", "min": 3},
    "Пиво Mova темне б/а": {"unit": "шт", "min": 3},
    "Пиво Mova темне б/а": {"unit": "шт", "min": 3},
    "Сидр Рогатий Заєц": {"unit": "шт", "min": 3},
    "Напій ELMN": {"unit": "шт", "min": 3},
    "Комбуча Spraga": {"unit": "шт", "min": 1},
}


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def load_stock():
    return load_json("stock.json", {})


def save_stock(data):
    save_json("stock.json", data)


def load_recipes():
    return load_json("recipes.json", {})


def load_processed_transactions():
    return load_json("processed_transactions.json", [])


def save_processed_transactions(data):
    save_json("processed_transactions.json", data)

def load_processed_supplies():
    try:
        with open("processed_supplies.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_processed_supplies(data):
    with open("processed_supplies.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_transactions_list(transactions_data):
    response = transactions_data.get("response", {})

    if isinstance(response, list):
        return [x for x in response if isinstance(x, dict) and x.get("transaction_id")]

    if isinstance(response, dict):
        if "data" in response and isinstance(response["data"], list):
            return [x for x in response["data"] if isinstance(x, dict) and x.get("transaction_id")]

        transactions = []
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
        "📦 Нотатки:\n"
        "— поки список порожній\n\n"
        "⚠️ Що закінчується:\n"
        "— дивись кнопку 📦 Залишки\n\n"
        f"{get_cleaning_text()}"
    )


async def send_morning_message():
    await bot.send_message(CHAT_ID, get_morning_message())


async def auto_write_off():
    recipes = load_recipes()
    stock = load_stock()
    processed = load_processed_transactions()

    today = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

    transactions_url = (
        f"https://joinposter.com/api/transactions.getTransactions"
        f"?token={POSTER_TOKEN}"
        f"&date_from={today}"
        f"&date_to={today}"
        f"&page=1"
        f"&per_page=100"
    )

    menu_url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"

    try:
        transactions_data = requests.get(transactions_url).json()
        menu_data = requests.get(menu_url).json()

        product_map, modification_map = build_product_maps(menu_data)
        transactions = get_transactions_list(transactions_data)

        changed = False

        for transaction in transactions:
            transaction_id = str(transaction.get("transaction_id"))

            if transaction_id in processed:
                continue

            for product in transaction.get("products", []):
                if not isinstance(product, dict):
                    continue

                quantity = float(product.get("num", 1))
                full_name = get_full_product_name(product, product_map, modification_map)

                recipe = recipes.get(full_name)

                if not recipe:
                    continue

                for ingredient, amount in recipe.items():
                    current = float(stock.get(ingredient, 0))
                    stock[ingredient] = max(0, current - float(amount) * quantity)
                    changed = True

            processed.append(transaction_id)

        if changed:
            save_stock(stock)

        save_processed_transactions(processed)

    except Exception as e:
        print("AUTO WRITE OFF ERROR:", e)

async def auto_supply():

    stock = load_stock()
    processed = load_processed_supplies()

    supplies_url = (
        f"https://joinposter.com/api/storage.getSupplies"
        f"?token={POSTER_TOKEN}"
    )

    try:
        supplies_data = requests.get(supplies_url).json()

        supplies = supplies_data.get("response", [])

        changed = False

        for supply in supplies:

            supply_id = str(supply.get("supply_id"))

            if supply_id in processed:
                continue

            detail_url = (
                f"https://joinposter.com/api/storage.getSupply"
                f"?token={POSTER_TOKEN}"
                f"&supply_id={supply_id}"
            )

            detail_data = requests.get(detail_url).json()
            detail = detail_data.get("response", {})

            for ingredient in detail.get("ingredients", []):

                name = ingredient.get("ingredient_name")
                amount = float(ingredient.get("supply_ingredient_num", 0))

                current = float(stock.get(name, 0))
                stock[name] = current + amount

                changed = True

            processed.append(supply_id)

        if changed:
            save_stock(stock)

        save_processed_supplies(processed)

    except Exception as e:
        print("AUTO SUPPLY ERROR:", e)


@dp.message(Command("start", "старт"))
async def start(message: types.Message):
    await message.answer("Бар бот працює 🍸", reply_markup=menu_keyboard)


@dp.message(Command("мій_id"))
async def my_id(message: types.Message):
    await message.answer(f"ID цього чату:\n{message.chat.id}")

@dp.message(lambda message: message.text == "🕘 Зміна")
async def shift_menu(message: types.Message):
    await message.answer(
        "Оберіть дію зі зміною:",
        reply_markup=shift_keyboard
    )


@dp.message(lambda message: message.text == "⬅️ Назад")
async def back_to_main_menu(message: types.Message):
    await message.answer(
        "Головне меню:",
        reply_markup=menu_keyboard
    )

@dp.message(lambda message: message.text == "🔓 Відкрити зміну")
async def open_shift_template(message: types.Message, state: FSMContext):
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
        await message.answer_photo(message.photo[-1].file_id, caption="📸 Фото до відкриття")

    await state.clear()


@dp.message(lambda message: message.text == "🔒 Закрити зміну")
async def close_shift_template(message: types.Message, state: FSMContext):
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
        await message.answer_photo(message.photo[-1].file_id, caption="🧾 Фото чека")

    await state.clear()

@dp.message(lambda message: message.text == "🔓 Відкрити зміну")
async def open_shift_template(message: types.Message, state: FSMContext):

    await state.clear()

    today = datetime.now(KYIV_TZ).strftime("%d/%m/%Y")

@dp.message(lambda message: message.text == "🔒 Закрити зміну")
async def close_shift_template(message: types.Message, state: FSMContext):

    await state.clear()

    today = datetime.now(KYIV_TZ).strftime("%d/%m/%Y")

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
        await message.answer(f"Помилка:\n{e}")

@dp.message(Command("id"))
async def my_id(message: types.Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")

@dp.message(lambda message: message.text == "📦 Залишки")
async def show_stock(message: types.Message):

    url = (
        f"https://joinposter.com/api/storage.getStorageLeftovers"
        f"?token={POSTER_TOKEN}"
    )

    try:
        data = requests.get(url).json()

        leftovers = data.get("response", [])

        if not leftovers:
            await message.answer("Склад порожній.")
            return

        low = []
        normal = []

        for item in leftovers:

            name = item.get("ingredient_name", "Без назви")

            amount = float(item.get("ingredient_left", 0))

            unit = item.get("ingredient_unit", "")

            limit_value = float(item.get("limit_value", 0))

            line = f"— {name}: {round(amount, 2)} {unit}"

            if limit_value > 0 and amount <= limit_value:
                low.append(line + f" / мін {limit_value}")
            else:
                normal.append(line)

        text = ""

        if low:
            text += "⚠️ Треба замовити:\n"
            text += "\n".join(low)
            text += "\n\n"

        if normal:
            text += "✅ Нормально:\n"
            text += "\n".join(normal)

        for i in range(0, len(text), 3500):
            await message.answer(text[i:i + 3500])

    except Exception as e:
        await message.answer(f"Помилка складу: {e}")

@dp.message(lambda message: message.text == "📦 Залишки")
async def stock_menu(message: types.Message):
    await message.answer(
        "Оберіть тип залишків:",
        reply_markup=stock_keyboard
    )

@dp.message(lambda message: message.text == "🧹 Прибирання")
@dp.message(Command("прибирання"))
async def cleaning(message: types.Message):
    await message.answer(get_cleaning_text())

@dp.message(lambda message: message.text == "🧾 Продажі")
@dp.message(Command("sales"))
async def sales(message: types.Message):

    if message.text.startswith("/sales"):

        parts = message.text.split()

        if len(parts) > 1:
            date_value = parts[1]
        else:
            date_value = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

    else:
        date_value = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

    transactions_url = (
        f"https://joinposter.com/api/transactions.getTransactions"
        f"?token={POSTER_TOKEN}"
        f"&date_from={date_value}"
        f"&date_to={date_value}"
        f"&page=1"
        f"&per_page=100"
    )

    menu_url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"

    transactions_data = requests.get(transactions_url).json()
    menu_data = requests.get(menu_url).json()

    product_map, modification_map = build_product_maps(menu_data)
    transactions = get_transactions_list(transactions_data)

    text = f"🧾 Продажі за {date_value}:\n\n"
    found = False

    for transaction in transactions:
        transaction_id = transaction.get("transaction_id")
        date_close = transaction.get("date_close", "")

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
        await message.answer(f"Продажів за {date_value} поки не знайдено.")
        return

    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

    scheduler.add_job(send_morning_message, "cron", day_of_week="mon-fri", hour=16, minute=0)
    scheduler.add_job(send_morning_message, "cron", day_of_week="sat-sun", hour=14, minute=0)
   # scheduler.add_job(auto_supply, "interval", minutes=1)
    scheduler.add_job(auto_write_off, "interval", minutes=1)

    scheduler.start()

    print("Бот запущений 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    asyncio.run(main())