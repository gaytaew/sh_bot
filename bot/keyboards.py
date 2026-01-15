"""
Клавиатуры для Telegram бота Shokz.
"""
from urllib.parse import quote, unquote
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.google_sheets import get_sheets_service
from services.accounts import get_account_service


def start_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Новый Shokz (категории)", callback_data="mode:categories")],
            [InlineKeyboardButton(text="🧾 Новый Shokz (eBay скрин)", callback_data="mode:ebay")],
            [InlineKeyboardButton(text="🔄 Обновить статус", callback_data="mode:update_status")],
        ]
    )


def category_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории получателя."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перевозчики", callback_data="cat:carriers")],
            [InlineKeyboardButton(text="Типы", callback_data="cat:types")],
            [InlineKeyboardButton(text="Посреды", callback_data="cat:mediators")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
        ]
    )


def recipients_keyboard(sheet, category_key: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора получателя из категории."""
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
    # Добавляем кнопку возврата к категориям
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="mode:categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(cat_key: str, recipient_row: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора товара."""
    account_service = get_account_service()
    products = account_service.get_products_from_header()
    buttons = []
    
    for col_idx, name in products:
        text_btn = name if len(name) <= 40 else name[:37] + "..."
        
        # Передаем НАЗВАНИЕ товара (URL-кодированное)
        product_name_encoded = quote(name)
        
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text_btn,
                    callback_data=f"product_select:{cat_key}:{recipient_row}:{product_name_encoded}", 
                )
            ]
        )
    if not buttons:
        buttons = [[InlineKeyboardButton(text="(нет товаров)", callback_data="noop")]]
    # Добавляем кнопку возврата в главное меню
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="mode:categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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

