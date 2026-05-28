"""
pogoda.py — moduł pobierania danych pogodowych z Open-Meteo API.
Darmowe API, nie wymaga klucza. Pobiera dane historyczne + prognozę.
"""

import requests
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


# Open-Meteo zwraca godziny w tej strefie (parametr "timezone" w zapytaniu).
# Porównujemy bieżący czas w TEJ SAMEJ strefie — inaczej na serwerze w UTC
# (Fly.io) „aktualna" pogoda była przesunięta o offset strefy.
STREFA = ZoneInfo("Europe/Warsaw")

TIMEOUT_S = 10
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def pobierz_pogode(lat: float, lon: float) -> Optional[dict]:
    """
    Pobiera dane pogodowe dla podanych współrzędnych.
    Zwraca słownik z przetworzonymi danymi lub None przy błędzie.
    Dane: temperatura, wiatr, ciśnienie (48h historii + 24h prognozy), zachmurzenie, opady.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "temperature_2m",
            "precipitation",
            "cloudcover",
            "windspeed_10m",
            "winddirection_10m",
            "surface_pressure",
            "weathercode"
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "sunrise",
            "sunset"
        ],
        "timezone": "Europe/Warsaw",
        "past_days": 2,
        "forecast_days": 2
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
        resp.raise_for_status()
        raw = resp.json()
    except requests.exceptions.ConnectionError:
        return {"blad": "Brak połączenia z internetem — nie można pobrać pogody."}
    except requests.exceptions.Timeout:
        return {"blad": f"Przekroczono czas oczekiwania ({TIMEOUT_S}s) na odpowiedź API."}
    except requests.exceptions.HTTPError as e:
        return {"blad": f"Błąd HTTP {e.response.status_code} z Open-Meteo API."}
    except Exception as e:
        return {"blad": f"Nieoczekiwany błąd: {str(e)}"}

    return _przetworz_dane(raw)


def _najblizszy_indeks(godziny: list, teraz_naive: datetime) -> int:
    """Zwraca indeks godziny z API najbliższej bieżącemu czasowi."""
    najlepszy, najmniejsza = len(godziny) // 2, None
    for i, t in enumerate(godziny):
        try:
            dt = datetime.strptime(t, "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            continue
        roznica = abs((dt - teraz_naive).total_seconds())
        if najmniejsza is None or roznica < najmniejsza:
            najmniejsza, najlepszy = roznica, i
    return najlepszy


def _przetworz_dane(raw: dict) -> dict:
    """Przetwarza surowe dane JSON z API na czytelne struktury."""
    godziny = raw["hourly"]["time"]
    teraz = datetime.now(STREFA)
    teraz_str = teraz.strftime("%Y-%m-%dT%H:00")

    # Znajdź indeks aktualnej godziny
    idx = None
    for i, t in enumerate(godziny):
        if t == teraz_str:
            idx = i
            break
    if idx is None:
        # Brak dokładnego trafienia — weź najbliższy czasowo (porównanie naiwne)
        idx = _najblizszy_indeks(godziny, teraz.replace(tzinfo=None))

    cisnienia_48h = []
    for offset in range(-47, 1):
        j = idx + offset
        if 0 <= j < len(raw["hourly"]["surface_pressure"]):
            v = raw["hourly"]["surface_pressure"][j]
            if v is not None:
                cisnienia_48h.append(v)

    tendencja_cisnienia = _oblicz_tendencje(cisnienia_48h)

    def _get(klucz, i=idx):
        val = raw["hourly"][klucz]
        return val[i] if i < len(val) else None

    kierunek_wiatru = _get("winddirection_10m")
    predkosc_wiatru = _get("windspeed_10m")

    # Szacowana temperatura wody (opóźnienie termiczne — woda wygrzewa się wolniej)
    temp_powietrza = _get("temperature_2m")
    temp_wody_est = _szacuj_temperature_wody(temp_powietrza, raw)

    # Dane dziennie (dzisiaj) — znajdź po dacie zamiast sztywnego indeksu
    daily = raw.get("daily", {})
    daily_times = daily.get("time", [])
    dzis = teraz.strftime("%Y-%m-%d")
    if dzis in daily_times:
        dzisiaj_idx = daily_times.index(dzis)
    else:
        dzisiaj_idx = min(2, max(0, len(daily_times) - 1))

    def _daily(klucz):
        seria = daily.get(klucz, [])
        return seria[dzisiaj_idx] if dzisiaj_idx < len(seria) else None

    wschod = _daily("sunrise")
    zachod = _daily("sunset")

    return {
        "blad": None,
        "aktualna": {
            "temperatura_c": temp_powietrza,
            "temperatura_wody_c": temp_wody_est,
            "cisnienie_hpa": _get("surface_pressure"),
            "predkosc_wiatru_kmh": predkosc_wiatru,
            "kierunek_wiatru_deg": kierunek_wiatru,
            "kierunek_wiatru_text": _kierunek_na_tekst(kierunek_wiatru),
            "zachmurzenie_proc": _get("cloudcover"),
            "opady_mm": _get("precipitation"),
            "kod_pogody": _get("weathercode"),
            "opis_pogody": _kod_na_opis(_get("weathercode"))
        },
        "tendencja_cisnienia": tendencja_cisnienia,
        "cisnienia_48h": cisnienia_48h[-24:] if len(cisnienia_48h) >= 24 else cisnienia_48h,
        "wschod_slonca": wschod,
        "zachod_slonca": zachod,
        "czas_pobrania": teraz.strftime("%Y-%m-%d %H:%M")
    }


def _oblicz_tendencje(cisnienia: list[float]) -> dict:
    """
    Analizuje tendencję ciśnienia z ostatnich godzin.
    Zwraca: zmiana_3h, zmiana_24h, ocena ('rosnace'/'stabilne'/'spadajace'/'gwaltowne')
    """
    if len(cisnienia) < 4:
        return {"ocena": "brak_danych", "zmiana_3h": 0, "zmiana_24h": 0}

    zmiana_3h = cisnienia[-1] - cisnienia[-4] if len(cisnienia) >= 4 else 0
    zmiana_24h = cisnienia[-1] - cisnienia[-25] if len(cisnienia) >= 25 else cisnienia[-1] - cisnienia[0]

    if abs(zmiana_3h) > 4 or abs(zmiana_24h) > 8:
        ocena = "gwaltowne"
    elif zmiana_3h > 1.5 or zmiana_24h > 4:
        ocena = "rosnace"
    elif zmiana_3h < -1.5 or zmiana_24h < -4:
        ocena = "spadajace"
    else:
        ocena = "stabilne"

    return {
        "ocena": ocena,
        "zmiana_3h": round(zmiana_3h, 1),
        "zmiana_24h": round(zmiana_24h, 1)
    }


def _szacuj_temperature_wody(temp_powietrza: Optional[float], raw: dict) -> Optional[float]:
    """Szacuje temp. wody na podstawie uśrednionej temp. powietrza z ostatnich dni."""
    if temp_powietrza is None:
        return None
    # Prosta heurystyka: temp wody ~ średnia ważona ostatnich 5 dni + korekta sezonowa
    temps = raw["hourly"].get("temperature_2m", [])
    if not temps:
        return None
    ostatnie = [t for t in temps[-120:] if t is not None]
    if not ostatnie:
        return None
    srednia = sum(ostatnie) / len(ostatnie)
    # Woda jest "leniwa" — opóźnienie i wygładzenie
    return round(srednia * 0.7 + temp_powietrza * 0.3, 1)


def _kierunek_na_tekst(deg: Optional[float]) -> str:
    """Zamienia stopnie na tekst kierunku (N, NE, E, ...) po polsku."""
    if deg is None:
        return "nieznany"
    kierunki = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = round(deg / 45) % 8
    mapa = {"N": "Północny", "NE": "Północno-wschodni", "E": "Wschodni",
            "SE": "Południowo-wschodni", "S": "Południowy", "SW": "Południowo-zachodni",
            "W": "Zachodni", "NW": "Północno-zachodni"}
    return mapa.get(kierunki[idx], "Nieznany")


def _kod_na_opis(kod: Optional[int]) -> str:
    """Tłumaczy WMO weathercode na opis po polsku."""
    if kod is None:
        return "Brak danych"
    if kod == 0:
        return "Bezchmurnie"
    elif kod in (1, 2):
        return "Częściowe zachmurzenie"
    elif kod == 3:
        return "Całkowite zachmurzenie"
    elif kod in (45, 48):
        return "Mgła"
    elif kod in (51, 53, 55):
        return "Mżawka"
    elif kod in (61, 63, 65):
        return "Deszcz"
    elif kod in (71, 73, 75):
        return "Opady śniegu"
    elif kod in (80, 81, 82):
        return "Przelotne deszcze"
    elif kod in (95, 96, 99):
        return "Burza"
    return "Zmienne warunki"
