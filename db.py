"""
db.py — warstwa bazy danych SQLite.

Zastępuje pliki JSON (users.json, dziennik_*.json) oraz zapis GPS do
współdzielonego jeziora.json. SQLite zapewnia:
  • atomowe transakcje (koniec z uszkodzeniem pliku przy równoczesnym zapisie),
  • bezpieczny dostęp z wielu workerów gunicorna (blokady na poziomie pliku + WAL),
  • izolację danych per-użytkownik (kolumna username).

Używa wbudowanego modułu sqlite3 — bez dodatkowych zależności.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "planer.db")

# Serializuje zapisy w obrębie procesu; SQLite obsługuje synchronizację między
# procesami (workerami) samodzielnie przez blokady plikowe + tryb WAL.
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def get_db():
    """Kontekst transakcji: commit przy sukcesie, rollback przy wyjątku."""
    conn = _connect()
    try:
        with _lock:
            yield conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Tworzy schemat (idempotentnie) i wykonuje jednorazową migrację z JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # WAL ustawiamy poza transakcją kontekstu
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username   TEXT PRIMARY KEY,
                hash       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dziennik (
                id           TEXT PRIMARY KEY,
                username     TEXT NOT NULL,
                data_dodania TEXT NOT NULL,
                dane         TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dziennik_user ON dziennik(username);

            CREATE TABLE IF NOT EXISTS gps_lowiska (
                username   TEXT NOT NULL,
                jezior_id  TEXT NOT NULL,
                lowisko_id TEXT NOT NULL,
                lat        REAL NOT NULL,
                lon        REAL NOT NULL,
                PRIMARY KEY (username, jezior_id, lowisko_id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    _migruj_z_json()


# =====================================================================
# JEDNORAZOWA MIGRACJA Z PLIKÓW JSON
# =====================================================================

def _migruj_z_json() -> None:
    """
    Importuje istniejące users.json i dziennik_*.json do bazy (raz).
    Migracja zachowawcza: tylko gdy tabela jest pusta. Po imporcie pliki
    są przemianowywane na *.imported, żeby nie migrować dwukrotnie.
    """
    # ── users.json ──────────────────────────────────────────────
    users_file = os.path.join(DATA_DIR, "users.json")
    if os.path.exists(users_file):
        try:
            with get_db() as conn:
                pusto = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
                if pusto:
                    with open(users_file, encoding="utf-8") as f:
                        users = json.load(f)
                    teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    for nick, dane in users.items():
                        h = dane.get("hash") if isinstance(dane, dict) else None
                        if h:
                            conn.execute(
                                "INSERT OR IGNORE INTO users (username, hash, created_at) VALUES (?, ?, ?)",
                                (nick.lower(), h, teraz),
                            )
            os.replace(users_file, users_file + ".imported")
        except Exception as e:
            print(f"[db] Migracja users.json pominięta: {e}")

    # ── dziennik_*.json ─────────────────────────────────────────
    try:
        for nazwa in os.listdir(DATA_DIR):
            if not (nazwa.startswith("dziennik_") and nazwa.endswith(".json")):
                continue
            sciezka = os.path.join(DATA_DIR, nazwa)
            nick = nazwa[len("dziennik_"):-len(".json")]
            try:
                with open(sciezka, encoding="utf-8") as f:
                    wpisy = json.load(f).get("wpisy", [])
                with get_db() as conn:
                    juz = conn.execute(
                        "SELECT COUNT(*) AS n FROM dziennik WHERE username = ?", (nick,)
                    ).fetchone()["n"]
                    if juz == 0:
                        # odwróć: w pliku najnowsze są pierwsze, wstawiamy od najstarszych
                        for wpis in reversed(wpisy):
                            wid = wpis.get("id") or os.urandom(4).hex()
                            conn.execute(
                                "INSERT OR IGNORE INTO dziennik (id, username, data_dodania, dane) VALUES (?, ?, ?, ?)",
                                (wid, nick, wpis.get("data_dodania", ""), json.dumps(wpis, ensure_ascii=False)),
                            )
                os.replace(sciezka, sciezka + ".imported")
            except Exception as e:
                print(f"[db] Migracja {nazwa} pominięta: {e}")
    except OSError:
        pass


# =====================================================================
# UŻYTKOWNICY
# =====================================================================

def pobierz_uzytkownika(username: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT username, hash FROM users WHERE username = ?", (username.lower(),)
        ).fetchone()


def utworz_uzytkownika(username: str, hash_: str) -> bool:
    """Zwraca True przy sukcesie, False jeśli nick zajęty."""
    teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, hash, created_at) VALUES (?, ?, ?)",
                (username.lower(), hash_, teraz),
            )
        return True
    except sqlite3.IntegrityError:
        return False


# =====================================================================
# DZIENNIK POŁOWÓW (per-użytkownik)
# =====================================================================

def wpisy_uzytkownika(username: str) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT dane FROM dziennik WHERE username = ? ORDER BY rowid DESC",
            (username.lower(),),
        ).fetchall()
    return [json.loads(r["dane"]) for r in rows]


def dodaj_wpis_db(username: str, wpis: dict) -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO dziennik (id, username, data_dodania, dane) VALUES (?, ?, ?, ?)",
            (wpis["id"], username.lower(), wpis.get("data_dodania", ""),
             json.dumps(wpis, ensure_ascii=False)),
        )
    return wpis


def usun_wpis_db(username: str, wpis_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM dziennik WHERE username = ? AND id = ?",
            (username.lower(), wpis_id),
        )
        return cur.rowcount > 0


# =====================================================================
# GPS ŁOWISK (per-użytkownik — nie dotyka współdzielonego jeziora.json)
# =====================================================================

def zapisz_gps(username: str, jezior_id: str, lowisko_id: str, lat: float, lon: float) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO gps_lowiska (username, jezior_id, lowisko_id, lat, lon)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(username, jezior_id, lowisko_id)
               DO UPDATE SET lat = excluded.lat, lon = excluded.lon""",
            (username.lower(), jezior_id, lowisko_id, round(lat, 6), round(lon, 6)),
        )


def gps_overrides(username: str) -> dict:
    """Zwraca {(jezior_id, lowisko_id): {"lat":.., "lon":..}} dla użytkownika."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT jezior_id, lowisko_id, lat, lon FROM gps_lowiska WHERE username = ?",
            (username.lower(),),
        ).fetchall()
    return {(r["jezior_id"], r["lowisko_id"]): {"lat": r["lat"], "lon": r["lon"]} for r in rows}
