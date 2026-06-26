import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.handlers import router
from bot.bulk_handlers import router as bulk_router

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(bulk_router)
    dp.include_router(router)

    print("🤖 Price Monitor Bot started...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())