import sqlite3
import time
from typing import Tuple

DB_PATH = "bot.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# ====== CONSTS ======
STAT_MAX = 11

MENU_CD = 60              # меню раз в минуту
RACE_CD = 6 * 60 * 60     # гонки раз в 6 часов
WALK_CD = 6 * 60 * 60     # прогулка раз в 6 часов
ESCAPE_CD = 48 * 60 * 60  # побег раз в 48 часов

SNOT_COOLDOWN = 24 * 60 * 60  # 24 часа
SNOT_DURATION = 30 * 60       # 30 минут

TAME_COOLDOWN = 24 * 60 * 60     # хозяйка может приручать раз в сутки
RETAME_COOLDOWN = 24 * 60 * 60   # бывшая хозяйка может вернуть сбежавшего пса через сутки

MSG_XP_CD = 2  # ✅ XP за сообщение раз в 2 секунды

PENDING_DEFAULT_TTL = 120     # 2 минуты


# ===================== INIT / MIGRATIONS =====================

def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id     INTEGER PRIMARY KEY,
        name        TEXT,
        xp          INTEGER DEFAULT 0,
        bones       INTEGER DEFAULT 0,

        owner_id    INTEGER,
        dog_id      INTEGER,

        gender      TEXT,          -- 'girl' для хозяйки
        sign        TEXT,          -- "кастомная роль discord"
        last_food   INTEGER DEFAULT 0,

        owner_title TEXT,          -- кастомное имя хозяйки
        photo_id    TEXT,          -- file_id телеги
        dog_title   TEXT,          -- кастомное имя пса

        is_tamed        INTEGER DEFAULT 0,  -- 1 если приручен
        last_owner_id   INTEGER,            -- последняя хозяйка
        last_escape_ts  INTEGER             -- время последнего побега
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        speed   INTEGER DEFAULT 0,
        fangs   INTEGER DEFAULT 0,
        bite    INTEGER DEFAULT 0
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_cooldowns (
        user_id     INTEGER PRIMARY KEY,
        last_menu   INTEGER DEFAULT 0,
        last_race   INTEGER DEFAULT 0,
        last_walk   INTEGER DEFAULT 0,
        last_escape INTEGER DEFAULT 0,
        last_snot   INTEGER DEFAULT 0,
        last_tame   INTEGER DEFAULT 0,
        last_msg_xp INTEGER DEFAULT 0
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_actions (
        user_id INTEGER PRIMARY KEY,
        action  TEXT,
        meta    TEXT,
        ts      INTEGER
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS snot_marks (
        chat_id   INTEGER PRIMARY KEY,
        marked_id INTEGER,
        until_ts  INTEGER,
        setter_id INTEGER
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fights (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id         INTEGER,
        challenger_id   INTEGER,
        challenger_name TEXT,
        target_id       INTEGER,
        target_name     TEXT,
        stake           INTEGER,
        created_ts      INTEGER,
        status          TEXT
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS race_lobby (
        chat_id INTEGER PRIMARY KEY,
        end_ts  INTEGER
    )
    """)
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS race_participants (
        chat_id   INTEGER,
        user_id   INTEGER,
        name      TEXT,
        speed     INTEGER,
        joined_ts INTEGER,
        PRIMARY KEY(chat_id, user_id)
    )
    """)
    conn.commit()

    # ---- MIGRATIONS users (на случай старой бд) ----
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}

    def add_col(col_sql: str):
        cursor.execute(col_sql)
        conn.commit()

    if "bones" not in cols:
        add_col("ALTER TABLE users ADD COLUMN bones INTEGER DEFAULT 0")
    if "owner_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN owner_id INTEGER")
    if "dog_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN dog_id INTEGER")
    if "gender" not in cols:
        add_col("ALTER TABLE users ADD COLUMN gender TEXT")
    if "sign" not in cols:
        add_col("ALTER TABLE users ADD COLUMN sign TEXT")
    if "last_food" not in cols:
        add_col("ALTER TABLE users ADD COLUMN last_food INTEGER DEFAULT 0")
    if "owner_title" not in cols:
        add_col("ALTER TABLE users ADD COLUMN owner_title TEXT")
    if "photo_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN photo_id TEXT")
    if "dog_title" not in cols:
        add_col("ALTER TABLE users ADD COLUMN dog_title TEXT")

    if "is_tamed" not in cols:
        add_col("ALTER TABLE users ADD COLUMN is_tamed INTEGER DEFAULT 0")
    if "last_owner_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN last_owner_id INTEGER")
    if "last_escape_ts" not in cols:
        add_col("ALTER TABLE users ADD COLUMN last_escape_ts INTEGER")

    # ---- MIGRATIONS user_cooldowns ----
    cols_cd = {row[1] for row in cursor.execute("PRAGMA table_info(user_cooldowns)").fetchall()}
    if "last_snot" not in cols_cd:
        add_col("ALTER TABLE user_cooldowns ADD COLUMN last_snot INTEGER DEFAULT 0")
    if "last_tame" not in cols_cd:
        add_col("ALTER TABLE user_cooldowns ADD COLUMN last_tame INTEGER DEFAULT 0")
    if "last_msg_xp" not in cols_cd:
        add_col("ALTER TABLE user_cooldowns ADD COLUMN last_msg_xp INTEGER DEFAULT 0")

init_db()


# ===================== USERS =====================

def get_or_create(user_id: int, name: str):
    cursor.execute("INSERT OR IGNORE INTO users(user_id, name) VALUES(?,?)", (user_id, name))
    conn.commit()

    cursor.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
    conn.commit()

    cursor.execute("INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)", (user_id,))
    conn.commit()
    cursor.execute("INSERT OR IGNORE INTO user_cooldowns(user_id) VALUES(?)", (user_id,))
    conn.commit()

def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def add_xp(user_id: int, amount: int):
    cursor.execute("UPDATE users SET xp = COALESCE(xp,0) + ? WHERE user_id=?", (int(amount), user_id))
    conn.commit()

def add_bones(user_id: int, amount: int):
    cursor.execute("UPDATE users SET bones = COALESCE(bones,0) + ? WHERE user_id=?", (int(amount), user_id))
    conn.commit()

def get_bones(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(bones,0) FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0

def spend_bones(user_id: int, amount: int) -> bool:
    amount = int(amount)
    bal = get_bones(user_id)
    if bal < amount:
        return False
    cursor.execute("UPDATE users SET bones = COALESCE(bones,0) - ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    return True

def set_photo(user_id: int, file_id: str):
    cursor.execute("UPDATE users SET photo_id=? WHERE user_id=?", (file_id, user_id))
    conn.commit()

def set_owner_title(user_id: int, title: str):
    cursor.execute("UPDATE users SET owner_title=? WHERE user_id=?", (title[:30], user_id))
    conn.commit()

def set_dog_title(user_id: int, title: str):
    cursor.execute("UPDATE users SET dog_title=? WHERE user_id=?", (title[:25], user_id))
    conn.commit()

def set_sign(user_id: int, text: str):
    cursor.execute("UPDATE users SET sign=? WHERE user_id=?", (text[:50], user_id))
    conn.commit()

def is_girl(user_id: int) -> bool:
    cursor.execute("SELECT gender FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return bool(row and row[0] == "girl")

def set_girl(user_id: int):
    cursor.execute("UPDATE users SET gender='girl' WHERE user_id=?", (user_id,))
    conn.commit()


# ===================== STATS =====================

def get_stats(user_id: int) -> Tuple[int, int, int]:
    cursor.execute("SELECT speed, fangs, bite FROM user_stats WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return (0, 0, 0)
    return (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0))

def add_stat_point(user_id: int, stat: str) -> bool:
    if stat not in ("speed", "fangs", "bite"):
        return False
    spd, fng, bit = get_stats(user_id)
    current = {"speed": spd, "fangs": fng, "bite": bit}[stat]
    if current >= STAT_MAX:
        return False
    cursor.execute(f"UPDATE user_stats SET {stat} = COALESCE({stat},0) + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    return True


# ===================== COOLDOWNS =====================

def _get_cd(user_id: int):
    cursor.execute("""
        SELECT last_menu, last_race, last_walk, last_escape, last_snot, last_tame, last_msg_xp
        FROM user_cooldowns
        WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT OR IGNORE INTO user_cooldowns(user_id) VALUES(?)", (user_id,))
        conn.commit()
        return (0, 0, 0, 0, 0, 0, 0)
    return tuple(int(x or 0) for x in row)

def can_open_menu(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    last_menu, *_ = _get_cd(user_id)
    if now - last_menu < MENU_CD:
        return False, MENU_CD - (now - last_menu)
    return True, 0

def set_menu_open(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_menu=? WHERE user_id=?", (now, user_id))
    conn.commit()

def can_race(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    _, last_race, *_ = _get_cd(user_id)
    if now - last_race < RACE_CD:
        return False, RACE_CD - (now - last_race)
    return True, 0

def set_race(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_race=? WHERE user_id=?", (now, user_id))
    conn.commit()

def can_walk(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    _, _, last_walk, *_ = _get_cd(user_id)
    if now - last_walk < WALK_CD:
        return False, WALK_CD - (now - last_walk)
    return True, 0

def set_walk(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_walk=? WHERE user_id=?", (now, user_id))
    conn.commit()

def can_escape(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    _, _, _, last_escape, *_ = _get_cd(user_id)
    if now - last_escape < ESCAPE_CD:
        return False, ESCAPE_CD - (now - last_escape)
    return True, 0

def set_escape(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_escape=? WHERE user_id=?", (now, user_id))
    conn.commit()

def can_tame_owner(owner_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    *_, last_tame, _last_msg_xp = _get_cd(owner_id)
    if now - last_tame < TAME_COOLDOWN:
        return False, TAME_COOLDOWN - (now - last_tame)
    return True, 0

def set_tame_owner(owner_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_tame=? WHERE user_id=?", (now, owner_id))
    conn.commit()

# ✅ XP за сообщения
def can_msg_xp(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    *_, last_msg_xp = _get_cd(user_id)
    if now - last_msg_xp < MSG_XP_CD:
        return False, MSG_XP_CD - (now - last_msg_xp)
    return True, 0

def set_msg_xp(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_msg_xp=? WHERE user_id=?", (now, user_id))
    conn.commit()


# ===================== TAME / RELEASE =====================

def can_retame(owner_id: int, dog_id: int) -> Tuple[bool, int]:
    cursor.execute("SELECT last_owner_id, COALESCE(last_escape_ts,0) FROM users WHERE user_id=?", (dog_id,))
    row = cursor.fetchone()
    if not row:
        return False, RETAME_COOLDOWN

    last_owner_id = int(row[0] or 0)
    last_escape_ts = int(row[1] or 0)

    if last_escape_ts <= 0:
        return True, 0

    if last_owner_id != owner_id:
        return False, RETAME_COOLDOWN

    now = int(time.time())
    passed = now - last_escape_ts
    if passed >= RETAME_COOLDOWN:
        return True, 0
    return False, RETAME_COOLDOWN - passed

def tame_dog(owner_id: int, dog_id: int) -> bool:
    owner = get_user(owner_id)
    dog = get_user(dog_id)
    if not owner or not dog:
        return False

    if owner[5]:
        return False
    if dog[4]:
        return False

    cursor.execute("UPDATE users SET dog_id=? WHERE user_id=?", (dog_id, owner_id))
    cursor.execute("""
        UPDATE users
        SET owner_id=?,
            is_tamed=1,
            last_owner_id=?,
            last_escape_ts=NULL
        WHERE user_id=?
    """, (owner_id, owner_id, dog_id))
    conn.commit()
    return True

def release_dog(owner_id: int) -> bool:
    owner = get_user(owner_id)
    if not owner:
        return False
    dog_id = owner[5]
    if not dog_id:
        return False

    cursor.execute("UPDATE users SET dog_id=NULL WHERE user_id=?", (owner_id,))
    cursor.execute("""
        UPDATE users
        SET owner_id=NULL,
            is_tamed=0,
            last_owner_id=?
        WHERE user_id=?
    """, (owner_id, dog_id))
    conn.commit()
    return True


# ===================== ESCAPE FROM OWNER =====================

def escape_from_owner(dog_id: int) -> int:
    dog = get_user(dog_id)
    if not dog:
        return 0
    owner_id = dog[4]
    if not owner_id:
        return 0

    owner_bones = get_bones(owner_id)
    stolen = int(owner_bones * 0.20)

    if stolen > 0:
        cursor.execute("UPDATE users SET bones = COALESCE(bones,0) - ? WHERE user_id=?", (stolen, owner_id))
        cursor.execute("UPDATE users SET bones = COALESCE(bones,0) + ? WHERE user_id=?", (stolen, dog_id))

    now = int(time.time())
    cursor.execute("""
        UPDATE users
        SET is_tamed=0,
            last_owner_id=?,
            last_escape_ts=?
        WHERE user_id=?
    """, (owner_id, now, dog_id))

    cursor.execute("UPDATE users SET dog_id=NULL WHERE user_id=?", (owner_id,))
    cursor.execute("UPDATE users SET owner_id=NULL WHERE user_id=?", (dog_id,))
    conn.commit()
    return stolen


# ===================== SNOT =====================

def can_set_snot_user(user_id: int) -> Tuple[bool, int]:
    now = int(time.time())
    _, _, _, _, last_snot, _, _ = _get_cd(user_id)
    if now - last_snot < SNOT_COOLDOWN:
        return False, SNOT_COOLDOWN - (now - last_snot)
    return True, 0

def set_snot_user_ts(user_id: int):
    now = int(time.time())
    cursor.execute("UPDATE user_cooldowns SET last_snot=? WHERE user_id=?", (now, user_id))
    conn.commit()

def get_snot(chat_id: int):
    cursor.execute("SELECT marked_id, until_ts, setter_id FROM snot_marks WHERE chat_id=?", (chat_id,))
    return cursor.fetchone()

def set_snot(chat_id: int, marked_id: int, setter_id: int):
    now = int(time.time())
    until_ts = now + SNOT_DURATION
    cursor.execute("""
        INSERT INTO snot_marks(chat_id, marked_id, until_ts, setter_id)
        VALUES(?,?,?,?)
        ON CONFLICT(chat_id) DO UPDATE SET
            marked_id=excluded.marked_id,
            until_ts=excluded.until_ts,
            setter_id=excluded.setter_id
    """, (chat_id, marked_id, until_ts, setter_id))
    conn.commit()

def clear_snot(chat_id: int):
    cursor.execute("DELETE FROM snot_marks WHERE chat_id=?", (chat_id,))
    conn.commit()


# ===================== PENDING =====================

def set_pending(user_id: int, action: str, meta: str = ""):
    cursor.execute("""
        INSERT INTO pending_actions(user_id, action, meta, ts)
        VALUES(?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            action=excluded.action,
            meta=excluded.meta,
            ts=excluded.ts
    """, (user_id, action, meta, int(time.time())))
    conn.commit()

def get_pending(user_id: int):
    cursor.execute("SELECT action, meta, ts FROM pending_actions WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def clear_pending(user_id: int):
    cursor.execute("DELETE FROM pending_actions WHERE user_id=?", (user_id,))
    conn.commit()


# ===================== FIGHTS =====================

def create_fight(chat_id: int, challenger_id: int, challenger_name: str,
                 target_id: int, target_name: str, stake: int) -> int:
    cursor.execute("""
        INSERT INTO fights(chat_id, challenger_id, challenger_name, target_id, target_name, stake, created_ts, status)
        VALUES(?,?,?,?,?,?,?,?)
    """, (chat_id, challenger_id, challenger_name, target_id, target_name, int(stake), int(time.time()), "pending"))
    conn.commit()
    return cursor.lastrowid

def get_fight(fight_id: int):
    cursor.execute("SELECT * FROM fights WHERE id=?", (fight_id,))
    return cursor.fetchone()

def set_fight_status(fight_id: int, status: str):
    cursor.execute("UPDATE fights SET status=? WHERE id=?", (status, fight_id))
    conn.commit()


# ===================== RACE LOBBY =====================

def race_join(chat_id: int, user_id: int, name: str, speed: int):
    now = int(time.time())

    cursor.execute("SELECT end_ts FROM race_lobby WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    end_ts = int(row[0]) if row else 0

    if end_ts <= now:
        end_ts = now + 30 * 60
        cursor.execute("""
            INSERT INTO race_lobby(chat_id, end_ts)
            VALUES(?,?)
            ON CONFLICT(chat_id) DO UPDATE SET end_ts=excluded.end_ts
        """, (chat_id, end_ts))
        conn.commit()

    cursor.execute("""
        INSERT INTO race_participants(chat_id, user_id, name, speed, joined_ts)
        VALUES(?,?,?,?,?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            name=excluded.name,
            speed=excluded.speed,
            joined_ts=excluded.joined_ts
    """, (chat_id, user_id, name, int(speed), now))
    conn.commit()

    return now, end_ts

def race_participants(chat_id: int):
    cursor.execute("""
        SELECT user_id, name, speed, joined_ts
        FROM race_participants
        WHERE chat_id=?
        ORDER BY joined_ts ASC
    """, (chat_id,))
    return cursor.fetchall()

def race_clear(chat_id: int):
    cursor.execute("DELETE FROM race_participants WHERE chat_id=?", (chat_id,))
    cursor.execute("DELETE FROM race_lobby WHERE chat_id=?", (chat_id,))
    conn.commit()


# ===================== TOPS =====================

def get_top_dogs(limit: int = 10):
    cursor.execute("""
        SELECT u.user_id, u.name, COALESCE(u.xp,0) AS xp,
               u.owner_id
        FROM users u
        WHERE (u.gender IS NULL OR u.gender != 'girl')
        ORDER BY xp DESC
        LIMIT ?
    """, (int(limit),))
    rows = cursor.fetchall()

    out = []
    for (uid, name, xp, owner_id) in rows:
        owner_name = ""
        if owner_id:
            cursor.execute("SELECT COALESCE(owner_title, name) FROM users WHERE user_id=?", (owner_id,))
            r = cursor.fetchone()
            if r:
                owner_name = (r[0] or "")
        out.append((uid, name, int(xp), owner_id, owner_name))
    return out

def get_top_owners(limit: int = 10):
    cursor.execute("""
        SELECT u.user_id, COALESCE(u.owner_title, u.name) AS nm, COALESCE(u.xp,0) AS xp,
               u.dog_id,
               (SELECT u2.dog_title FROM users u2 WHERE u2.user_id=u.dog_id) AS dogtitle,
               (SELECT u2.name FROM users u2 WHERE u2.user_id=u.dog_id) AS dogtg
        FROM users u
        WHERE u.gender='girl'
        ORDER BY xp DESC
        LIMIT ?
    """, (int(limit),))
    rows = cursor.fetchall()
    out = []
    for (uid, nm, xp, dog_id, dogtitle, dogtg) in rows:
        dogname = (dogtitle or "").strip() or (f"{dogtg} пёс" if dogtg else "нет")
        out.append((uid, nm, int(xp), dog_id, dogname))
    return out
