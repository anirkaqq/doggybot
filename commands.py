from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault


async def set_commands(bot: Bot):
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="menu", description="Открыть меню"),
        ],
        scope=BotCommandScopeDefault()
    )
