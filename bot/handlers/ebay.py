"""
Обработчики для работы с eBay скриншотами (OCR + GPT).
"""
import os
import logging
from aiogram import Router, types

from bot.keyboards import status_keyboard, start_keyboard
from services.accounts import get_account_service
from services.receipts import get_receipt_service
from services.ocr_gpt import get_ocr_gpt_service
from services.address import parse_ebay_address
from models import ReceiptData

logger = logging.getLogger(__name__)
router = Router()

# Глобальное состояние для ожидания фото от пользователей
waiting_for_ebay_users = set()


@router.callback_query(lambda c: c.data == "mode:ebay")
async def handle_mode_ebay(call: types.CallbackQuery):
    """Обработчик выбора режима eBay."""
    waiting_for_ebay_users.add(call.from_user.id)
    await call.message.answer(
        "Отправь скриншот заказа eBay одним фото.",
        reply_markup=start_keyboard()
    )
    await call.answer()


@router.message(lambda m: m.from_user and m.from_user.id in waiting_for_ebay_users and m.photo)
async def process_ebay_photo(message: types.Message):
    """
    Обработка скрина заказа eBay: OCR -> GPT -> запись строки -> выдача аккаунта и обеих ссылок.
    """
    local_file = None
    try:
        waiting_for_ebay_users.discard(message.from_user.id)
        
        if not message.photo:
            await message.answer("Пожалуйста, отправь фото заказа eBay.")
            return

        photo = message.photo[-1]
        bot = message.bot
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path
        local_file = f"{photo.file_id}.jpg"
        await bot.download_file(file_path, local_file)
        logger.info(f"Фото скачано: {local_file}")

        # OCR + GPT обработка
        ocr_gpt_service = get_ocr_gpt_service()
        structured = await ocr_gpt_service.process_ebay_photo(local_file)
        
        name = structured.get("Имя", "").strip()
        address_raw = structured.get("Адрес", "").strip()  # Адрес, который вернул GPT
        product = structured.get("Товар", "").strip()

        # Проверка: если товар не найден, сообщаем пользователю
        if not product:
            logger.warning(f"Товар не найден в данных GPT. Структурированные данные: {structured}")
            await message.answer(
                "❌ Не удалось определить товар из скриншота.\n\n"
                "Попробуйте:\n"
                "1. Отправить более четкий скриншот\n"
                "2. Убедитесь, что на скриншоте видно название товара\n"
                "3. Используйте режим 'Новый Shokz (категории)' для ручного выбора товара",
                reply_markup=start_keyboard()
            )
            return

        # Парсинг адреса на компоненты для URL
        address_parts = parse_ebay_address(address_raw)
        
        # Запись в лист eBay_Addresses
        from services.google_sheets import get_sheets_service
        sheets = get_sheets_service()
        sheets.append_ebay_address(
            name=name or "[нет имени]",
            addr1=address_parts.addr1,
            addr2=address_parts.addr2,
            city=address_parts.city,
            state=address_parts.state,
            zip_code=address_parts.zip_code,
            product=product or "[нет товара]",
        )

        # ГЕНЕРАЦИЯ АККАУНТА (запись в Google Sheets)
        account_service = get_account_service()
        try:
            account_data = account_service.create_account_from_ebay(
                name=name,
                address_raw=address_raw,  # Адрес как есть от GPT (БЕЗ искажения)
                product=product,  # Теперь точно не пустая строка
                address_parts=address_parts,
            )
        except RuntimeError as e:
            await message.answer(f"❌ {e}")
            return
        except Exception as e:
            logger.exception("Ошибка при создании аккаунта из eBay")
            await message.answer(f"❌ Ошибка при создании аккаунта: {e}")
            return

        # ГЕНЕРАЦИЯ ССЫЛКИ
        receipt_service = get_receipt_service()
        
        receipt_data = ReceiptData(
            product_name=account_data.product,
            date=account_data.date,
            name=account_data.name,
            address_parts=account_data.address_parts,
        )
        
        links_text = ""
        final_url = ""
        
        shop_emojis = {
            "amazon": "🛍️",
            "bestbuy": "🛒",
        }
        
        for shop_key in ["amazon", "bestbuy"]:
            try:
                url = receipt_service.build_receipt_url(shop_key, receipt_data)
                emoji = shop_emojis.get(shop_key, "🔗")
                links_text += f"\n{emoji} *{shop_key.capitalize()}*:\n<code>{url}</code>\n"
                if not final_url:
                     final_url = url  # Сохраняем первую успешную ссылку
            except ValueError as e:
                emoji = shop_emojis.get(shop_key, "🔗")
                links_text += f"\n{emoji} *{shop_key.capitalize()}*: ❌ Ошибка ({e})\n"
            except Exception as e:
                logger.exception(f"Неожиданная ошибка при генерации URL квитанции {shop_key}")
                emoji = shop_emojis.get(shop_key, "🔗")
                links_text += f"\n{emoji} *{shop_key.capitalize()}*: ❌ Непредвиденная ошибка\n"

        # ОБНОВЛЕНИЕ КОЛОНКИ ССЫЛКИ В GS
        if final_url:
            account_service.update_receipt_link(account_data.row_idx, final_url, "amazon")

        # ОТПРАВКА ДАННЫХ АККАУНТА + ССЫЛКА
        text_resp = (
            f"✅ **Заказ eBay обработан.**\n\n"
            f"Имя: <code>{name or '[имя не найдено]'}</code>\n"
            f"Адрес: <code>{address_raw or '[адрес не найден]'}</code>\n"
            f"Товар: <code>{product or '[товар не найден]'}</code>\n\n"
            f"**Shokz аккаунт:**\n"
            f"Email: <code>{account_data.email}</code>\n"
            f"Телефон: <code>{account_data.phone}</code>\n"
            f"Серийник: <code>{account_data.serial}</code>\n"
            f"Номер заказа: <code>{account_data.order_no}</code>\n"
            "\n**Причина обращения:**\n" + account_data.issue + "\n\n**Ссылки на квитанции:**" + links_text
        )

        await message.answer(text_resp, reply_markup=status_keyboard(account_data.row_idx))
        await message.answer("Что дальше?", reply_markup=start_keyboard())

    except Exception as e:
        logger.exception("Ошибка при обработке eBay скрина")
        await message.answer(f"❌ Ошибка при обработке скрина: {e}")
    finally:
        if local_file and os.path.exists(local_file):
            os.remove(local_file)
            logger.info("Фото удалено после обработки.")

