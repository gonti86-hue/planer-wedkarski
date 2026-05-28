"""
dziennik.py — dziennik połowów (per-użytkownik).
Każdy użytkownik ma osobny plik dziennik_{username}.json.
"""

import json
import os
import uuid
from datetime import datetime

from config import DATA_DIR
_DIR = DATA_DIR


def _sciezka(username: str) -> str:
    """Ścieżka do pliku dziennika dla danego użytkownika."""
    bezpieczny = "".join(c for c in username.lower() if c.isalnum() or c in "_-")
    return os.path.join(_DIR, f"dziennik_{bezpieczny}.json")


def _wczytaj(username: str) -> dict:
    sc = _sciezka(username)
    if not os.path.exists(sc):
        return {"wpisy": []}
    try:
        with open(sc, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"wpisy": []}


def _zapisz(username: str, dane: dict) -> None:
    with open(_sciezka(username), "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)


def pobierz_wpisy(username: str) -> list:
    """Zwraca wszystkie wpisy użytkownika (najnowsze pierwsze)."""
    return _wczytaj(username).get("wpisy", [])


def dodaj_wpis(username: str, dane_wpisu: dict) -> dict:
    """Tworzy nowy wpis i zwraca go z nadanym ID."""
    dane = _wczytaj(username)
    wpis = {
        "id":           str(uuid.uuid4())[:8],
        "data_dodania": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **dane_wpisu,
    }
    dane["wpisy"].insert(0, wpis)
    _zapisz(username, dane)
    return wpis


def usun_wpis(username: str, wpis_id: str) -> bool:
    """Usuwa wpis o podanym ID. Zwraca True jeśli znaleziono i usunięto."""
    dane = _wczytaj(username)
    przed = len(dane["wpisy"])
    dane["wpisy"] = [w for w in dane["wpisy"] if w.get("id") != wpis_id]
    if len(dane["wpisy"]) < przed:
        _zapisz(username, dane)
        return True
    return False


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
            dlugosci.append(float(dl))
            if rekord is None or float(dl) > float(rekord.get("dlugosc_cm", 0)):
                rekord = w

    return {
        "total":      len(wpisy),
        "gatunki":    dict(sorted(gatunki.items(), key=lambda x: -x[1])),
        "rekord":     rekord,
        "sr_dlugosc": round(sum(dlugosci) / len(dlugosci), 1) if dlugosci else None,
    }
