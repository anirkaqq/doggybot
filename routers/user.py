import asyncio
import random
import time

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    STAT_MAX,
    get_or_create, get_user,
    add_xp, add_bones, get_bones, spend_bones,
    set_photo, set_owner_title, set_dog_title,
    is_girl, set_girl,

    get_stats, add_stat_point,
    can_open_menu, set_menu_open,

    can_race, set_race,
    can_walk, set_walk,

    can_escape, set_escape, escape_from_owner,

    can_set_snot_user, set_snot_user_ts, get_snot, set_snot, clear_snot,

    set_pending, get_pending, clear_pending,

    create_fight, get_fight, set_fight_status,

    get_top_dogs, get_top_owners,

    race_join, race_participants, race_clear,

    # tame/release
    can_tame_owner, set_tame_owner,
    can_retame, tame_dog, release_dog,

    # discord role
    set_sign,
)

from levels import get_level

router = Router()

MENU_LIFETIME = 180
PENDING_TTL = 120

CASINO_ODDS = {2: 0.45, 3: 0.20, 4: 0.10, 5: 0.05}

# ✅ магазин: стать хозяйкой + одно кастомное имя + роль дискорд
SHOP = {
    "be_girl": ("👑 Стать хозяйкой", 250, "auto_girl"),
    "custom_name": ("✏️ Кастомное имя", 100, "text_name"),
    "custom_discord_role": ("🎭 Кастомная роль Discord", 500, "text_role"),
}


# ===================== HELPERS =====================

def cb_pack(uid: int, action: str, extra: str | None = None) -> str:
    return f"{uid}:{action}" if extra is None else f"{uid}:{action}:{extra}"

def cb_unpack(data: str):
    parts = data.split(":")
    uid = int(parts[0])
    action = parts[1] if len(parts) > 1 else ""
    extra = parts[2] if len(parts) > 2 else None
    return uid, action, extra

async def auto_hide_kb(message: Message):
    await asyncio.sleep(MENU_LIFETIME)
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

def skill_points_available(level: int, speed: int, fangs: int, bite: int) -> int:
    return max(0, (level - 1) - (speed + fangs + bite))

def bar(v: int, mx: int = STAT_MAX, filled: str = "■", empty: str = "□") -> str:
    v = max(0, min(mx, int(v)))
    return filled * v + empty * (mx - v)

def fmt_time_left(sec: int) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}ч {m}м"
    if m > 0:
        return f"{m}м {s}с"
    return f"{s}с"

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None):
    try:
        if getattr(call.message, "photo", None):
            await call.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            pass

def get_dog_display(dog_id: int) -> str:
    dog = get_user(dog_id)
    if not dog:
        return "пёс"
    dog_tg = dog[1]
    dog_custom = (dog[11] or "").strip()
    return dog_custom or f"{dog_tg} пёс"

def owner_has_tamed_dog(owner_id: int):
    """
    Возвращает (dog_id, dog_row) если у хозяйки есть пес И он приручен к ней.
    users columns:
      0 user_id
      1 name
      2 xp
      3 bones
      4 owner_id
      5 dog_id
      6 gender
      7 sign
      8 last_food
      9 owner_title
      10 photo_id
      11 dog_title
      12 is_tamed
      13 last_owner_id
      14 last_escape_ts
    """
    owner = get_user(owner_id)
    if not owner:
        return None, None
    dog_id = owner[5]
    if not dog_id:
        return None, None
    dog = get_user(dog_id)
    if not dog:
        return None, None
    is_tamed = int(dog[12] or 0)
    if is_tamed != 1:
        return None, None
    if int(dog[4] or 0) != owner_id:
        return None, None
    return int(dog_id), dog

def get_effective_stats_for_games(uid: int):
    """
    Для игр:
    - если пёс -> его статы
    - если хозяйка -> статы её прирученного пса (иначе None)
    """
    if not is_girl(uid):
        return get_stats(uid)

    dog_id, _dog = owner_has_tamed_dog(uid)
    if not dog_id:
        return None
    return get_stats(dog_id)

def fight_power_from_stats(fangs: int, bite: int) -> float:
    """
    "Рулетка": шанс победы зависит от клыков и укуса.
    """
    f = max(0, int(fangs))
    b = max(0, int(bite))
    return 1.0 + (f * 0.75) + (b * 0.65)


# ===================== KEYBOARDS =====================

def kb_main(uid: int, user):
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Профиль", callback_data=cb_pack(uid, "m_profile"))

    if user and is_girl(uid):
        kb.button(text="👑 Хозяйка", callback_data=cb_pack(uid, "m_owner"))
    else:
        kb.button(text="👑 Хозяйка", callback_data=cb_pack(uid, "noop_owner"))

    if user and (not is_girl(uid)):
        kb.button(text="🐶 Пёс", callback_data=cb_pack(uid, "m_dog"))
    else:
        kb.button(text="🐶 Пёс", callback_data=cb_pack(uid, "noop_dog"))

    kb.button(text="🎮 Игры", callback_data=cb_pack(uid, "m_games"))
    kb.button(text="🛒 Магазин", callback_data=cb_pack(uid, "m_shop"))
    kb.button(text="🏆 Топ", callback_data=cb_pack(uid, "m_top"))
    kb.button(text="🤧 Сопливый", callback_data=cb_pack(uid, "m_snot"))
    kb.button(text="❌ Выход", callback_data=cb_pack(uid, "exit"))
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()

def kb_profile_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Показать", callback_data=cb_pack(uid, "profile_show"))
    kb.button(text="🧠 Прокачка", callback_data=cb_pack(uid, "skills"))
    kb.button(text="📷 Фото", callback_data=cb_pack(uid, "photo"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(2, 1, 1)
    return kb.as_markup()

def kb_owner_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🪢 Приручить пса", callback_data=cb_pack(uid, "owner_tame"))
    kb.button(text="🔓 Отпустить пса", callback_data=cb_pack(uid, "owner_release"))
    kb.button(text="🍖 Покормить (+5 XP псу +1 🦴)", callback_data=cb_pack(uid, "owner_feed"))
    kb.button(text="❤️ Приласкать (+10 XP псу)", callback_data=cb_pack(uid, "owner_pet"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()

def kb_dog_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🏃 Побег (10% шанс, кража 20% 🦴)", callback_data=cb_pack(uid, "dog_escape"))
    kb.button(text="🚶 Пойти погулять (раз в 6ч)", callback_data=cb_pack(uid, "dog_walk"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def kb_games_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🏁 Гонки (лобби 30 мин)", callback_data=cb_pack(uid, "race"))
    kb.button(text="🎲 Битва на клыках (рулетка)", callback_data=cb_pack(uid, "fight"))
    kb.button(text="🎰 Казино", callback_data=cb_pack(uid, "casino"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()

def kb_top_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="👑 Топ хозяек", callback_data=cb_pack(uid, "topowner"))
    kb.button(text="🐶 Топ псов", callback_data=cb_pack(uid, "topdog"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def kb_snot_menu(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🤧 Поставить", callback_data=cb_pack(uid, "snot_set"))
    kb.button(text="🧼 Снять", callback_data=cb_pack(uid, "snot_clear"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def kb_skills(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Скорость", callback_data=cb_pack(uid, "up", "speed"))
    kb.button(text="➕ Клыки", callback_data=cb_pack(uid, "up", "fangs"))
    kb.button(text="➕ Укус", callback_data=cb_pack(uid, "up", "bite"))
    kb.button(text="⬅ Назад", callback_data=cb_pack(uid, "m_profile"))
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()

def kb_shop(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🦴 Баланс", callback_data=cb_pack(uid, "bal"))
    kb.button(text="👑 Стать хозяйкой — 250 🦴", callback_data=cb_pack(uid, "buy", "be_girl"))
    kb.button(text="✏️ Кастомное имя — 100 🦴", callback_data=cb_pack(uid, "buy", "custom_name"))
    kb.button(text="🎭 Роль Discord — 500 🦴", callback_data=cb_pack(uid, "buy", "custom_discord_role"))
    kb.button(text="⬅ Вернуться в меню", callback_data=cb_pack(uid, "back_main"))
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()

def kb_casino_choose_x(uid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="x2 (45%)", callback_data=cb_pack(uid, "cx", "2"))
    kb.button(text="x3 (20%)", callback_data=cb_pack(uid, "cx", "3"))
    kb.button(text="x4 (10%)", callback_data=cb_pack(uid, "cx", "4"))
    kb.button(text="x5 (5%)", callback_data=cb_pack(uid, "cx", "5"))
    kb.button(text="⬅ Назад", callback_data=cb_pack(uid, "m_games"))
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def kb_casino_bets(uid: int, mult: int):
    kb = InlineKeyboardBuilder()
    for b in (1, 5, 10, 25, 50, 100):
        kb.button(text=f"Ставка {b} 🦴", callback_data=cb_pack(uid, "cb", f"{mult},{b}"))
    kb.button(text="⬅ Назад", callback_data=cb_pack(uid, "casino"))
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()

def kb_fight_request(fight_id: int, target_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"fight:accept:{fight_id}:{target_id}")
    kb.button(text="❌ Отказ", callback_data=f"fight:decline:{fight_id}:{target_id}")
    kb.adjust(2)
    return kb.as_markup()


# ===================== PROFILE RENDER =====================

def build_profile_text(uid: int) -> str:
    user = get_user(uid)
    if not user:
        return "❌ Профиль не найден"

    tg_name = user[1]
    xp = int(user[2] or 0)
    bones = int(user[3] or 0)
    owner_id = user[4]
    dog_id = user[5]

    discord_role = (user[7] or "").strip()
    owner_title = (user[9] or "").strip() or "Хозяйка"
    photo_id = user[10] or ""
    dog_title = (user[11] or "").strip()

    photo_ok = "✅" if photo_id else "❌"

    spd, fng, bit = get_stats(uid)

    # если хозяйка и пес приручен — показываем статы пса
    if is_girl(uid) and dog_id:
        dog = get_user(dog_id)
        if dog and int(dog[12] or 0) == 1 and int(dog[4] or 0) == uid:
            spd, fng, bit = get_stats(dog_id)

    lvl = int(get_level(xp))
    points = skill_points_available(lvl, spd, fng, bit)

    dog_display = dog_title or f"{tg_name} пёс"

    extra = ""
    if is_girl(uid):
        header = f"👑 <b>{owner_title}</b>"
        role_line = "🏷 <b>Роль:</b> хозяйка"
        if dog_id:
            dog = get_user(dog_id)
            if dog:
                dog_name = get_dog_display(dog_id)
                tamed = "✅" if (int(dog[12] or 0) == 1 and int(dog[4] or 0) == uid) else "❌"
                extra = f"🐶 <b>Пёс:</b> {dog_name} | 🪢 {tamed}"
            else:
                extra = "🐶 <b>Пёс:</b> нет"
        else:
            extra = "🐶 <b>Пёс:</b> нет"
    elif owner_id:
        owner = get_user(owner_id)
        owner_name = (owner[9] or "").strip() if owner else ""
        if not owner_name and owner:
            owner_name = owner[1]
        header = f"🐕‍🦺 <b>{dog_display}</b>"
        role_line = "🏷 <b>Роль:</b> домашний"
        extra = f"👑 <b>Хозяйка:</b> {owner_name or 'Хозяйка'}"
    else:
        header = f"🐕 <b>{dog_display}</b>"
        role_line = "🏷 <b>Роль:</b> бродячий"

    role_line2 = f"🎭 <b>Discord роль:</b> {discord_role}" if discord_role else ""

    stat_block = (
        f"🧠 <b>Skill Points:</b> {points}\n\n"
        f"⚡ <b>Скорость</b> {spd}/{STAT_MAX}\n<code>{bar(spd)}</code>\n"
        f"🦷 <b>Клыки</b> {fng}/{STAT_MAX}\n<code>{bar(fng)}</code>\n"
        f"💥 <b>Укус</b> {bit}/{STAT_MAX}\n<code>{bar(bit)}</code>"
    )

    lines = [
        f"🐾 <b>{tg_name}</b>",
        header,
        role_line,
    ]
    if role_line2:
        lines.append(role_line2)
    if extra:
        lines.append(extra)

    lines += [
        "",
        f"📷 <b>Фото:</b> {photo_ok}",
        f"🏆 <b>Уровень:</b> {lvl}",
        f"📊 <b>XP:</b> {xp}",
        f"🦴 <b>Кости:</b> {bones}",
        "",
        stat_block,
    ]
    return "\n".join(lines).strip()

async def edit_profile_menu(bot, chat_id: int, message_id: int, uid: int):
    user = get_user(uid)
    caption = build_profile_text(uid)
    photo_id = user[10] if user else None

    if photo_id:
        media = InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML")
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
            reply_markup=kb_profile_menu(uid),
        )
    else:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=caption,
            reply_markup=kb_profile_menu(uid),
            parse_mode="HTML",
        )


# ===================== MENU =====================

async def send_menu(message: Message):
    uid = message.from_user.id
    name = message.from_user.first_name
    get_or_create(uid, name)
    user = get_user(uid)

    ok, remaining = can_open_menu(uid)
    if not ok:
        await message.answer(f"⏳ Меню можно открыть через {max(1, int(remaining))} сек.")
        return

    set_menu_open(uid)

    msg = await message.answer(
        "🐾 <b>Меню</b>\nВыбирай раздел:",
        reply_markup=kb_main(uid, user),
        parse_mode="HTML",
    )
    asyncio.create_task(auto_hide_kb(msg))

@router.message(CommandStart())
async def start(message: Message):
    await send_menu(message)

@router.message(Command("menu"))
async def menu(message: Message):
    await send_menu(message)


# ===================== CALLBACKS =====================

@router.callback_query(F.data.contains(":"))
async def callbacks(call: CallbackQuery):
    owner_uid, action, extra = cb_unpack(call.data)

    if call.from_user.id != owner_uid:
        await call.answer("Это меню не твоё. Напиши /menu", show_alert=True)
        return

    uid = call.from_user.id
    name = call.from_user.first_name
    get_or_create(uid, name)
    user = get_user(uid)

    if action == "exit":
        try:
            await call.message.delete()
        except Exception:
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await call.answer()
        return

    if action == "back_main":
        await safe_edit(call, "🐾 <b>Меню</b>\nВыбирай раздел:", kb_main(uid, get_user(uid)))
        await call.answer()
        return

    if action == "noop_owner":
        await call.answer("Это меню только для хозяйки.", show_alert=True)
        return

    if action == "noop_dog":
        await call.answer("Это меню только для пса.", show_alert=True)
        return

    if action == "m_profile":
        await safe_edit(call, "👤 <b>Профиль</b>", kb_profile_menu(uid))
        await call.answer()
        return

    if action == "m_owner":
        await safe_edit(call, "👑 <b>Хозяйка</b>", kb_owner_menu(uid))
        await call.answer()
        return

    if action == "m_dog":
        await safe_edit(call, "🐶 <b>Пёс</b>", kb_dog_menu(uid))
        await call.answer()
        return

    if action == "m_games":
        await safe_edit(call, "🎮 <b>Игры</b>", kb_games_menu(uid))
        await call.answer()
        return

    if action == "m_shop":
        await safe_edit(call, "🛒 <b>Магазин</b>\nВалюта: 🦴 кости", kb_shop(uid))
        await call.answer()
        return

    if action == "m_top":
        await safe_edit(call, "🏆 <b>Топ</b>", kb_top_menu(uid))
        await call.answer()
        return

    if action == "m_snot":
        await safe_edit(call, "🤧 <b>Сопливый</b>", kb_snot_menu(uid))
        await call.answer()
        return

    if action == "profile_show":
        await edit_profile_menu(call.bot, call.message.chat.id, call.message.message_id, uid)
        await call.answer()
        return

    if action == "photo":
        meta = f"{call.message.chat.id}:{call.message.message_id}"
        set_pending(uid, "set_photo", meta)
        await safe_edit(call, "📷 <b>Фото профиля</b>\nПришли фото в чат (оно будет удалено).", kb_profile_menu(uid))
        await call.answer()
        return

    if action == "skills":
        await safe_edit(call, "🧠 <b>Прокачка</b>\nНажми, чтобы вложить 1 skill point:", kb_skills(uid))
        await call.answer()
        return

    if action == "up":
        stat = extra or ""
        spd, fng, bit = get_stats(uid)
        lvl = int(get_level(user[2] or 0))
        points = skill_points_available(lvl, spd, fng, bit)
        if points <= 0:
            await call.answer("Нет свободных skill points.", show_alert=True)
            return
        ok = add_stat_point(uid, stat)
        if not ok:
            await call.answer("Лимит 11 или ошибка.", show_alert=True)
            return
        await call.answer("✅ +1")
        await safe_edit(call, "🧠 <b>Прокачка</b>\nНажми, чтобы вложить 1 skill point:", kb_skills(uid))
        return

    # ===================== SHOP =====================

    if action == "bal":
        await call.answer(f"🦴 Баланс: {get_bones(uid)}", show_alert=True)
        return

    if action == "buy":
        item_key = extra or ""
        if item_key not in SHOP:
            await call.answer("Нет такого товара.", show_alert=True)
            return

        title, price, mode = SHOP[item_key]
        if get_bones(uid) < price:
            await call.answer("🦴 Не хватает костей.", show_alert=True)
            return

        spend_bones(uid, price)

        if mode == "auto_girl":
            if is_girl(uid):
                await call.answer("Ты уже хозяйка.", show_alert=True)
                return
            set_girl(uid)
            await safe_edit(call, f"✅ Куплено: <b>{title}</b>\n👑 Теперь ты хозяйка!", kb_shop(uid))
            await call.answer()
            return

        meta = f"{call.message.chat.id}:{call.message.message_id}"

        if mode == "text_name":
            set_pending(uid, "shop_custom_name", meta)
            if is_girl(uid):
                await safe_edit(
                    call,
                    "👑 <b>Кастомное имя</b>\n"
                    "Отправь имя хозяйки (до 30 символов).\n"
                    f"⏳ {PENDING_TTL} сек.",
                    kb_shop(uid),
                )
            else:
                await safe_edit(
                    call,
                    "🐶 <b>Кастомное имя</b>\n"
                    "Отправь <b>одно слово</b> (до 15 символов).\n"
                    "Имя станет: <b>слово пёс</b>.\n"
                    f"⏳ {PENDING_TTL} сек.",
                    kb_shop(uid),
                )
            await call.answer()
            return

        if mode == "text_role":
            set_pending(uid, "shop_discord_role", meta)
            await safe_edit(call,
                            "🎭 <b>Кастомная роль Discord</b>\n"
                            "Отправь текст роли (до 50 символов).\n"
                            f"⏳ {PENDING_TTL} сек.",
                            kb_shop(uid))
            await call.answer()
            return

        await call.answer()
        return

    # ===================== OWNER =====================

    if action == "owner_tame":
        if not call.message.chat or call.message.chat.type == "private":
            await call.answer("Приручение — только в чате. Открой меню в группе.", show_alert=True)
            return

        if not is_girl(uid):
            await call.answer("Только хозяйка.", show_alert=True)
            return

        if user[5]:
            await safe_edit(call, "👑 <b>Хозяйка</b>\n🐶 У тебя уже есть пёс. Сначала отпусти его 🔓", kb_owner_menu(uid))
            await call.answer()
            return

        ok_cd, rem_cd = can_tame_owner(uid)
        if not ok_cd:
            await safe_edit(call, f"👑 <b>Хозяйка</b>\n⏳ Приручить можно через <b>{fmt_time_left(rem_cd)}</b>", kb_owner_menu(uid))
            await call.answer()
            return

        set_pending(uid, "tame_pick", f"{call.message.chat.id}")
        await safe_edit(
            call,
            "👑 <b>Приручение</b>\n"
            "Ответь на сообщение <b>незанятого пса</b> любым текстом.\n"
            f"⏳ Время: {PENDING_TTL} сек.\n"
            "⚠️ Можно приручать <b>раз в сутки</b>.",
            kb_owner_menu(uid),
        )
        await call.answer()
        return

    if action == "owner_release":
        if not is_girl(uid):
            await call.answer("Только хозяйка.", show_alert=True)
            return
        if not user[5]:
            await safe_edit(call, "👑 <b>Хозяйка</b>\n🐶 У тебя нет пса.", kb_owner_menu(uid))
            await call.answer()
            return
        ok = release_dog(uid)
        if not ok:
            await call.answer("Ошибка отпуска.", show_alert=True)
            return
        await safe_edit(call, "👑 <b>Хозяйка</b>\n🔓 Ты отпустила пса. Теперь он бродячий 🐕", kb_owner_menu(uid))
        await call.answer()
        return

    if action == "owner_feed":
        if not is_girl(uid):
            await call.answer("Только хозяйка.", show_alert=True)
            return
        dog_id, _dog = owner_has_tamed_dog(uid)
        if not dog_id:
            await safe_edit(call, "👑 <b>Хозяйка</b>\n🐶 Нет прирученного пса.", kb_owner_menu(uid))
            await call.answer()
            return
        add_xp(dog_id, 5)
        add_bones(dog_id, 1)
        await safe_edit(call, "👑 <b>Хозяйка</b>\n🍖 Ты покормила пса!\n🐶 +<b>5 XP</b> и +<b>1 🦴</b>", kb_owner_menu(uid))
        await call.answer()
        return

    if action == "owner_pet":
        if not is_girl(uid):
            await call.answer("Только хозяйка.", show_alert=True)
            return
        dog_id, _dog = owner_has_tamed_dog(uid)
        if not dog_id:
            await safe_edit(call, "👑 <b>Хозяйка</b>\n🐶 Нет прирученного пса.", kb_owner_menu(uid))
            await call.answer()
            return
        add_xp(dog_id, 10)
        await safe_edit(call, "👑 <b>Хозяйка</b>\n❤️ Ты приласкала пса!\n🐶 +<b>10 XP</b>", kb_owner_menu(uid))
        await call.answer()
        return

    # ===================== DOG =====================

    if action == "dog_escape":
        if is_girl(uid):
            await call.answer("Это для пса.", show_alert=True)
            return

        ok, rem = can_escape(uid)
        if not ok:
            await safe_edit(call, f"🐶 <b>Пёс</b>\n🏃 Побег можно попытаться через <b>{fmt_time_left(rem)}</b>", kb_dog_menu(uid))
            await call.answer()
            return

        set_escape(uid)
        success = random.random() < 0.10
        if not success:
            await safe_edit(call, "🐶 <b>Пёс</b>\n🏃 Ты попытался сбежать... но тебя поймали 😭", kb_dog_menu(uid))
            await call.answer()
            return

        stolen = escape_from_owner(uid)
        add_xp(uid, 5)
        await safe_edit(
            call,
            f"🐶 <b>Пёс</b>\n🏃 <b>Побег удался!</b>\n🦴 Украдено: <b>{stolen}</b>\n📊 +<b>5 XP</b>",
            kb_dog_menu(uid),
        )
        await call.answer()
        return

    if action == "dog_walk":
        if is_girl(uid):
            await call.answer("Это для пса.", show_alert=True)
            return
        ok, rem = can_walk(uid)
        if not ok:
            await safe_edit(call, f"🐶 <b>Пёс</b>\n🚶 Погулять можно через <b>{fmt_time_left(rem)}</b>", kb_dog_menu(uid))
            await call.answer()
            return
        set_walk(uid)
        r = random.random()
        if r < 0.35:
            bones = random.randint(1, 10)
            add_bones(uid, bones)
            text = f"🐶 <b>Пёс</b>\n🚶 Ты нашёл на улице <b>{bones} 🦴</b>!"
        elif r < 0.45:
            text = "🐶 <b>Пёс</b>\n🚶 Ты нашёл <b>тапок</b>... и гордо унёс его 😈"
        else:
            text = "🐶 <b>Пёс</b>\n🚶 Ты погулял... но ничего не нашёл."
        await safe_edit(call, text, kb_dog_menu(uid))
        await call.answer()
        return

    # ===================== GAMES =====================

    if action == "race":
        if not call.message.chat or call.message.chat.type == "private":
            await call.answer("Только в чате.", show_alert=True)
            return

        eff = get_effective_stats_for_games(uid)
        if eff is None:
            await call.answer("Чтобы участвовать, хозяйке нужен прирученный пёс 🪢", show_alert=True)
            return

        ok_cd, rem_cd = can_race(uid)
        if not ok_cd:
            await call.answer(f"Кд: {fmt_time_left(rem_cd)}", show_alert=True)
            return

        chat_id = call.message.chat.id
        spd, _f, _b = eff

        if is_girl(uid):
            dog_id, _ = owner_has_tamed_dog(uid)
            part_name = get_dog_display(dog_id) if dog_id else name
        else:
            part_name = name

        _start_ts, end_ts = race_join(chat_id, uid, part_name, spd)
        parts = race_participants(chat_id)

        now = int(time.time())
        left = end_ts - now

        def _race_chances(participants):
            weights = []
            for (_uid, _name, speed, _ts) in participants:
                s = int(speed or 0)
                w = 10 + (s * 6)
                weights.append(w)
            total = sum(weights) if weights else 1
            chances = []
            for (p, w) in zip(participants, weights):
                puid, pname, pspeed, _ts = p
                chance = (w / total) * 100.0
                chances.append((puid, pname, int(pspeed or 0), chance, w))
            return chances, weights

        if left <= 0:
            if len(parts) < 3:
                race_clear(chat_id)
                await safe_edit(call,
                                "🏁 <b>Гонки</b>\nОкно лобби истекло, но игроков меньше 3. Лобби сброшено.\nНажмите ещё раз, чтобы создать новое.",
                                kb_games_menu(uid))
                await call.answer()
                return

            chances, _ = _race_chances(parts)
            winner = random.choices(chances, weights=[c[4] for c in chances], k=1)[0]
            winner_uid, winner_name, _winner_speed, _winner_chance, _w = winner

            prize = random.randint(5, 15)
            add_bones(winner_uid, prize)
            add_xp(winner_uid, 6)

            for (pu, _pn, _ps, _ts) in parts:
                if pu != winner_uid:
                    add_xp(pu, 2)

            for (pu, _pn, _ps, _ts) in parts:
                set_race(pu)

            text = "🏁 <b>ГОНКИ</b>\n\n"
            text += "📊 <b>Шансы участников:</b>\n"
            for (_pu, pn, ps, ch, _w2) in sorted(chances, key=lambda x: x[3], reverse=True):
                text += f"• <b>{pn}</b> (⚡{ps}) — <b>{ch:.1f}%</b>\n"

            text += f"\n🏆 <b>Победил:</b> {winner_name}\n🦴 <b>Приз:</b> {prize}\n📊 <b>+6 XP</b>"
            race_clear(chat_id)

            await safe_edit(call, text, kb_games_menu(uid))
            await call.answer()
            return

        chances, _ = _race_chances(parts)
        text = "🏁 <b>Гонки (лобби)</b>\n\n"
        text += f"⏳ До старта: <b>{fmt_time_left(left)}</b>\n"
        text += f"👥 Участников: <b>{len(parts)}</b>/3+\n\n"
        text += "📊 <b>Текущие шансы:</b>\n"
        for (_pu, pn, ps, ch, _w2) in sorted(chances, key=lambda x: x[3], reverse=True):
            text += f"• <b>{pn}</b> (⚡{ps}) — <b>{ch:.1f}%</b>\n"
        if len(parts) < 3:
            text += "\n❗ Нужно минимум <b>3</b> игрока."

        await safe_edit(call, text, kb_games_menu(uid))
        await call.answer()
        return

    if action == "fight":
        if not call.message.chat or call.message.chat.type == "private":
            await call.answer("Только в чате.", show_alert=True)
            return

        eff = get_effective_stats_for_games(uid)
        if eff is None:
            await call.answer("Чтобы играть, хозяйке нужен прирученный пёс 🪢", show_alert=True)
            return

        meta = f"{call.message.chat.id}:{call.message.message_id}"
        set_pending(uid, "fight_pick", meta)
        await safe_edit(
            call,
            "🎲 <b>Битва на клыках (рулетка)</b>\n"
            "Ответь на сообщение соперника числом <b>ставки</b> (костей).\n"
            "Пример: <b>10</b>\n"
            "⚠️ Второй должен <b>подтвердить</b> участие.\n"
            f"⏳ Время: {PENDING_TTL} сек.",
            kb_games_menu(uid),
        )
        await call.answer()
        return

    if action == "casino":
        await safe_edit(call, "🎰 <b>Казино</b>\nВыбери множитель:", kb_casino_choose_x(uid))
        await call.answer()
        return

    if action == "cx":
        if not extra or extra not in ("2", "3", "4", "5"):
            await call.answer()
            return
        mult = int(extra)
        await safe_edit(call, f"🎰 <b>Казино</b>\nМножитель: <b>x{mult}</b>\nВыбери ставку:", kb_casino_bets(uid, mult))
        await call.answer()
        return

    if action == "cb":
        if not extra or "," not in extra:
            await call.answer()
            return
        m_s, b_s = extra.split(",", 1)
        if not (m_s.isdigit() and b_s.isdigit()):
            await call.answer()
            return
        mult, bet = int(m_s), int(b_s)
        if mult not in CASINO_ODDS:
            await call.answer()
            return
        if not spend_bones(uid, bet):
            await call.answer("🦴 Не хватает костей.", show_alert=True)
            return

        if random.random() < CASINO_ODDS[mult]:
            win = bet * mult
            add_bones(uid, win)
            text = f"🎰 <b>Казино</b>\n✅ Выигрыш!\n🦴 +<b>{win}</b>"
        else:
            text = f"🎰 <b>Казино</b>\n❌ Проигрыш...\n🦴 -<b>{bet}</b>"
        await safe_edit(call, text, kb_games_menu(uid))
        await call.answer()
        return

    if action == "topdog":
        rows = get_top_dogs(10)
        text = "🐶 <b>ТОП ПСОВ</b>\n\n"
        for i, (_id, n, xp, owner_id, owner_name) in enumerate(rows, 1):
            text += f"{i}. 🐶 <b>{n}</b> — <b>{xp}</b> XP"
            if owner_id:
                text += f" | 👑 {owner_name}"
            text += "\n"
        await safe_edit(call, text, kb_top_menu(uid))
        await call.answer()
        return

    if action == "topowner":
        rows = get_top_owners(10)
        text = "👑 <b>ТОП ХОЗЯЕК</b>\n\n"
        for i, (_id, n, xp, _dogid, dogname) in enumerate(rows, 1):
            text += f"{i}. 👑 <b>{n}</b> — <b>{xp}</b> XP | 🐶 {dogname}\n"
        await safe_edit(call, text, kb_top_menu(uid))
        await call.answer()
        return

    if action == "snot_set":
        if not call.message.chat or call.message.chat.type == "private":
            await call.answer("Только в чате.", show_alert=True)
            return

        ok, rem = can_set_snot_user(uid)
        if not ok:
            await call.answer(f"КД: {fmt_time_left(rem)}", show_alert=True)
            return

        chat_id = call.message.chat.id
        set_pending(uid, "snot_pick", f"{chat_id}")
        await safe_edit(
            call,
            "🤧 <b>Сопливый</b>\n"
            "Ответь на сообщение жертвы <b>любым текстом</b> (2 минуты).\n"
            "⏳ Метка держится <b>30 минут</b>.\n"
            "🕒 КД на постановку: <b>24 часа</b>.",
            kb_snot_menu(uid),
        )
        await call.answer()
        return

    if action == "snot_clear":
        if not call.message.chat or call.message.chat.type == "private":
            await call.answer("Только в чате.", show_alert=True)
            return

        row = get_snot(call.message.chat.id)
        if not row:
            await call.answer("Сопливый не стоит.", show_alert=True)
            return

        marked_id, until_ts, setter_id = int(row[0]), int(row[1] or 0), int(row[2] or 0)

        is_chat_admin = False
        try:
            member = await call.bot.get_chat_member(call.message.chat.id, uid)
            is_chat_admin = member.status in ("administrator", "creator")
        except Exception:
            pass

        if uid != setter_id and not is_chat_admin:
            await call.answer("Снять может тот, кто поставил, или админ чата.", show_alert=True)
            return

        clear_snot(call.message.chat.id)
        await safe_edit(call, "🤧 <b>Сопливый</b>\n🧼 Снято.", kb_snot_menu(uid))
        await call.answer()
        return

    await call.answer()


# ===================== FIGHT ACCEPT/DECLINE =====================

@router.callback_query(F.data.startswith("fight:"))
async def fight_callbacks(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return

    action = parts[1]
    fight_id = int(parts[2])
    target_id = int(parts[3])

    if call.from_user.id != target_id:
        await call.answer("Это не тебе.", show_alert=True)
        return

    fight = get_fight(fight_id)
    if not fight:
        await call.answer("Битва не найдена.", show_alert=True)
        return

    _id, chat_id, challenger_id, challenger_name, t_id, target_name, stake, created_ts, status = fight
    if status != "pending":
        await call.answer("Уже решено.", show_alert=True)
        return

    if action == "decline":
        set_fight_status(fight_id, "declined")
        await call.message.answer(f"❌ {target_name} отказался от поединка.")
        await call.answer()
        return

    if get_bones(challenger_id) < stake or get_bones(target_id) < stake:
        set_fight_status(fight_id, "cancelled")
        await call.message.answer("⚠️ У одного из участников нет костей. Поединок отменён.")
        await call.answer()
        return

    spend_bones(challenger_id, stake)
    spend_bones(target_id, stake)

    c_eff = get_effective_stats_for_games(challenger_id)
    t_eff = get_effective_stats_for_games(target_id)
    if c_eff is None or t_eff is None:
        set_fight_status(fight_id, "cancelled")
        await call.message.answer("⚠️ У одного из участников нет прирученного пса. Поединок отменён.")
        await call.answer()
        return

    _c_spd, c_fng, c_bit = c_eff
    _t_spd, t_fng, t_bit = t_eff

    c_power = fight_power_from_stats(c_fng, c_bit)
    t_power = fight_power_from_stats(t_fng, t_bit)

    win_prob = c_power / (c_power + t_power)

    if random.random() < win_prob:
        winner_id = challenger_id
        winner_name = challenger_name
        loser_name = target_name
    else:
        winner_id = target_id
        winner_name = target_name
        loser_name = challenger_name

    prize = stake * 2
    add_bones(winner_id, prize)
    add_xp(winner_id, 10)
    add_xp(challenger_id, 2)
    add_xp(target_id, 2)

    set_fight_status(fight_id, "done")

    await call.message.answer(
        "🎲 <b>БИТВА НА КЛЫКАХ (РУЛЕТКА)!</b>\n"
        f"🦴 Ставка: <b>{stake}</b>\n\n"
        f"📈 Шанс {challenger_name}: <b>{win_prob*100:.1f}%</b>\n"
        f"📉 Шанс {target_name}: <b>{(1-win_prob)*100:.1f}%</b>\n\n"
        f"🏆 Победил: <b>{winner_name}</b>\n"
        f"💀 Проиграл: <b>{loser_name}</b>\n"
        f"🦴 Приз: <b>{prize}</b>",
        parse_mode="HTML"
    )
    await call.answer()


# ===================== TEXT HANDLER =====================

@router.message()
async def messages(message: Message):
    if message.from_user:
        uid = message.from_user.id
        pend = get_pending(uid)
        if pend:
            action, meta, ts = pend
            if int(time.time()) - int(ts or 0) > PENDING_TTL:
                clear_pending(uid)
            else:
                menu_chat_id = None
                menu_msg_id = None
                if meta and ":" in meta:
                    a, b = meta.split(":", 1)
                    if a.isdigit() and b.isdigit():
                        menu_chat_id = int(a)
                        menu_msg_id = int(b)

                if action == "set_photo":
                    if not message.photo:
                        return
                    file_id = message.photo[-1].file_id
                    set_photo(uid, file_id)
                    clear_pending(uid)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    if menu_chat_id and menu_msg_id:
                        try:
                            await edit_profile_menu(message.bot, menu_chat_id, menu_msg_id, uid)
                        except Exception:
                            pass
                    return

                if action == "shop_custom_name":
                    text = (message.text or "").strip()
                    if not text:
                        return

                    if is_girl(uid):
                        set_owner_title(uid, text[:30])
                    else:
                        word = text.split()[0][:15]
                        set_dog_title(uid, f"{word} пёс")

                    clear_pending(uid)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    if menu_chat_id and menu_msg_id:
                        try:
                            await edit_profile_menu(message.bot, menu_chat_id, menu_msg_id, uid)
                        except Exception:
                            pass
                    return

                if action == "shop_discord_role":
                    text = (message.text or "").strip()
                    if not text:
                        return
                    set_sign(uid, text[:50])
                    clear_pending(uid)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    if menu_chat_id and menu_msg_id:
                        try:
                            await edit_profile_menu(message.bot, menu_chat_id, menu_msg_id, uid)
                        except Exception:
                            pass
                    return

                if action == "tame_pick":
                    if not message.chat or message.chat.type == "private":
                        return
                    if not is_girl(uid):
                        clear_pending(uid)
                        return
                    if not message.reply_to_message or not message.reply_to_message.from_user:
                        return

                    chat_id_needed = int(meta) if meta and meta.isdigit() else None
                    if chat_id_needed and message.chat.id != chat_id_needed:
                        return

                    ok_cd, _rem_cd = can_tame_owner(uid)
                    if not ok_cd:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    me = get_user(uid)
                    if me and me[5]:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    target = message.reply_to_message.from_user
                    dog_id = target.id
                    dog = get_user(dog_id)
                    if not dog:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    if is_girl(dog_id):
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    # пёс должен быть свободен
                    if dog[4] is not None:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    ok_ret, _rem_ret = can_retame(uid, dog_id)
                    if not ok_ret:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    ok = tame_dog(uid, dog_id)
                    if ok:
                        set_tame_owner(uid)

                    clear_pending(uid)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    return

                if action == "snot_pick":
                    if not message.chat or message.chat.type == "private":
                        return
                    if not message.reply_to_message or not message.reply_to_message.from_user:
                        return
                    chat_id_needed = int(meta) if meta and meta.isdigit() else None
                    if chat_id_needed and message.chat.id != chat_id_needed:
                        return

                    ok, _rem = can_set_snot_user(uid)
                    if not ok:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    target = message.reply_to_message.from_user
                    set_snot(message.chat.id, target.id, uid)
                    set_snot_user_ts(uid)
                    clear_pending(uid)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    return

                if action == "fight_pick":
                    if not message.chat or message.chat.type == "private":
                        return
                    if not message.reply_to_message or not message.reply_to_message.from_user:
                        return
                    stake_txt = (message.text or "").strip()
                    if not stake_txt.isdigit():
                        return
                    stake = int(stake_txt)
                    if stake <= 0:
                        return

                    enemy = message.reply_to_message.from_user
                    if enemy.id == uid:
                        return

                    me = get_user(uid)
                    en = get_user(enemy.id)
                    if not me or not en:
                        return

                    if get_effective_stats_for_games(uid) is None:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return
                    if get_effective_stats_for_games(enemy.id) is None:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    if get_bones(uid) < stake or get_bones(enemy.id) < stake:
                        clear_pending(uid)
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

                    fight_id = create_fight(message.chat.id, uid, me[1], enemy.id, enemy.first_name, stake)
                    clear_pending(uid)

                    try:
                        await message.delete()
                    except Exception:
                        pass

                    await message.answer(
                        "🎲 <b>Вызов на битву на клыках!</b>\n"
                        f"🦴 Ставка: <b>{stake}</b>\n\n"
                        f"{enemy.first_name}, подтверждай участие:",
                        reply_markup=kb_fight_request(fight_id, enemy.id),
                        parse_mode="HTML"
                    )
                    return

    # сопливый авто-гав
    if not message.chat or message.chat.type == "private":
        return
    if not message.from_user:
        return

    row = get_snot(message.chat.id)
    if not row:
        return

    marked_id, until_ts, _setter_id = int(row[0]), int(row[1] or 0), int(row[2] or 0)
    if int(time.time()) > until_ts:
        clear_snot(message.chat.id)
        return
    if message.from_user.id == marked_id:
        await message.answer("🤧 гав...")
