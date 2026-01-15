"""
Общие обработчики для всех сообщений.
"""
from aiogram import Router, types

from bot.keyboards import start_keyboard
from bot.handlers.ebay import waiting_for_ebay_users

router = Router()


@router.callback_query(lambda c: c.data == "noop")
async def handle_noop(call: types.CallbackQuery):
    """Обработчик пустого callback."""
    await call.answer()


@router.message()
async def handle_default_message(message: types.Message):
    """Обработчик сообщений по умолчанию."""
    # Если прислали фото, но режим eBay не включён
    if message.photo:
        await message.answer(
            "Если хочешь обработать eBay заказ, сначала выбери режим "
            "'Новый Shokz (eBay скрин)' через /start.",
            reply_markup=start_keyboard()
        )
        return

    # Дефолт
    await message.answer("Используй /start, чтобы выбрать режим.", reply_markup=start_keyboard())

