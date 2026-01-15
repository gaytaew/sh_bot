import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
import random
import string
import json as _json
from urllib.parse import urlencode, quote, unquote

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import (
    TELEGRAM_TOKEN,
    GOOGLE_SHEETS_KEY,
    GSERVICE_JSON,
    SHOKZ_ACCOUNTS_SHEET,
    CARRIERS_SHEET,
    TYPES_SHEET,
    MEDIATORS_SHEET,
    PRODUCTS_SHEET,
    COL_DATE,
    COL_ORDER_NO,
    COL_NAME,
    COL_EMAIL,
    COL_ADDRESS,
    COL_PHONE,
    COL_PRODUCT,
    COL_SERIAL,
    COL_STATUS,
    COL_ISSUE,
)
from ebay_utils import ocr_space_file, gpt_structured_fields, parse_zip_and_city, fake_phone
from issues import ISSUE_TEMPLATES
from receipts_config import RECEIPT_LAYOUTS
from receipt_product_map import PRODUCT_ID_MAP


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# --- Дополнительный индекс для колонки квитанции ---
COL_RECEIPT_LINK = COL_ISSUE + 1 # Предполагается, что это колонка сразу после COL_ISSUE (11)


# --- Google Sheets init ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

try:
    creds_dict = _json.loads(GSERVICE_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client_gsheets = gspread.authorize(creds)

    spreadsheet = client_gsheets.open_by_key(GOOGLE_SHEETS_KEY)
    sheet_accounts = spreadsheet.worksheet(SHOKZ_ACCOUNTS_SHEET)
    sheet_carriers = spreadsheet.worksheet(CARRIERS_SHEET)
    sheet_types = spreadsheet.worksheet(TYPES_SHEET)
    sheet_mediators = spreadsheet.worksheet(MEDIATORS_SHEET)
    sheet_products = spreadsheet.worksheet(PRODUCTS_SHEET)
    sheet_emails = spreadsheet.worksheet("Emails")

except Exception as e:
    logger.error(f"Ошибка при инициализации Google Sheets: {e}")
    raise

# --- helper state ---
waiting_for_ebay_users = set()
waiting_for_status_update = set()

# --- СЛОВАРИ СИНОНИМОВ ДЛЯ АДРЕСА ---
STREET_SYNONYMS = {
    "RD": ["Road", "Roud", "Rd."],
    "ST": ["Street", "Strt", "St."],
    "CT": ["Court", "Ct."],
    "AVE": ["Avenue", "Ave."],
    "LN": ["Lane", "Lnae"],
    "PL": ["Place", "Plce"],
    "GR": ["Grove", "Gr."],
    "DR": ["Drive", "Dr."],
    "TER": ["Terrace", "Ter."],
    "APT": ["Apartments", "Apartment", "Aprt", "Aprts", "Apt."],
}
DIRECTION_SYNONYMS = {
    "N": ["North", "Nth"],
    "S": ["South", "Sth"],
    "E": ["East", "Est"],
    "W": ["West", "Wst"],
}
# ====================================


# ====== КОВЕРКАНИЕ ИМЁН И АДРЕСОВ ======

def _perturb_word_letters(word: str, max_changes: int = 1) -> str:
    """
    Слегка коверкать буквы в слове (макс. 1 изменение) или добавлять лишнюю букву (50/50).
    """
    if not word or len(word) < 4:
        return word

    if any(char.isdigit() for char in word):
        return word # НЕ ТРОГАЕМ СЛОВА С ЦИФРАМИ (НОМЕРА ДОМОВ/КВАРТИР)

    chars = list(word)
    letter_positions = [i for i, c in enumerate(chars) if c.isalpha()]
    
    if not letter_positions:
        return word

    # 50% шанс изменить букву, 50% шанс добавить букву
    if random.random() < 0.5:
        # СЛУЧАЙ 1: Изменение существующей буквы (макс. 1)
        pos = random.choice(letter_positions)
        old = chars[pos]
        if old.isupper():
            alphabet = string.ascii_uppercase
        else:
            alphabet = string.ascii_lowercase
        candidates = [ch for ch in alphabet if ch != old]
        if candidates:
            chars[pos] = random.choice(candidates)
    else:
        # СЛУЧАЙ 2: Добавление лишней буквы
        insert_pos = random.randint(1, len(chars)) 
        
        if insert_pos > 0 and chars[insert_pos - 1].isupper():
            new_char = random.choice(string.ascii_uppercase)
        else:
            new_char = random.choice(string.ascii_lowercase)
            
        chars.insert(insert_pos, new_char)

    return "".join(chars)


def perturb_name(full_name: str) -> str:
    """
    Правила:
    - Максимум 1 изменение (буква/добавление) в каждом слове.
    - 50% шанс поменять местами имя и фамилию.
    """
    if not full_name:
        return full_name

    words = full_name.split()
    
    # 50% шанс поменять местами имя/фамилию (если минимум 2 слова)
    if len(words) >= 2 and random.random() < 0.5:
        words[0], words[1] = words[1], words[0]

    # Коверкаем каждое слово с макс. 1 изменением
    mutated = [_perturb_word_letters(w, max_changes=1) for w in words]
    return " ".join(mutated)


def col_to_letter(col: int) -> str:
    """1 -> A, 2 -> B, ..."""
    result = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        result = chr(65 + rem) + result
    return result


def _perturb_city(city: str) -> str:
    """
    Город: максимум 1 изменение (буква/добавление) и не первая буква,
    только в 50% случаев.
    """
    if not city or len(city) < 4:
        return city
        
    if any(char.isdigit() for char in city):
        return city # НЕ ТРОГАЕМ СЛОВА С ЦИФРАМИ

    # Новое правило: Коверкаем только в 50% случаев
    if random.random() < 0.5:
        return city
        
    chars = list(city)
    letter_positions = [i for i, c in enumerate(chars) if c.isalpha()]

    # Убираем первую букву из кандидатов на изменение
    change_positions = [i for i in letter_positions if i != 0]
    
    if not change_positions:
        return city
        
    # 50% шанс изменить букву, 50% шанс добавить букву
    if random.random() < 0.5:
        # СЛУЧАЙ 1: Изменение существующей буквы
        pos = random.choice(change_positions)
        old = chars[pos]
        if old.isupper():
            alphabet = string.ascii_uppercase
        else:
            alphabet = string.ascii_lowercase
        candidates = [ch for ch in alphabet if ch != old]
        if candidates:
            chars[pos] = random.choice(candidates)
    else:
        # СЛУЧАЙ 2: Добавление лишней буквы
        insert_pos = random.randint(1, len(chars)) 
        
        if insert_pos > 0 and chars[insert_pos - 1].isupper():
            new_char = random.choice(string.ascii_uppercase)
        else:
            new_char = random.choice(string.ascii_lowercase)
            
        chars.insert(insert_pos, new_char)

    return "".join(chars)


def replace_with_synonym(word, synonym_map):
    """
    Заменяет слово на синоним из карты, если слово найдено в карте (без учета регистра/точек).
    """
    upper_word = word.upper().strip().replace('.', '')
    # Объединяем все глобальные карты синонимов
    full_map = {
        "RD": ["Road", "Roud", "Rd."],
        "ST": ["Street", "Strt", "St."],
        "CT": ["Court", "Ct."],
        "AVE": ["Avenue", "Ave."],
        "LN": ["Lane", "Lnae"],
        "PL": ["Place", "Plce"],
        "GR": ["Grove", "Gr."],
        "DR": ["Drive", "Dr."],
        "TER": ["Terrace", "Ter."],
        "APT": ["Apartments", "Apartment", "Aprt", "Aprts", "Apt."],
        "N": ["North", "Nth"],
        "S": ["South", "Sth"],
        "E": ["East", "Est"],
        "W": ["West", "Wst"],
    }

    if upper_word in full_map:
        return random.choice(full_map[upper_word])
    return word

def perturb_address(
    addr1: str, addr2: str, city: str, state: str, zip_code: str
) -> str:
    """
    Коверкает адрес, собирает его в одну строку для записи в GS (COL_ADDRESS).
    """
    mutated_parts = []

    # 1. КОНОРКАНИЕ УЛИЦЫ (addr1)
    street_parts = addr1.split()
    new_street_parts = []
    
    for word in street_parts:
        if any(char.isdigit() for char in word):
            new_street_parts.append(word) # Сохраняем номера домов/Line 1
            continue
        
        upper_word = word.upper().replace('.', '')
        
        # Замена синонимов (Rd, St, N, S, APT и т.д.)
        if upper_word in STREET_SYNONYMS or upper_word in DIRECTION_SYNONYMS:
            new_street_parts.append(replace_with_synonym(word, {})) 
        else:
            # Коверкаем только основные слова в названии улицы
            new_street_parts.append(_perturb_word_letters(word, max_changes=1))

    mutated_parts.append(" ".join(new_street_parts))

    # 2. КОНОРКАНИЕ LINE 2 (addr2)
    if addr2:
        line2_parts = addr2.split()
        new_line2_parts = []
        for word in line2_parts:
             if any(char.isdigit() for char in word):
                new_line2_parts.append(word) # Сохраняем номера квартир
             else:
                # Замена синонимов (Apt, Unit и т.д.)
                upper_word = word.upper().replace('.', '')
                if upper_word in STREET_SYNONYMS: 
                    new_line2_parts.append(replace_with_synonym(word, {}))
                else:
                    new_line2_parts.append(_perturb_city(word)) 
        mutated_parts.append(" ".join(new_line2_parts)) 

    # 3. КОНОРКАНИЕ ГОРОДА
    city_words = city.split()
    # Коверкаем только ПЕРВОЕ слово города, в 50% случаев
    if city_words:
        city_words[0] = _perturb_city(city_words[0])
    mutated_parts.append(" ".join(city_words))

    # 4. Добавляем неискаженные State/Zip/Country
    mutated_parts.append(f"{state} {zip_code}")
    mutated_parts.append("United States")

    return ", ".join([p.strip() for p in mutated_parts if p.strip()])


# --- products / serials helpers ---

def get_products_from_header():
    """
    Считать список товаров из первой строки листа 'Товары'.
    """
    headers = sheet_products.row_values(1)
    products = []
    for idx, name in enumerate(headers, start=1):
        if not name:
            continue
        if name.strip().upper().endswith("USED"):
            continue
        products.append((idx, name.strip()))
    return products


def get_serial_for_product(product_name: str) -> str:
    """
    Найти первый свободный серийник для товара и
    ПЕРЕНЕСТИ его: из основного столбца -> в столбец USED (основной очистить).
    """
    headers = sheet_products.row_values(1)
    try:
        col_idx = headers.index(product_name) + 1  # 1-based
    except ValueError:
        raise RuntimeError(f"Не найден столбец для товара '{product_name}' в листе 'Товары'.")

    used_col_idx = col_idx + 1

    # Читаем данные из листа "Товары", начиная со второй строки (индекс 0 в списках)
    col_vals = sheet_products.col_values(col_idx)[1:]
    used_vals = sheet_products.col_values(used_col_idx)[1:]

    # i - это фактический номер строки в Google Sheets (начиная с 2)
    for i, serial in enumerate(col_vals, start=2): 
        # list_index - индекс в списках col_vals/used_vals (начинается с 0)
        list_index = i - 2
        
        serial = serial.strip()
        used = used_vals[list_index].strip() if list_index < len(used_vals) else ""
        
        if serial and not used:
            # Найдена свободная запись в строке i листа Товары
            row_idx = i 
            main_col_letter = col_to_letter(col_idx)
            used_col_letter = col_to_letter(used_col_idx)
            rng = f"{main_col_letter}{row_idx}:{used_col_letter}{row_idx}"
            
            # основной столбец очищаем, в USED пишем серийник
            sheet_products.update(rng, [["", serial]])
            logger.info(f"Выдан серийник {serial} для товара '{product_name}' (строка {row_idx})")
            return serial

    raise RuntimeError(f"Нет доступных серийников для товара '{product_name}'. Добавь новые в лист 'Товары'.")


# --- emails helpers ---

def get_email_from_pool() -> str:
    col_emails = sheet_emails.col_values(1)[1:]  # без заголовка
    col_used = sheet_emails.col_values(2)[1:]

    for i, email in enumerate(col_emails, start=2):
        email = email.strip()
        used = col_used[i - 2].strip() if i - 2 < len(col_used) else ""
        if email and not used:
            row_idx = i
            rng = f"A{i}:B{i}"
            
            try:
                sheet_emails.update(rng, [["", email]], value_input_option='USER_ENTERED')
            except Exception as e:
                logger.error(f"Ошибка обновления Google Sheets (Emails, строка {row_idx}): {e}")
                raise RuntimeError(f"Ошибка при блокировке email: {email}")

            logger.info(f"Выдан email {email} (строка {row_idx} листа Emails)")
            return email

    raise RuntimeError("Нет свободных email-ов в листе 'Emails'. Добавь новые Email / очисти USED.")


# --- date generation helper ---

def generate_random_date_str() -> str:
    """
    Генерирует случайную дату в диапазоне от 4 до 9 месяцев НАЗАД от текущей даты.
    Возвращает строку в формате DD.MM.YYYY.
    """
    now = datetime.now()
    
    min_days_back = 4 * 30.4375
    max_days_back = 9 * 30.4375
    
    random_days = random.randint(int(min_days_back), int(max_days_back))
    
    random_date = now - timedelta(days=random_days)
    
    return random_date.strftime("%d.%m.%Y")


# --- accounts sheet helpers ---

def assign_account(
    name: str,
    address: str, # Искаженный адрес
    phone: str = "",
    product: str | None = None,
    issue_reason: str | None = None,
):
    """
    Создать НОВУЮ строку в Shokz_accounts и вернуть данные аккаунта.
    """
    if not product:
        raise RuntimeError("Не указан товар при выдаче аккаунта (product=None).")

    email = get_email_from_pool()
    serial = get_serial_for_product(product)

    all_values = sheet_accounts.get_all_values()
    data_rows = max(0, len(all_values) - 1)
    order_seq = data_rows + 1
    order_no = f"SHKZ{order_seq:03d}"

    row_idx = data_rows + 2

    issue = issue_reason or random.choice(ISSUE_TEMPLATES)
    date_receipt = generate_random_date_str() # Дата для квитанции (в прошлом)
    date_gs_current = datetime.now().strftime("%d.%m.%Y") # ТЕКУЩАЯ ДАТА ЗАКАЗА
    
    min_len = COL_RECEIPT_LINK 
    new_row = [""] * min_len
    
    # --- ЯВНОЕ ЗАПОЛНЕНИЕ ПОЛЕЙ ---
    new_row[COL_DATE - 1] = date_gs_current # ИСПРАВЛЕНО: ТЕКУЩАЯ ДАТА ЗАКАЗА
    new_row[COL_ORDER_NO - 1] = order_no
    new_row[COL_NAME - 1] = name
    new_row[COL_EMAIL - 1] = email 
    new_row[COL_ADDRESS - 1] = address # ИСКАЖЕННЫЙ АДРЕС
    new_row[COL_PHONE - 1] = phone
    new_row[COL_PRODUCT - 1] = product
    new_row[COL_SERIAL - 1] = serial
    new_row[COL_STATUS - 1] = "Новый"
    new_row[COL_ISSUE - 1] = issue
    # new_row[COL_RECEIPT_LINK - 1] остается пустым, будет обновлен после генерации ссылки

    range_a1 = f"A{row_idx}:{col_to_letter(COL_RECEIPT_LINK)}{row_idx}"
    sheet_accounts.update(range_a1, [new_row])

    return {
        "row_idx": row_idx,
        "email": email,
        "product": product,
        "serial": serial,
        "issue": issue,
        "name": name,
        "address": address,
        "phone": phone,
        "order_no": order_no,
        "date": date_receipt, # Дата для квитанции (в прошлом)
    }


def update_status(row_idx: int, status_value: str):
    sheet_accounts.update(f"I{row_idx}", [[status_value]])
    logger.info(f"Статус строки {row_idx} обновлён на {status_value}")


# --- receipt helpers ---

def build_receipt_url(shop_key: str, account: dict) -> str:
    """
    Генерирует ссылку на макет квитанции, используя shop_key.
    
    ВНИМАНИЕ: Для генерации URL используются ЧИСТЫЕ КОМПОНЕНТЫ АДРЕСА.
    """
    layout = RECEIPT_LAYOUTS.get(shop_key)
    if not layout:
        raise ValueError(f"Неизвестный ключ магазина: {shop_key}")
        
    base_url = layout["base_url"]

    # 1. ПОЛУЧАЕМ ID ТОВАРА ДЛЯ ТИЛЬДЫ
    product_name = account.get("product", "")
    
    product_tilda_id = PRODUCT_ID_MAP.get(product_name)
    
    if not product_tilda_id:
         raise ValueError(f"Товар '{product_name}' не найден в маппинге PRODUCT_ID_MAP. Обновите receipt_product_map.py.")
    
    # 2. ПАРСИНГ ДАТЫ
    date_str = account.get("date")
    date_iso = ""
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            date_iso = ""

    # 3. ЧТЕНИЕ ЧИСТЫХ КОМПОНЕНТОВ АДРЕСА ДЛЯ URL (Прямой доступ)
    # Эти поля ГАРАНТИРОВАННО приходят из handle_callback / process_ebay_photo
    addr1 = account.get("addr1_clean", "")
    addr2 = account.get("addr2_clean", "")
    city_name = account.get("city_clean", "")
    state_code = account.get("state_clean", "")
    zip_code = account.get("zip_clean", "")


    # 4. ФОРМИРОВАНИЕ ПАРАМЕТРОВ
    params = {
        "product": product_tilda_id,
        "date": date_iso,
        "name": account.get("name", ""),
        "addr1": addr1,
        "addr2": addr2, 
        "city": city_name, 
        "zip": zip_code,
        "state": state_code,
    }

    # Ключевой момент: quote_via=quote, иначе URL будет с +
    query = urlencode(params, quote_via=quote)

    return f"{base_url}?{query}"


# --- keyboards (без изменений) ---

def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Новый Shokz (категории)", callback_data="mode:categories")],
            [InlineKeyboardButton(text="🧾 Новый Shokz (eBay скрин)", callback_data="mode:ebay")],
            [InlineKeyboardButton(text="🔄 Обновить статус", callback_data="mode:update_status")],
        ]
    )


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перевозчики", callback_data="cat:carriers")],
            [InlineKeyboardButton(text="Типы", callback_data="cat:types")],
            [InlineKeyboardButton(text="Посреды", callback_data="cat:mediators")],
        ]
    )


def recipients_keyboard(sheet, category_key: str) -> InlineKeyboardMarkup:
    values = sheet.get_all_values()[1:]  # без заголовка
    buttons = []
    for idx, row in enumerate(values, start=2):
        name = row[0] if len(row) > 0 else f"Получатель {idx - 1}"
        text_btn = name if len(name) <= 40 else name[:37] + "..."
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text_btn,
                    callback_data=f"recipient:{category_key}:{idx}",
                )
            ]
        )
    if not buttons:
        buttons = [[InlineKeyboardButton(text="(нет получателей)", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(cat_key: str, recipient_row: int) -> InlineKeyboardMarkup:
    products = get_products_from_header()
    buttons = []
    
    headers = sheet_products.row_values(1)
    
    for col_idx, name in products:
        text_btn = name if len(name) <= 40 else name[:37] + "..."
        
        # Передаем НАЗВАНИЕ товара (URL-кодированное)
        product_name_encoded = quote(name)
        
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text_btn,
                    callback_data=f"shop_prompt:{cat_key}:{recipient_row}:{product_name_encoded}", 
                )
            ]
        )
    if not buttons:
        buttons = [[InlineKeyboardButton(text="(нет товаров)", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def shop_select_keyboard(cat_key: str, recipient_row: int, product_name: str) -> InlineKeyboardMarkup:
    """Новая клавиатура для выбора магазина."""
    # product_name теперь является строкой с названием товара
    product_name_encoded = quote(product_name)
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛍️ Amazon",
                    # Теперь передаем закодированное название товара
                    callback_data=f"shop_select:amazon:{cat_key}:{recipient_row}:{product_name_encoded}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛒 BestBuy",
                    # Теперь передаем закодированное название товара
                    callback_data=f"shop_select:bestbuy:{cat_key}:{recipient_row}:{product_name_encoded}",
                )
            ],
        ]
    )


def status_keyboard(row_idx: int) -> InlineKeyboardMarkup:
    """
    Кнопки статуса + быстрый переход к созданию нового аккаунта.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟡 Новый", callback_data=f"status:new:{row_idx}")],
            [InlineKeyboardButton(text="🟠 Оформлен", callback_data=f"status:in_progress:{row_idx}")],
            [InlineKeyboardButton(text="🟢 Одобрен", callback_data=f"status:approved:{row_idx}")],
            [InlineKeyboardButton(text="➕ Новый аккаунт", callback_data="mode:categories")],
        ]
    )


# --- handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Это бот для выдачи Shokz аккаунтов.\nВыбери режим:",
        reply_markup=start_keyboard(),
    )


@dp.message(Command("test_receipt"))
async def cmd_test_receipt(message: types.Message):
    """
    Тест: собираем URL квитанции Amazon по тестовым данным.
    """
    shop_key = "amazon"
    test_product_name = "Openrun Pro 2 Black" 
    account = {
        "name": "Yahmere Wixhon",
        "product": test_product_name, 
        "date": generate_random_date_str(), # Используем новую логику даты (в прошлом)
        # Тестовый адрес с Line 2
        "address": "36 Court Gr, Apt. A, Wilmington, DE 19805, United States", 
    }

    try:
        url = build_receipt_url(shop_key, account)
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}")
        return

    # Отправляем только ссылку
    await message.answer(
        f"Тестовая ссылка {shop_key.capitalize()} успешно сгенерирована:\n"
        f"Дата: {account['date']}\n"
        f"<code>{url}</code>",
    )


@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    data = call.data or ""

    if data == "noop":
        await call.answer()
        return

    if data == "mode:categories":
        await call.message.answer("Выбери категорию получателя:", reply_markup=category_keyboard())
        await call.answer()
        return

    if data == "mode:ebay":
        waiting_for_ebay_users.add(call.from_user.id)
        await call.message.answer("Отправь скриншот заказа eBay одним фото.")
        await call.answer()
        return

    if data == "mode:update_status":
        waiting_for_status_update.add(call.from_user.id)
        await call.message.answer("Введи номер аккаунта (SHKZ001) или email.")
        await call.answer()
        return

    if data.startswith("cat:"):
        _, cat_key = data.split(":", 1)
        sheet_map = {
            "carriers": sheet_carriers,
            "types": sheet_types,
            "mediators": sheet_mediators,
        }
        sheet = sheet_map.get(cat_key)
        if not sheet:
            await call.message.answer("Неизвестная категория.")
            await call.answer()
            return

        kb = recipients_keyboard(sheet, cat_key)
        await call.message.answer("Выбери получателя:", reply_markup=kb)
        await call.answer()
        return

    if data.startswith("recipient:"):
        _, cat_key, row_str = data.split(":", 2)
        row_idx = int(row_str)

        kb = products_keyboard(cat_key, row_idx)
        await call.message.answer("Теперь выбери товар:", reply_markup=kb)
        await call.answer()
        return
    
    # Новый шаг: Запрос магазина после выбора товара
    if data.startswith("shop_prompt:"):
        _, cat_key, row_str, product_name_encoded = data.split(":", 3)
        recipient_row = int(row_str)
        
        product_name = unquote(product_name_encoded) 

        kb = shop_select_keyboard(cat_key, recipient_row, product_name)
        await call.message.answer("Выберите магазин для генерации квитанции:", reply_markup=kb)
        await call.answer()
        return

    # Финальный шаг: Генерация аккаунта и ссылки на квитанцию
    if data.startswith("shop_select:"):
        _, shop_key, cat_key, row_str, product_name_encoded = data.split(":", 4)
        recipient_row = int(row_str)
        
        product_name = unquote(product_name_encoded)

        sheet_map = {
            "carriers": sheet_carriers,
            "types": sheet_types,
            "mediators": sheet_mediators,
        }
        sheet = sheet_map.get(cat_key)
        if not sheet:
            await call.message.answer("Неизвестная категория.")
            await call.answer()
            return

        # 1. ПОДГОТОВКА ДАННЫХ
        row = sheet.row_values(recipient_row)
        
        # !!! КРИТИЧЕСКОЕ ЧТЕНИЕ КОЛОНОК АДРЕСА ИЗ GS !!!
        # Мы ожидаем 6 колонок: [Имя(0), Улица(1), Линия 2(2), Город(3), Штат(4), ZIP(5)]
        if len(row) < 6:
             await call.message.answer(f"❌ Ошибка структуры GS: Недостаточно колонок адреса в листе '{sheet.title}'. Ожидается минимум 6 (Имя, Улица, Линия 2, Город, Штат, ZIP).")
             await call.answer()
             return
             
        base_name = row[0].strip()
        base_addr1 = row[1].strip()
        base_addr2 = row[2].strip()
        base_city = row[3].strip()
        base_state = row[4].strip()
        base_zip = row[5].strip()
        
        # --- ГЕНЕРАЦИЯ ИСКАЖЕННЫХ ДАННЫХ ДЛЯ ЗАПИСИ В GS/ОТЧЕТА ---
        name = perturb_name(base_name)
        
        # Используем чистые компоненты для генерации искаженного адреса (для записи в GS)
        address_mutated = perturb_address(
            addr1=base_addr1,
            addr2=base_addr2,
            city=base_city,
            state=base_state,
            zip_code=base_zip
        ) 
        
        zip_code, _city = parse_zip_and_city(base_zip or "") # Используем чистый ZIP для fake_phone
        phone = fake_phone(zip_code)

        # 2. ГЕНЕРАЦИЯ АККАУНТА (запись в Google Sheets)
        try:
            result = assign_account(
                name=name,
                address=address_mutated, # Записываем искаженный адрес в GS
                phone=phone,
                product=product_name,
            )
        except RuntimeError as e:
            await call.message.answer(f"❌ {e}")
            await call.answer()
            return
        except Exception as e:
            logger.exception("Ошибка при выдаче аккаунта (категории+товар)")
            await call.message.answer(f"❌ Ошибка при выдаче аккаунта: {e}")
            await call.answer()
            return

        # 3. ГЕНЕРАЦИЯ ССЫЛКИ
        account_data_for_receipt = {
            "name": result['name'],
            # Передаем ЧИСТЫЕ КОМПОНЕНТЫ для URL
            "addr1_clean": base_addr1, 
            "addr2_clean": base_addr2,
            "city_clean": base_city,
            "state_clean": base_state,
            "zip_clean": base_zip,
            "date": result['date'],
            "product": result['product'], 
        }

        links_text = "" # Для сборки ссылок
        final_url = "" # Сохраняем одну ссылку для обновления GS

        for key in ["amazon", "bestbuy"]:
            try:
                url = build_receipt_url(key, account_data_for_receipt)
                links_text += f"*{key.capitalize()}*: <code>{url}</code>\n"
                if key == shop_key:
                     final_url = url # Сохраняем выбранную ссылку
            except ValueError as e:
                links_text += f"*{key.capitalize()}*: ❌ Ошибка ({e})\n"
            except Exception as e:
                logger.exception(f"Неожиданная ошибка при генерации URL квитанции {key}")
                links_text += f"*{key.capitalize()}*: ❌ Непредвиденная ошибка\n"


        # 4. ОБНОВЛЕНИЕ КОЛОНКИ ССЫЛКИ В GS
        if final_url:
            link_for_gs = f'=HYPERLINK("{final_url}", "Receipt Link ({shop_key.capitalize()})")'
            sheet_accounts.update_cell(result["row_idx"], COL_RECEIPT_LINK, link_for_gs)
            logger.info(f"Ссылка записана в COL_RECEIPT_LINK: {link_for_gs}")


        # 5. ОТПРАВКА ДАННЫХ АККАУНТА + ССЫЛКА
        text_resp = (
            f"✅ **Аккаунт для Shokz создан:**\n"
            f"№ Заказа: **{result['order_no']}**\n"
            f"Имя: {result['name']}\n"
            f"Email: {result['email']}\n"
            f"Адрес: {result['address']}\n" # Отправляем искаженный адрес пользователю
            f"Телефон: {result['phone']}\n"
            f"Товар: {result['product']}\n"
            f"Серийник: {result['serial']}\n"
            "\nПричина обращения:\n" + result["issue"] + "\n\n" + links_text
        )

        await call.message.answer(text_resp, reply_markup=status_keyboard(result["row_idx"]))
        await call.message.answer("Что дальше?", reply_markup=start_keyboard())
        await call.answer()
        return

    if data.startswith("status:"):
        _, status_key, row_str = data.split(":", 2)
        row_idx = int(row_str)

        mapping = {
            "new": "Новый",
            "in_progress": "Оформлен",
            "approved": "Одобрен",
        }
        status_value = mapping.get(status_key, status_key)

        try:
            update_status(row_idx, status_value)
            await call.answer("Статус сохранён.")
            await call.message.answer(f"Статус для строки {row_idx} обновлён: {status_value}")
        except Exception as e:
            logger.exception("Ошибка при обновлении статуса")
            await call.message.answer(f"❌ Ошибка при обновлении статуса: {e}")
            await call.answer()
        return

    await call.answer()


async def process_ebay_photo(message: types.Message):
    """
    Обработка скрина заказа eBay: OCR -> GPT -> запись строки -> выдача аккаунта и обеих ссылок.
    """
    local_file = None
    try:
        if not message.photo:
            await message.answer("Пожалуйста, отправь фото заказа eBay.")
            return

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path
        local_file = f"{photo.file_id}.jpg"
        await bot.download_file(file_path, local_file)
        logger.info(f"Фото скачано: {local_file}")

        ocr_result = await ocr_space_file(local_file)
        parsed_text = ocr_result.get("ParsedResults", [{}])[0].get("ParsedText", "")
        
        structured = await asyncio.to_thread(gpt_structured_fields, parsed_text)
        logger.info(f"Структурированные данные: {structured}")
        name = structured.get("Имя", "")
        address = structured.get("Адрес", "") # Адрес, который вернул GPT
        product = structured.get("Товар", "")

        # 1. Парсинг адреса от GPT/OCR
        zip_code, city_name_from_util = parse_zip_and_city(address or "")
        
        state_match = re.search(r'([A-Z]{2})\s' + re.escape(zip_code), address or "")
        state_code = state_match.group(1) if state_match else ""
        
        # 1. Считаем все, кроме Города/ST/ZIP, как Line 1
        addr1_url = address
        
        # Удаляем ZIP
        if zip_code and zip_code != "00000":
            addr1_url = re.sub(r'\b' + re.escape(zip_code) + r'\b', '', addr1_url).strip()
        # Удаляем State
        if state_code:
            addr1_url = re.sub(r'\b' + re.escape(state_code) + r'\b', '', addr1_url, flags=re.IGNORECASE).strip()
        # Удаляем City
        if city_name_from_util:
            addr1_url = re.sub(r'\b' + re.escape(city_name_from_util) + r'\b', '', addr1_url, flags=re.IGNORECASE).strip()
            
        # Очищаем лишние символы
        addr1_url = addr1_url.replace('United States', '').replace(',', ' ').replace('  ', ' ').strip()
        
        addr2_url = "" # Line 2 остается пустым
        
        phone = fake_phone(zip_code)

        # 2. Запись разобранных данных в лист eBay_Addresses
        try:
            # Запись разобранных компонентов, даже если они не идеальны
            new_row_ebay = [
                name or "[нет имени]",
                addr1_url, # Улица + Line 2
                addr2_url, # Пусто
                city_name_from_util,
                state_code,
                zip_code,
                product or "[нет товара]",
            ]
            # Вам нужно будет определить sheet_ebay_addresses, если вы хотите включить эту запись
            # sheet_ebay_addresses.append_row(new_row_ebay)
            logger.info(f"Запись в eBay_Addresses (логически) успешна.")
        except Exception as e:
             logger.error(f"Ошибка записи в eBay_Addresses: {e}")
             
        
        # 3. ГЕНЕРАЦИЯ АККАУНТА (запись в Google Sheets)
        try:
            result = assign_account(
                name=name or "[имя не найдено]",
                address=address or "",
                phone=phone,
                product=product or None,
            )
        except RuntimeError as e:
            await message.answer(f"❌ {e}")
            return

        # 4. ГЕНЕРАЦИЯ ССЫЛКИ
        account_data_for_receipt = {
            "name": result['name'],
            "address": result['address'],
            "date": result['date'],
            "product": result['product'], 
            # Передаем разобранные компоненты для URL
            "addr1_clean": addr1_url,
            "addr2_clean": addr2_url, 
            "city_clean": city_name_from_util,
            "state_clean": state_code,
            "zip_clean": zip_code,
        }
        
        links_text = "🔗 **Ссылки на квитанции:**\n"
        final_url = ""
        
        for shop_key in ["amazon", "bestbuy"]:
            try:
                url = build_receipt_url(shop_key, account_data_for_receipt)
                links_text += f"*{shop_key.capitalize()}*: <code>{url}</code>\n"
                if not final_url:
                     final_url = url # Сохраняем первую успешную ссылку
            except ValueError as e:
                links_text += f"*{shop_key.capitalize()}*: ❌ Ошибка ({e})\n"
            except Exception as e:
                logger.exception(f"Неожиданная ошибка при генерации URL квитанции {shop_key}")
                links_text += f"*{shop_key.capitalize()}*: ❌ Непредвиденная ошибка\n"


        # 5. ОБНОВЛЕНИЕ КОЛОНКИ ССЫЛКИ В GS
        if final_url:
            link_for_gs = f'=HYPERLINK("{final_url}", "Receipt Link")'
            sheet_accounts.update_cell(result["row_idx"], COL_RECEIPT_LINK, link_for_gs)
            logger.info(f"Ссылка записана в COL_RECEIPT_LINK: {link_for_gs}")


        # 6. ОТПРАВКА ДАННЫХ АККАУНТА + ССЫЛКА
        text_resp = (
            f"✅ **Заказ eBay обработан.**\n\n"
            f"Имя: {name or '[имя не найдено]'}\n"
            f"Адрес: {address or '[адрес не найден]'}\n"
            f"Товар: {product or '[товар не найден]'}\n\n"
            f"**Shokz аккаунт:**\n"
            f"Email: {result['email']}\n"
            f"Телефон: {result['phone']}\n"
            f"Серийник: {result['serial']}\n"
            f"Номер заказа: {result['order_no']}\n"
            "\nПричина обращения:\n" + result["issue"] + "\n\n" + links_text
        )

        await message.answer(text_resp, reply_markup=status_keyboard(result["row_idx"]))
        await message.answer("Что дальше?", reply_markup=start_keyboard())

    except Exception as e:
        logger.exception("Ошибка при обработке eBay скрина")
        await message.answer(f"❌ Ошибка при обработке скрина: {e}")
    finally:
        if local_file and os.path.exists(local_file):
            os.remove(local_file)
            logger.info("Фото удалено после обработки.")


@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    # 1) eBay: ждём фото
    if user_id in waiting_for_ebay_users and message.photo:
        waiting_for_ebay_users.discard(user_id)
        await process_ebay_photo(message)
        return

    # 2) обновление статуса: ждём номер или email
    if user_id in waiting_for_status_update and message.text:
        waiting_for_status_update.discard(user_id)
        query = (message.text or "").strip()

        if not query:
            await message.answer("Пустой ввод. Попробуй ещё раз через «Обновить статус».")
            return

        row_idx = None

        # если это похоже на email
        if "@" in query:
            target_email = query.strip().lower()
            col_emails = sheet_accounts.col_values(COL_EMAIL)[1:]  # без заголовка
            for idx, val in enumerate(col_emails, start=2):
                if val.strip().lower() == target_email:
                    row_idx = idx
                    break
        else:
            # считаем, что это код SHKZ...
            code = query.strip().upper()
            col_order = sheet_accounts.col_values(COL_ORDER_NO)[1:]  # без заголовка
            for idx, val in enumerate(col_order, start=2):
                if val.strip().upper() == code:
                    row_idx = idx
                    break

        if row_idx is None:
            await message.answer("Аккаунт не найден ни по номеру, ни по email.")
            return

        row = sheet_accounts.row_values(row_idx)

        def safe(col_idx: int) -> str:
            return row[col_idx - 1] if len(row) >= col_idx else ""

        name = safe(COL_NAME)
        email = safe(COL_EMAIL)
        address = safe(COL_ADDRESS)
        phone = safe(COL_PHONE)
        product = safe(COL_PRODUCT)
        serial = safe(COL_SERIAL)
        status = safe(COL_STATUS)
        issue = safe(COL_ISSUE)
        order_no = safe(COL_ORDER_NO)

        text_resp = (
            f"Текущий аккаунт {order_no or '[без номера]'}:\n"
            f"Имя: {name}\n"
            f"Email: {email}\n"
            f"Адрес: {address}\n"
            f"Телефон: {phone}\n"
            f"Товар: {product}\n"
            f"Серийник: {serial}\n"
            f"Текущий статус: {status or '—'}\n\n"
            f"Причина обращения:\n{issue}"
        )

        await message.answer(text_resp, reply_markup=status_keyboard(row_idx))
        return

    # 3) Если прислали фото, но режим eBay не включён
    if message.photo:
        await message.answer(
            "Если хочешь обработать eBay заказ, сначала выбери режим "
            "'Новый Shokz (eBay скрин)' через /start."
        )
        return

    # 4) дефолт
    await message.answer("Используй /start, чтобы выбрать режим.")


async def main():
    logger.info("Shokz бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import re
    # Этот импорт нужен, чтобы re был доступен в build_receipt_url
        
    asyncio.run(main())