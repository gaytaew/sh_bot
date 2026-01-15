"""
Обработчики для создания аккаунтов через категории (Перевозчики/Типы/Посреды).
"""
from urllib.parse import unquote
from aiogram import Router, types

from bot.keyboards import (
    category_keyboard,
    recipients_keyboard,
    products_keyboard,
    status_keyboard,
    start_keyboard,
)
from services.google_sheets import get_sheets_service
from services.accounts import get_account_service
from services.receipts import get_receipt_service
from models import ReceiptData

router = Router()


@router.callback_query(lambda c: c.data == "mode:categories")
async def handle_mode_categories(call: types.CallbackQuery):
    """Обработчик выбора режима категорий."""
    await call.message.answer("Выбери категорию получателя:", reply_markup=category_keyboard())
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cat:"))
async def handle_category(call: types.CallbackQuery):
    """Обработчик выбора категории."""
    _, cat_key = call.data.split(":", 1)
    sheets = get_sheets_service()
    sheet = sheets.get_sheet_by_category(cat_key)
    
    if not sheet:
        await call.message.answer("Неизвестная категория.", reply_markup=start_keyboard())
        await call.answer()
        return

    kb = recipients_keyboard(sheet, cat_key)
    await call.message.answer("Выбери получателя:", reply_markup=kb)
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("recipient:"))
async def handle_recipient(call: types.CallbackQuery):
    """Обработчик выбора получателя."""
    _, cat_key, row_str = call.data.split(":", 2)
    row_idx = int(row_str)

    kb = products_keyboard(cat_key, row_idx)
    await call.message.answer("Теперь выбери товар:", reply_markup=kb)
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("product_select:"))
async def handle_product_select(call: types.CallbackQuery):
    """Обработчик выбора товара - сразу создает аккаунт и генерирует обе ссылки."""
    _, cat_key, row_str, product_name_encoded = call.data.split(":", 3)
    recipient_row = int(row_str)
    
    product_name = unquote(product_name_encoded)

    sheets = get_sheets_service()
    sheet = sheets.get_sheet_by_category(cat_key)
    
    if not sheet:
        await call.message.answer("Неизвестная категория.", reply_markup=start_keyboard())
        await call.answer()
        return

    # 1. ПОДГОТОВКА ДАННЫХ
    row = sheet.row_values(recipient_row)
    
    # !!! КРИТИЧЕСКОЕ ЧТЕНИЕ КОЛОНОК АДРЕСА ИЗ GS !!!
    # Мы ожидаем 6 колонок: [Имя(0), Улица(1), Линия 2(2), Город(3), Штат(4), ZIP(5)]
    if len(row) < 6:
         await call.message.answer(
             f"❌ Ошибка структуры GS: Недостаточно колонок адреса в листе '{sheet.title}'. "
             f"Ожидается минимум 6 (Имя, Улица, Линия 2, Город, Штат, ZIP).",
             reply_markup=start_keyboard()
         )
         await call.answer()
         return
         
    base_name = row[0].strip()
    base_addr1 = row[1].strip()
    base_addr2 = row[2].strip()
    base_city = row[3].strip()
    base_state = row[4].strip()
    base_zip = row[5].strip()
    
    # 2. ГЕНЕРАЦИЯ АККАУНТА (запись в Google Sheets)
    account_service = get_account_service()
    try:
        account_data = account_service.create_account_from_category(
            base_name=base_name,
            base_addr1=base_addr1,
            base_addr2=base_addr2,
            base_city=base_city,
            base_state=base_state,
            base_zip=base_zip,
            product=product_name,
        )
    except RuntimeError as e:
        await call.message.answer(f"❌ {e}", reply_markup=start_keyboard())
        await call.answer()
        return
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Ошибка при выдаче аккаунта (категории+товар)")
        await call.message.answer(f"❌ Ошибка при выдаче аккаунта: {e}", reply_markup=start_keyboard())
        await call.answer()
        return

    # 3. ГЕНЕРАЦИЯ ССЫЛКИ
    receipt_service = get_receipt_service()
    
    receipt_data = ReceiptData(
        product_name=account_data.product,
        date=account_data.date,
        name=account_data.name,
        address_parts=account_data.address_parts,
    )

    links_text = ""  # Для сборки ссылок
    final_url = ""  # Сохраняем первую успешную ссылку для обновления GS

    shop_emojis = {
        "amazon": "🛍️",
        "bestbuy": "🛒",
    }
    
    for key in ["amazon", "bestbuy"]:
        try:
            url = receipt_service.build_receipt_url(key, receipt_data)
            emoji = shop_emojis.get(key, "🔗")
            links_text += f"\n{emoji} *{key.capitalize()}*:\n<code>{url}</code>\n"
            # Сохраняем первую успешную ссылку (Amazon по умолчанию)
            if not final_url:
                 final_url = url
                 shop_key_for_gs = key
        except ValueError as e:
            emoji = shop_emojis.get(key, "🔗")
            links_text += f"\n{emoji} *{key.capitalize()}*: ❌ Ошибка ({e})\n"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"Неожиданная ошибка при генерации URL квитанции {key}")
            emoji = shop_emojis.get(key, "🔗")
            links_text += f"\n{emoji} *{key.capitalize()}*: ❌ Непредвиденная ошибка\n"

    # 4. ОБНОВЛЕНИЕ КОЛОНКИ ССЫЛКИ В GS (сохраняем первую успешную)
    if final_url:
        account_service.update_receipt_link(account_data.row_idx, final_url, shop_key_for_gs)

    # 5. ОТПРАВКА ДАННЫХ АККАУНТА + ССЫЛКА
    text_resp = (
        f"✅ **Аккаунт для Shokz создан:**\n\n"
        f"№ Заказа: <code>{account_data.order_no}</code>\n"
        f"Имя: <code>{account_data.name}</code>\n"
        f"Email: <code>{account_data.email}</code>\n"
        f"Адрес: <code>{account_data.address}</code>\n"
        f"Телефон: <code>{account_data.phone}</code>\n"
        f"Товар: <code>{account_data.product}</code>\n"
        f"Серийник: <code>{account_data.serial}</code>\n"
        "\n**Причина обращения:**\n" + account_data.issue + "\n\n**Ссылки на квитанции:**" + links_text
    )

    await call.message.answer(text_resp, reply_markup=status_keyboard(account_data.row_idx))
    await call.message.answer("Что дальше?", reply_markup=start_keyboard())
    await call.answer()

