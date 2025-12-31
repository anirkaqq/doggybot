import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()


def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        xp INTEGER DEFAULT 0,
        owner_id INTEGER,
        dog_id INTEGER,
        gender TEXT,
        sign TEXT,
        last_food TEXT
    )
    """)
    conn.commit()

    cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}

    if "owner_id" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN owner_id INTEGER")
    if "dog_id" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN dog_id INTEGER")
    if "gender" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN gender TEXT")
    if "sign" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN sign TEXT")
    if "last_food" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN last_food TEXT")

    conn.commit()


init_db()


# ================= ОСНОВНОЕ =================

def get_or_create(user_id: int, name: str):
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, name, xp) VALUES (?, ?, 0)",
            (user_id, name)
        )
    else:
        cursor.execute(
            "UPDATE users SET name=? WHERE user_id=?",
            (name, user_id)
        )
    conn.commit()


def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()


def add_xp(user_id: int, amount: int):
    cursor.execute(
        "UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id=?",
        (amount, user_id)
    )
    conn.commit()


# ================= ПОДПИСЬ =================

def set_sign(user_id: int, text: str):
    cursor.execute(
        "UPDATE users SET sign=? WHERE user_id=?",
        (text, user_id)
    )
    conn.commit()


# ================= РОЛИ =================

def set_girl(user_id: int):
    cursor.execute(
        "UPDATE users SET gender='girl' WHERE user_id=?",
        (user_id,)
    )
    conn.commit()


def is_girl(user_id: int) -> bool:
    cursor.execute(
        "SELECT gender FROM users WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    return bool(row and row[0] == "girl")


# ================= ПЁС =================

def adopt_dog(owner_id: int, dog_id: int, owner_name: str):
    cursor.execute(
        "UPDATE users SET owner_id=? WHERE user_id=?",
        (owner_id, dog_id)
    )
    cursor.execute(
        "UPDATE users SET dog_id=?, sign=? WHERE user_id=?",
        (dog_id, f"Пёс {owner_name}", owner_id)
    )
    conn.commit()


def release_dog(owner_id: int) -> bool:
    cursor.execute(
        "SELECT dog_id FROM users WHERE user_id=?",
        (owner_id,)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        return False

    dog_id = row[0]

    cursor.execute(
        "UPDATE users SET owner_id=NULL WHERE user_id=?",
        (dog_id,)
    )
    cursor.execute(
        "UPDATE users SET dog_id=NULL, sign=NULL WHERE user_id=?",
        (owner_id,)
    )
    conn.commit()
    return True


# ================= ЕДА =================

def set_last_food(user_id: int, value: str):
    cursor.execute(
        "UPDATE users SET last_food=? WHERE user_id=?",
        (value, user_id)
    )
    conn.commit()


# ================= ТОПЫ =================

def get_top_dogs(limit: int = 10):
    cursor.execute(
        """
        SELECT d.user_id, d.name, d.xp, d.owner_id, COALESCE(o.name, '')
        FROM users d
        LEFT JOIN users o ON d.owner_id = o.user_id
        ORDER BY d.xp DESC
        LIMIT ?
        """,
        (limit,)
    )
    return cursor.fetchall()


def get_top_owners(limit: int = 10):
    cursor.execute(
        """
        SELECT o.user_id, o.name, o.xp, o.dog_id, COALESCE(d.name, '')
        FROM users o
        LEFT JOIN users d ON o.dog_id = d.user_id
        WHERE o.dog_id IS NOT NULL
        ORDER BY o.xp DESC
        LIMIT ?
        """,
        (limit,)
    )
    return cursor.fetchall()
