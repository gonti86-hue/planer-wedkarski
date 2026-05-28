"""
auth.py — system kont użytkowników (na bazie SQLite, moduł db).
Hasła są hashowane (werkzeug, scrypt). Brak przechowywania haseł jawnie.
"""

import re

from werkzeug.security import check_password_hash, generate_password_hash

import db

# Nick: 3-20 znaków, litery/cyfry/podkreślnik/myślnik
_RE_NICK = re.compile(r"^[a-zA-Z0-9_\-]{3,20}$")

MIN_HASLO = 8


def zarejestruj(username: str, password: str) -> tuple[bool, str | None]:
    """
    Tworzy nowe konto.
    Zwraca (True, None) przy sukcesie lub (False, komunikat_bledu).
    """
    username = (username or "").strip().lower()
    if not _RE_NICK.match(username):
        return False, "Nick: 3–20 znaków, tylko litery, cyfry, _ lub -"
    if len(password or "") < MIN_HASLO:
        return False, f"Hasło musi mieć co najmniej {MIN_HASLO} znaków."

    if not db.utworz_uzytkownika(username, generate_password_hash(password)):
        return False, "Taki nick już istnieje — wybierz inny."
    return True, None


def weryfikuj(username: str, password: str) -> bool:
    """Zwraca True jeśli login i hasło pasują."""
    username = (username or "").strip().lower()
    user = db.pobierz_uzytkownika(username)
    if not user:
        # Wykonaj fikcyjne porównanie, by czas odpowiedzi nie zdradzał istnienia konta
        check_password_hash(
            "scrypt:32768:8:1$x$0000000000000000000000000000000000000000000000000000000000000000",
            password or "",
        )
        return False
    return check_password_hash(user["hash"], password or "")


def user_istnieje(username: str) -> bool:
    return db.pobierz_uzytkownika((username or "").strip().lower()) is not None
