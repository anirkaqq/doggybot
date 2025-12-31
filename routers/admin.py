from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMINS
from database import get_user, add_xp, set_girl

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMINS


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🛠 Админ-команды:\n"
        "/girl <id>\n"
        "/setxp <n> (ответом)\n"
        "/addxp <n> (ответом)"
    )


@router.message(Command("girl"))
async def girl(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return

    set_girl(int(parts[1]))
    await message.answer("👑 Хозяйка назначена")


@router.message(Command("setxp"))
async def setxp(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        return

    target_id = message.reply_to_message.from_user.id
    value = int(parts[1])

    user = get_user(target_id)
    if not user:
        return

    delta = value - user[2]
    add_xp(target_id, delta)

    await message.answer(f"📊 XP установлено: {value}")


@router.message(Command("addxp"))
async def addxp(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        return

    target_id = message.reply_to_message.from_user.id
    add_xp(target_id, int(parts[1]))

    await message.answer("📈 XP изменено")
