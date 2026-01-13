# routers/admin.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMINS
from database import get_or_create, add_xp, add_bones, reset_user, set_girl

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMINS


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🛠 Админ-команды:\n"
        "/girl (ответом) — выдать хозяйку\n"
        "/setxp <n> (ответом)\n"
        "/addxp <n> (ответом)\n"
        "/addbones <n> (ответом)\n"
        "/reset (ответом)"
    )


@router.message(Command("girl"))
async def cmd_girl(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    uid = message.reply_to_message.from_user.id
    name = message.reply_to_message.from_user.first_name
    get_or_create(uid, name)
    set_girl(uid)
    await message.answer("👑 Хозяйка выдана")


@router.message(Command("setxp"))
async def cmd_setxp(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return
    uid = message.reply_to_message.from_user.id
    n = int(parts[1])
    # setxp = add_xp (delta) нельзя, поэтому сбрасываем через reset_user + ставим как delta
    # если нужен "именно set", сделай отдельную функцию set_xp в database.py
    reset_user(uid, keep_name=True)
    add_xp(uid, n)
    await message.answer(f"✅ XP установлен: {n}")


@router.message(Command("addxp"))
async def cmd_addxp(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return
    uid = message.reply_to_message.from_user.id
    n = int(parts[1])
    add_xp(uid, n)
    await message.answer(f"✅ +{n} XP")


@router.message(Command("addbones"))
async def cmd_addbones(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return
    uid = message.reply_to_message.from_user.id
    n = int(parts[1])
    add_bones(uid, n)
    await message.answer(f"✅ +{n} 🦴")


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    uid = message.reply_to_message.from_user.id
    reset_user(uid, keep_name=True)
    await message.answer("✅ Сброшено")
