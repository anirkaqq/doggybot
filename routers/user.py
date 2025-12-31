from datetime import datetime
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database import (
    get_or_create, get_user, add_xp,
    is_girl, adopt_dog, release_dog,
    get_top_dogs, get_top_owners,
    set_sign, set_last_food
)
from levels import STRAY_LEVELS, HOME_LEVELS, get_level

router = Router()


# ================= УТИЛИТЫ =================

def safe_level(levels, lvl: int):
    return levels[lvl] if lvl < len(levels) else levels[-1]


def safe_sign(user, fallback: str):
    return user[6] if user and user[6] else fallback


# ================= ПРОФИЛЬ =================

@router.message(Command("me", ignore_mention=True))
async def me(message: Message):
    uid = message.from_user.id
    name = message.from_user.first_name

    get_or_create(uid, name)
    user = get_user(uid)

    xp, owner_id, dog_id = user[2], user[3], user[4]
    lvl = get_level(xp)

    # 👑 ХОЗЯЙКА
    if dog_id:
        dog = get_user(dog_id)
        await message.answer(
            f"👑 Ты — ХОЗЯЙКА\n"
            f"🐶 Пёс: {dog[1]}\n"
            f"✍ Подпись: {safe_sign(user, f'Пёс {name}')}\n"
            f"📊 XP: {xp}\n"
            f"🏆 Уровень: {lvl}"
        )
        return

    # 🐕‍🦺 ДОМАШНИЙ ПЁС
    if owner_id:
        owner = get_user(owner_id)
        await message.answer(
            f"🐕‍🦺 Домашний пёс\n"
            f"👑 Хозяйка: {owner[1]}\n"
            f"✍ Подпись: {safe_sign(owner, f'Пёс {owner[1]}')}\n"
            f"📊 XP: {xp}\n"
            f"🏆 {lvl} — {safe_level(HOME_LEVELS, lvl)}"
        )
        return

    # 🐕 БРОДЯЧИЙ
    await message.answer(
        f"🐕 Бродячий пёс\n"
        f"📊 XP: {xp}\n"
        f"🏆 {lvl} — {safe_level(STRAY_LEVELS, lvl)}"
    )


# ================= МОЙ ПЁС =================

@router.message(Command("mydog", ignore_mention=True))
async def mydog(message: Message):
    uid = message.from_user.id
    user = get_user(uid)

    if not user or not user[4]:
        await message.answer("❌ У тебя нет пса")
        return

    dog = get_user(user[4])
    if not dog:
        await message.answer("❌ Пёс не найден")
        return

    await message.answer(
        f"🐶 Твой пёс: {dog[1]}\n"
        f"📊 XP: {dog[2]}\n"
        f"🏆 {get_level(dog[2])} — {safe_level(HOME_LEVELS, get_level(dog[2]))}"
    )


# ================= ПОДПИСЬ =================

@router.message(Command("sign", ignore_mention=True))
async def sign(message: Message):
    uid = message.from_user.id
    user = get_user(uid)

    if not user or not user[4]:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        return

    set_sign(uid, parts[1][:50])
    await message.answer("✍ Подпись обновлена")


# ================= ПРИРУЧЕНИЕ =================

@router.message(Command("adopt", ignore_mention=True))
async def adopt(message: Message):
    if not message.reply_to_message:
        await message.answer("❌ Ответь на сообщение пса")
        return

    owner_id = message.from_user.id
    get_or_create(owner_id, message.from_user.first_name)

    if not is_girl(owner_id):
        await message.answer("❌ Только хозяйка может приручать")
        return

    dog_id = message.reply_to_message.from_user.id
    get_or_create(dog_id, message.reply_to_message.from_user.first_name)

    owner = get_user(owner_id)
    dog = get_user(dog_id)

    if owner[4]:
        await message.answer("❌ У тебя уже есть пёс")
        return

    if dog[3]:
        await message.answer("❌ Этот пёс уже домашний")
        return

    adopt_dog(owner_id, dog_id, message.from_user.first_name)
    await message.answer("👑 Пёс приручён")


# ================= ОТПУСТИТЬ =================

@router.message(Command("release", ignore_mention=True))
async def release(message: Message):
    uid = message.from_user.id
    get_or_create(uid, message.from_user.first_name)

    if release_dog(uid):
        await message.answer("💔 Ты отпустила пса")
    else:
        await message.answer("❌ У тебя нет пса")


# ================= ЕДА =================

@router.message(Command("food", ignore_mention=True))
async def food(message: Message):
    uid = message.from_user.id
    name = message.from_user.first_name

    get_or_create(uid, name)
    user = get_user(uid)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if now.hour < 12:
        period = "first"
        period_text = "в первой половине суток"
    else:
        period = "second"
        period_text = "во второй половине суток"

    food_key = f"{today}_{period}"

    if user[7] == food_key:
        await message.answer(f"🐶 Пёс уже кушал {period_text}")
        return

    # 👑 ХОЗЯЙКА
    if user[4]:
        add_xp(user[4], 10)
        set_last_food(uid, food_key)
        await message.answer(f"🦴 Ты покормила пса\n🐶 Пёс кушал {period_text}\n+10 XP")
        return

    # 🐕‍🦺 ДОМАШНИЙ ПЁС — НЕЛЬЗЯ
    if user[3]:
        return

    # 🐕 БРОДЯЧИЙ
    add_xp(uid, 5)
    set_last_food(uid, food_key)
    await message.answer(f"🦴 Бродячий пёс нашёл еду\n🐕 Пёс кушал {period_text}\n+5 XP")


# ================= ТОПЫ =================

@router.message(Command("topdog", ignore_mention=True))
async def topdog(message: Message):
    rows = get_top_dogs(10)
    text = "🐶 ТОП ПСОВ\n\n"

    for i, (_, name, xp, owner_id, owner_name) in enumerate(rows, 1):
        lvl = get_level(xp)
        if owner_id:
            text += f"{i}. 🐕‍🦺 {name} — {xp} XP | {safe_level(HOME_LEVELS, lvl)} | 👑 {owner_name}\n"
        else:
            text += f"{i}. 🐕 {name} — {xp} XP | {safe_level(STRAY_LEVELS, lvl)}\n"

    await message.answer(text)


@router.message(Command("topowner", ignore_mention=True))
async def topowner(message: Message):
    rows = get_top_owners(10)
    text = "👑 ТОП ХОЗЯЕК\n\n"

    for i, (_, name, xp, _, dog) in enumerate(rows, 1):
        text += f"{i}. 👑 {name} — {xp} XP | 🐶 {dog}\n"

    await message.answer(text)
