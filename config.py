"""
config.py — centralna konfiguracja: ścieżki, środowisko, klucze, .env.
Lokalnie: DATA_DIR = katalog aplikacji (domyślnie)
Produkcja (Fly.io): DATA_DIR = /data  (trwały wolumen)
"""

import os
import secrets
from pathlib import Path

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Wszystkie pliki z danymi użytkowników trafiają do DATA_DIR
DATA_DIR = os.environ.get("DATA_DIR", APP_DIR)

# Produkcja = dane trzymane poza katalogiem aplikacji (np. wolumen /data)
IS_PRODUCTION = os.path.abspath(DATA_DIR) != os.path.abspath(APP_DIR)


def zaladuj_env() -> None:
    """
    Wczytuje plik .env z katalogu aplikacji do zmiennych środowiskowych.
    Wywoływane raz przy starcie (zastępuje zduplikowany kod w app.py / ai_ocena_ryby.py).
    """
    env_path = Path(APP_DIR) / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def pobierz_secret_key() -> str:
    """
    Zwraca klucz sesji Flask.
    Kolejność: zmienna SECRET_KEY → trwały plik .secret_key → wygeneruj i zapisz.

    Trwały plik gwarantuje, że WSZYSTKIE workery gunicorna używają tego samego
    klucza i że sesje przeżywają restart (inaczej os.urandom() w każdym workerze
    dałby inny klucz i logowanie padałoby losowo).
    """
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key

    os.makedirs(DATA_DIR, exist_ok=True)
    key_file = os.path.join(DATA_DIR, ".secret_key")
    if os.path.exists(key_file):
        with open(key_file, encoding="utf-8") as f:
            zapisany = f.read().strip()
            if zapisany:
                return zapisany

    nowy = secrets.token_hex(32)
    with open(key_file, "w", encoding="utf-8") as f:
        f.write(nowy)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return nowy
