import asyncio
from aiogram import Bot, Dispatcher

from config import TOKEN
from routers import user, system, admin
from commands import set_commands


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    await set_commands(bot)

    dp.include_router(admin.router)
    dp.include_router(user.router)
    dp.include_router(system.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
