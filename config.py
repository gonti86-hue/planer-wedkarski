"""
config.py — centralna konfiguracja ścieżek.
Lokalnie: DATA_DIR = katalog aplikacji (domyślnie)
Produkcja (Fly.io): DATA_DIR = /data  (trwały wolumen)
"""

import os

APP_DIR  = os.path.dirname(os.path.abspath(__file__))

# Wszystkie pliki z danymi użytkowników trafiają do DATA_DIR
DATA_DIR = os.environ.get("DATA_DIR", APP_DIR)
