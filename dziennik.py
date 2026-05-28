"""
dziennik.py — dziennik połowów (per-użytkownik), oparty o SQLite (moduł db).
Publiczne API bez zmian: pobierz_wpisy / dodaj_wpis / usun_wpis / statystyki.
"""

import uuid
from datetime import datetime

import db


def pobierz_wpisy(username: str) -> list:
    """Zwraca wszystkie wpisy użytkownika (najnowsze pierwsze)."""
    return db.wpisy_uzytkownika(username)


def dodaj_wpis(username: str, dane_wpisu: dict) -> dict:
    """Tworzy nowy wpis i zwraca go z nadanym ID."""
    wpis = {
        "id":           str(uuid.uuid4())[:8],
        "data_dodania": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **dane_wpisu,
    }
    return db.dodaj_wpis_db(username, wpis)


def usun_wpis(username: str, wpis_id: str) -> bool:
    """Usuwa wpis o podanym ID. Zwraca True jeśli znaleziono i usunięto."""
    return db.usun_wpis_db(username, wpis_id)


def statystyki(username: str) -> dict:
    """Zwraca podsumowanie dziennika użytkownika."""
    wpisy = pobierz_wpisy(username)
    if not wpisy:
        return {"total": 0, "gatunki": {}, "rekord": None, "sr_dlugosc": None}

    gatunki: dict[str, int] = {}
    dlugosci: list[float]   = []
    rekord: dict | None     = None

    for w in wpisy:
        g  = w.get("gatunek", "Nieznany")
        gatunki[g] = gatunki.get(g, 0) + 1
        dl = w.get("dlugosc_cm")
        if dl:
            try:
                dl_f = float(dl)
            except (TypeError, ValueError):
                continue
            dlugosci.append(dl_f)
            if rekord is None or dl_f > float(rekord.get("dlugosc_cm", 0) or 0):
                rekord = w

    return {
        "total":      len(wpisy),
        "gatunki":    dict(sorted(gatunki.items(), key=lambda x: -x[1])),
        "rekord":     rekord,
        "sr_dlugosc": round(sum(dlugosci) / len(dlugosci), 1) if dlugosci else None,
    }
