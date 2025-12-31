from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
)


async def set_commands(bot: Bot):
    # очищаем команды для админов
    await bot.delete_my_commands(scope=BotCommandScopeAllChatAdministrators())

    # ===== ВСЕ ОБЫЧНЫЕ КОМАНДЫ (ЧЕРЕЗ ADMIN SCOPE) =====
    await bot.set_my_commands(
        [
            BotCommand(command="me", description="Мой статус"),
            BotCommand(command="mydog", description="Мой пёс"),
            BotCommand(command="adopt", description="Приручить пса (ответом)"),
            BotCommand(command="release", description="Отпустить пса"),
            BotCommand(command="food", description="Покормить пса"),
            BotCommand(command="topdog", description="Топ псов"),
            BotCommand(command="topowner", description="Топ хозяек"),
        ],
        scope=BotCommandScopeAllChatAdministrators()
    )
