"""
Обработчики команд старта и главного меню.
"""
from aiogram import Router, types
from aiogram.filters import Command

from bot.keyboards import start_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start."""
    await message.answer(
        "Привет! Это бот для выдачи Shokz аккаунтов.\nВыбери режим:",
        reply_markup=start_keyboard(),
    )


@router.callback_query(lambda c: c.data == "back_to_start")
async def handle_back_to_start(call: types.CallbackQuery):
    """Обработчик возврата в главное меню."""
    await call.message.answer("Выбери режим:", reply_markup=start_keyboard())
    await call.answer()

