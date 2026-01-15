"""
Точка входа для Telegram бота Shokz.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_TOKEN
from bot.handlers import start, accounts, ebay, status, common

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота."""
    logger.info("Shokz бот запущен.")
    
    # Инициализация бота и диспетчера
    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(accounts.router)
    dp.include_router(ebay.router)
    dp.include_router(status.router)
    dp.include_router(common.router)
    
    # Запуск polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

