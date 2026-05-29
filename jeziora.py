"""
jeziora.py — moduł danych o jeziorach.
Wczytuje dane z jeziora.json i opcjonalnie punkty GPS z pliku GPX.
"""

import json
import os
import xml.etree.ElementTree as ET
from typing import Optional


from config import APP_DIR

# jeziora.json jest TYLKO-DO-ODCZYTU (pozycje GPS użytkownika trzymane są w SQLite),
# więc czytamy wprost wersję z repozytorium — każdy deploy aktualizuje dane gatunków.
SCIEZKA_JSON = os.path.join(APP_DIR, "jeziora.json")

# === Cache JSON — nie czytamy pliku przy każdym zapytaniu (fix: backend dev) ===
_cache_dane: dict | None = None
_cache_mtime: float = 0.0


def wczytaj_jeziora() -> dict:
    """Wczytuje dane jezior z pliku JSON (cache'owane wg mtime pliku)."""
    global _cache_dane, _cache_mtime
    try:
        mtime = os.path.getmtime(SCIEZKA_JSON)
        if _cache_dane is None or mtime > _cache_mtime:
            with open(SCIEZKA_JSON, "r", encoding="utf-8") as f:
                _cache_dane = json.load(f)
            _cache_mtime = mtime
        return _cache_dane
    except FileNotFoundError:
        raise RuntimeError("Nie znaleziono pliku jeziora.json — sprawdź ścieżkę instalacji.")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Błąd składni w jeziora.json: {e}")


def pobierz_jezioro(jeziorka_data: dict, jezior_id: str) -> Optional[dict]:
    """Zwraca dane konkretnego jeziora po jego ID."""
    for j in jeziorka_data.get("jeziora", []):
        if j["id"] == jezior_id:
            return j
    return None


def wczytaj_punkty_gpx(sciezka_gpx: str) -> list[dict]:
    """
    Parsuje plik GPX i zwraca listę punktów waypoint jako słowniki.
    Format: [{"nazwa": "...", "lat": ..., "lon": ..., "opis": "..."}]
    Limit: maks. 500 punktów (ochrona przed nadmiernie dużymi plikami).
    """
    punkty = []
    try:
        # Security: wyłącz external entity processing (fix: security expert)
        parser = ET.XMLParser()
        tree = ET.parse(sciezka_gpx, parser=parser)
        root = tree.getroot()
        # Obsługa przestrzeni nazw GPX 1.0 i 1.1
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        for wpt in root.findall(f"{ns}wpt")[:500]:  # limit bezpieczeństwa
            lat = float(wpt.get("lat", 0))
            lon = float(wpt.get("lon", 0))
            nazwa_el = wpt.find(f"{ns}name")
            opis_el = wpt.find(f"{ns}desc")
            punkty.append({
                "nazwa": nazwa_el.text if nazwa_el is not None else "Bez nazwy",
                "lat": lat,
                "lon": lon,
                "opis": opis_el.text if opis_el is not None else "",
                "zrodlo": "GPX"
            })
    except ET.ParseError as e:
        raise ValueError(f"Błąd parsowania pliku GPX: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Nie znaleziono pliku GPX: {sciezka_gpx}")
    return punkty


def polacz_punkty_z_gpx(jezioro: dict, punkty_gpx: list[dict]) -> dict:
    """
    Dołącza punkty z pliku GPX do listy łowisk jeziora.
    Nie nadpisuje istniejących placeholderów — dodaje jako nowe.
    """
    import copy
    jezioro_kopia = copy.deepcopy(jezioro)
    for i, punkt in enumerate(punkty_gpx):
        nowe_lowisko = {
            "id": f"GPX_{i+1}",
            "nazwa": punkt["nazwa"],
            "opis": punkt.get("opis", "Punkt z pliku GPX"),
            "gps": {"lat": punkt["lat"], "lon": punkt["lon"], "placeholder": False},
            "glebokosc_m": [0, 0],
            "gatunki": []
        }
        jezioro_kopia["lowiska"].append(nowe_lowisko)
    return jezioro_kopia


def istnieje_lowisko(jezior_id: str, lowisko_id: str) -> bool:
    """Sprawdza, czy dane łowisko istnieje w (współdzielonych) danych jezior."""
    jezioro = pobierz_jezioro(wczytaj_jeziora(), jezior_id)
    if not jezioro:
        return False
    return any(l.get("id") == lowisko_id for l in jezioro.get("lowiska", []))


def zastosuj_gps_uzytkownika(jezioro: dict, overrides: dict) -> dict:
    """
    Nakłada prywatne pozycje GPS użytkownika na (współdzielone, tylko-do-odczytu)
    dane jeziora. Zwraca KOPIĘ — nigdy nie modyfikuje współdzielonego cache'u.

    overrides: {(jezior_id, lowisko_id): {"lat":.., "lon":..}}
    """
    import copy
    if not overrides:
        return jezioro
    jez = copy.deepcopy(jezioro)
    jid = jez.get("id")
    for low in jez.get("lowiska", []):
        ov = overrides.get((jid, low.get("id")))
        if ov:
            low["gps"] = {"lat": ov["lat"], "lon": ov["lon"], "placeholder": False}
    return jez


def gatunek_sezonowy(jezioro: dict, miesiac: int) -> list[dict]:
    """Zwraca listę gatunków aktywnych w danym miesiącu."""
    return [
        g for g in jezioro.get("gatunki", [])
        if miesiac in g.get("sezon", [])
    ]


def najlepsze_lowiska(jezioro: dict, gatunek_nazwa: str) -> list[dict]:
    """Zwraca łowiska rekomendowane dla danego gatunku."""
    return [
        l for l in jezioro.get("lowiska", [])
        if gatunek_nazwa in l.get("gatunki", [])
    ]
