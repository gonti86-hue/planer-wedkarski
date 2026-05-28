"""
auth.py — prosty system kont użytkowników.
Przechowuje dane w users.json z zahaszowanymi hasłami (werkzeug).
"""

import json
import os
import re

from werkzeug.security import check_password_hash, generate_password_hash
from config import DATA_DIR

USERS_FILE = os.path.join(DATA_DIR, "users.json")

# Nick: 3-20 znaków, litery/cyfry/podkreślnik/myślnik
_RE_NICK = re.compile(r"^[a-zA-Z0-9_\-]{3,20}$")


def _wczytaj() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _zapisz(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def zarejestruj(username: str, password: str) -> tuple[bool, str | None]:
    """
    Tworzy nowe konto.
    Zwraca (True, None) przy sukcesie lub (False, komunikat_bledu).
    """
    username = username.strip().lower()
    if not _RE_NICK.match(username):
        return False, "Nick: 3–20 znaków, tylko litery, cyfry, _ lub -"
    if len(password) < 4:
        return False, "Hasło musi mieć co najmniej 4 znaki."
    users = _wczytaj()
    if username in users:
        return False, "Taki nick już istnieje — wybierz inny."
    users[username] = {"hash": generate_password_hash(password)}
    _zapisz(users)
    return True, None


def weryfikuj(username: str, password: str) -> bool:
    """Zwraca True jeśli login i hasło pasują."""
    username = username.strip().lower()
    users = _wczytaj()
    user = users.get(username)
    if not user:
        return False
    return check_password_hash(user["hash"], password)


def user_istnieje(username: str) -> bool:
    return username.strip().lower() in _wczytaj()
