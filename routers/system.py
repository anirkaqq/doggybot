import time
from collections import defaultdict, deque

from aiogram import Router, F
from aiogram.types import Message

from database import get_or_create, add_xp, get_user
from config import ADMINS

router = Router()

# ================= АНТИ-СПАМ =================
TIME_WINDOW = 5
MAX_MESSAGES = 5
USER_MESSAGES = defaultdict(lambda: deque())


def is_spam(user_id: int) -> bool:
    now = time.time()
    q = USER_MESSAGES[user_id]

    while q and now - q[0] > TIME_WINDOW:
        q.popleft()

    q.append(now)
    return len(q) > MAX_MESSAGES


# ================= XP + АНТИ-СПАМ (НЕ КОМАНДЫ) =================
@router.message(F.text & ~F.text.startswith("/"))
async def system_filter(message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    name = message.from_user.first_name

    # ---------- ЛИЧНЫЕ СООБЩЕНИЯ ----------
    if message.chat.type == "private":
        if user_id not in ADMINS:
            await message.answer(
                "❌ Этот бот работает только в группах.\n"
                "Личные сообщения недоступны."
            )
        return

    # ---------- АНТИ-СПАМ ----------
    if user_id not in ADMINS and is_spam(user_id):
        return

    # ---------- XP ----------
    get_or_create(user_id, name)
    add_xp(user_id, 1)

    user = get_user(user_id)
    owner_id = user[3]

    # XP хозяйке за пса
    if owner_id:
        add_xp(owner_id, 1)


# ================= АВТО-УДАЛЕНИЕ ВСЕХ КОМАНД =================
@router.message(F.text.startswith("/"))
async def auto_delete_all_commands(message: Message):
    # команды в ЛС не трогаем
    if message.chat.type == "private":
        return

    try:
        await message.delete()
    except:
        pass
