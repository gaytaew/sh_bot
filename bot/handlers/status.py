"""
Обработчики для обновления и просмотра статуса аккаунтов.
"""
from aiogram import Router, types

from bot.keyboards import status_keyboard, start_keyboard
from services.accounts import get_account_service

router = Router()

# Глобальное состояние для ожидания ввода статуса
waiting_for_status_update = set()


@router.callback_query(lambda c: c.data == "mode:update_status")
async def handle_mode_update_status(call: types.CallbackQuery):
    """Обработчик выбора режима обновления статуса."""
    waiting_for_status_update.add(call.from_user.id)
    await call.message.answer("Введи номер аккаунта (SHKZ001) или email.", reply_markup=start_keyboard())
    await call.answer()


@router.message(lambda m: m.from_user and m.from_user.id in waiting_for_status_update and m.text)
async def handle_status_query(message: types.Message):
    """Обработчик запроса статуса по номеру или email."""
    waiting_for_status_update.discard(message.from_user.id)
    query = (message.text or "").strip()

    if not query:
        await message.answer("Пустой ввод. Попробуй ещё раз через «Обновить статус».", reply_markup=start_keyboard())
        return

    account_service = get_account_service()
    row_idx = account_service.find_account_by_email_or_order(query)

    if row_idx is None:
        await message.answer("Аккаунт не найден ни по номеру, ни по email.", reply_markup=start_keyboard())
        return

    account_data = account_service.get_account_data(row_idx)

    text_resp = (
        f"Текущий аккаунт <code>{account_data['order_no'] or '[без номера]'}</code>:\n"
        f"Имя: <code>{account_data['name']}</code>\n"
        f"Email: <code>{account_data['email']}</code>\n"
        f"Адрес: <code>{account_data['address']}</code>\n"
        f"Телефон: <code>{account_data['phone']}</code>\n"
        f"Товар: <code>{account_data['product']}</code>\n"
        f"Серийник: <code>{account_data['serial']}</code>\n"
        f"Текущий статус: {account_data['status'] or '—'}\n\n"
        f"**Причина обращения:**\n{account_data['issue']}"
    )

    await message.answer(text_resp, reply_markup=status_keyboard(row_idx))
    return


@router.callback_query(lambda c: c.data and c.data.startswith("status:"))
async def handle_status_update(call: types.CallbackQuery):
    """Обработчик обновления статуса."""
    _, status_key, row_str = call.data.split(":", 2)
    row_idx = int(row_str)

    mapping = {
        "new": "Новый",
        "in_progress": "Оформлен",
        "approved": "Одобрен",
    }
    status_value = mapping.get(status_key, status_key)

    account_service = get_account_service()
    try:
        account_service.update_status(row_idx, status_value)
        await call.answer("Статус сохранён.")
        await call.message.answer(f"Статус для строки {row_idx} обновлён: {status_value}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Ошибка при обновлении статуса")
        await call.message.answer(f"❌ Ошибка при обновлении статуса: {e}")
        await call.answer()

