"""
ocena.py — algorytm oceny warunków wędkarskich (wynik 0-100).
Ocenia osobno każde jezioro biorąc pod uwagę:
  - ciśnienie i jego tendencję
  - wiatr (prędkość, kierunek)
  - temperaturę (powietrza, szacunkową wody)
  - sezon i docelowe gatunki
  - okna solunarne i porę dnia
  - ochronę gatunków (okresy, zakazy) — fix: ichtiolog
  - przyducha w jeziorach eutroficznych — fix: ekolog
  - burza = wynik 0 — fix: algorytm
"""

from datetime import datetime
from typing import Optional


# =====================================================================
# OCHRONA GATUNKÓW — wg polskiego prawa (woj. warmińsko-mazurskie)
# Źródło: Ustawa o rybactwie śródlądowym + regulamin PZW Warmia-Mazury
# Fix: ichtiolog / prawnik
# =====================================================================
OCHRONA_GATUNKOW: dict[str, dict] = {
    "Sieja":            {"wymiar_cm": 35, "okres_ochronny": [10, 11, 12], "zakaz": False,
                         "uwaga": "Tarło październik–grudzień — C&R lub zmiana celu"},
    "Sielawa":          {"wymiar_cm": 18, "okres_ochronny": [10, 11],     "zakaz": False,
                         "uwaga": "Tarło październik–listopad"},
    "Sandacz":          {"wymiar_cm": 50, "okres_ochronny": [1, 2, 3, 4, 5], "zakaz": False,
                         "uwaga": "Wymiar 50 cm; okres ochronny do 31 maja"},
    "Szczupak":         {"wymiar_cm": 50, "okres_ochronny": [12, 1, 2, 3, 4], "zakaz": False,
                         "uwaga": "Wymiar 50 cm; okres ochronny 1 XII–30 IV"},
    "Węgorz":           {"wymiar_cm": 60, "okres_ochronny": [12, 1, 2, 3], "zakaz": False,
                         "uwaga": "Wymiar 60 cm; okres ochronny 1 XII–31 III; limit 2 szt./dobę (sprawdź przepisy Okręgu Olsztyn)"},
    "Sum":              {"wymiar_cm": 70,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Boleń":            {"wymiar_cm": 40,  "okres_ochronny": [1, 2, 3, 4], "zakaz": False,
                         "uwaga": "Wymiar 40 cm; okres ochronny 1 I–30 IV"},
    "Miętus":           {"wymiar_cm": 25,  "okres_ochronny": [12, 1, 2], "zakaz": False,
                         "uwaga": "Wymiar 25 cm; okres ochronny 1 XII–koniec lutego"},
    "Okoń":             {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Jazgarz":          {"wymiar_cm": None, "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Ukleja":           {"wymiar_cm": None, "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Jaź":              {"wymiar_cm": 25,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Leszcz":           {"wymiar_cm": 25,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Krąp":             {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Płoć":             {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Wzdręga":          {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Lin":              {"wymiar_cm": 25,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Karaś":            {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Karaś srebrzysty": {"wymiar_cm": 15,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Karp":             {"wymiar_cm": 30,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
    "Amur biały":       {"wymiar_cm": 50,  "okres_ochronny": [], "zakaz": False, "uwaga": None},
}


def ocen_jezioro(pogoda: dict, solunar: dict, jezioro: dict,
                 miesiac: Optional[int] = None,
                 preferencje: Optional[dict] = None) -> dict:
    """
    Główna funkcja oceny. Zwraca słownik z wynikiem i szczegółowym rozbiciem.
    preferencje = {"gatunek": str, "metoda": str, "jezioro_pref": str}
    """
    if pogoda.get("blad"):
        return {
            "wynik": 0, "blad": pogoda["blad"], "rozbicie": {},
            "rekomendacja": "Brak danych pogodowych",
            "gatunek_cel": None, "lowisko": None, "metoda": None,
            "glebokosc_rekomendowana": None, "dopasowanie_preferencji": None,
            "ostrzezenia": [], "ochrona": None
        }

    if miesiac is None:
        miesiac = datetime.now().month

    aktualna  = pogoda.get("aktualna", {})
    tendencja = pogoda.get("tendencja_cisnienia", {})

    # ===================================================================
    # FIX (algorytm): BURZA — zeruje wynik, najwyższy priorytet
    # ===================================================================
    kod_pogody = aktualna.get("kod_pogody", 0) or 0
    if kod_pogody in (95, 96, 99):
        return {
            "wynik": 0, "blad": None,
            "rozbicie": {
                "cisnienie":      {"wynik": 0, "maks": 25, "opis": "Burza — warunki niebezpieczne"},
                "wiatr":          {"wynik": 0, "maks": 20, "opis": "Burza — warunki niebezpieczne"},
                "temperatura":    {"wynik": 0, "maks": 15, "opis": "Burza — warunki niebezpieczne"},
                "sezon_gatunek":  {"wynik": 0, "maks": 20, "opis": "Burza — warunki niebezpieczne"},
                "solunar":        {"wynik": 0, "maks": 15, "opis": "Burza — warunki niebezpieczne"},
                "warunki_ogolne": {"wynik": 0, "maks":  5, "opis": "Burza elektryczna!"},
            },
            "rekomendacja": "⛈ BURZA — kategorycznie nie wychodzić na wodę!",
            "gatunek_cel": None, "lowisko": None, "metoda": None,
            "glebokosc_rekomendowana": None, "dopasowanie_preferencji": None,
            "ostrzezenia": ["⛈ Burza elektryczna — zakaz wędkowania na otwartych wodach!"],
            "ochrona": None
        }

    # ===================================================================
    # SCORING (6 składników)
    # ===================================================================
    wynik_cisnienie, opis_cisnienie = _ocen_cisnienie(aktualna, tendencja)
    wynik_wiatr,     opis_wiatr     = _ocen_wiatr(aktualna, jezioro)
    wynik_temp,      opis_temp      = _ocen_temperature(aktualna, miesiac)
    wynik_sezon, opis_sezon, gatunek_cel = _ocen_sezon(jezioro, miesiac, aktualna, preferencje)
    wynik_solunar,   opis_solunar   = _ocen_solunar(solunar)
    wynik_pogoda,    opis_pogoda    = _ocen_pogode_ogolna(aktualna)

    wynik_total = max(0, min(100,
        wynik_cisnienie + wynik_wiatr + wynik_temp +
        wynik_sezon + wynik_solunar + wynik_pogoda
    ))

    # ===================================================================
    # OSTRZEŻENIA I KARY
    # ===================================================================
    ostrzezenia: list[str] = []

    # Parsuj listę preferowanych gatunków (obsługa multi-select)
    _gatunek_raw = (preferencje or {}).get("gatunek", "")
    if isinstance(_gatunek_raw, list):
        gatunki_pref_lista = [g.strip() for g in _gatunek_raw if g.strip()]
    elif _gatunek_raw:
        gatunki_pref_lista = [g.strip() for g in _gatunek_raw.split(",") if g.strip()]
    else:
        gatunki_pref_lista = []

    # FIX (ichtiolog): sprawdź ochronę dla KAŻDEGO gatunku z preferencji.
    # Jeśli któryś jest zakazany/chroniony, pokaż ostrzeżenie.
    # Kara punktowa tylko jeśli gatunek_cel jest chroniony (alternatywy są OK).
    gatunki_do_sprawdzenia = gatunki_pref_lista or ([gatunek_cel] if gatunek_cel else [])
    wolne_gatunki = [g for g in gatunki_do_sprawdzenia
                     if not OCHRONA_GATUNKOW.get(g, {}).get("zakaz")
                     and miesiac not in OCHRONA_GATUNKOW.get(g, {}).get("okres_ochronny", [])]

    for gat_check in gatunki_do_sprawdzenia:
        ochr_check = OCHRONA_GATUNKOW.get(gat_check, {})
        if ochr_check.get("zakaz"):
            ostrzezenia.append(
                f"⛔ {gat_check}: {ochr_check.get('uwaga', 'Zakaz połowu — gatunek chroniony')}"
            )
            # Kara tylko jeśli nie ma wolnej alternatywy z listy preferencji
            if not wolne_gatunki:
                wynik_total = max(0, wynik_total - 25)
        elif miesiac in ochr_check.get("okres_ochronny", []):
            uwaga = ochr_check.get("uwaga") or "Złów i wypuść lub zmień gatunek"
            ostrzezenia.append(f"⚠ {gat_check}: Okres ochronny — {uwaga}")
            if not wolne_gatunki:
                wynik_total = max(0, wynik_total - 10)

    # ochrona dla rzeczywistego gatunek_cel (do wyświetlenia wymiarów)
    ochr_cel = OCHRONA_GATUNKOW.get(gatunek_cel, {}) if gatunek_cel else {}

    # FIX (ekolog): przyducha — eutroficzne jezioro + upał
    if "eutroficzne" in jezioro.get("typ", ""):
        temp_wody = aktualna.get("temperatura_wody_c") or 0
        predkosc_w = aktualna.get("predkosc_wiatru_kmh") or 0
        if miesiac in [7, 8] and temp_wody > 20 and predkosc_w < 8:
            kara = 8 if temp_wody > 23 else 4
            wynik_total = max(0, wynik_total - kara)
            ostrzezenia.append(
                f"🌡 Ryzyko przyduchy (temp. wody {temp_wody}°C, wiatr {predkosc_w:.0f} km/h) — "
                "możliwy niedobór tlenu przy dnie; ryby gromadzą się tuż pod powierzchnią"
            )

    # ===================================================================
    # ŁOWISKO, REKOMENDACJA, DOPASOWANIE
    # ===================================================================
    lowisko, metoda, glebokosc = _wybierz_lowisko(jezioro, gatunek_cel, miesiac, preferencje)
    rekomendacja = _generuj_rekomendacje(wynik_total, jezioro["nazwa"], gatunek_cel, lowisko, metoda)
    dopasowanie  = _ocen_dopasowanie(jezioro, gatunek_cel, metoda, miesiac, preferencje)
    szansa       = _oblicz_szanse_polowu(wynik_total, gatunek_cel, jezioro, miesiac, solunar)

    return {
        "wynik": wynik_total,
        "szansa_polowu_proc": szansa,
        "blad": None,
        "rozbicie": {
            "cisnienie":      {"wynik": wynik_cisnienie, "maks": 25, "opis": opis_cisnienie},
            "wiatr":          {"wynik": wynik_wiatr,     "maks": 20, "opis": opis_wiatr},
            "temperatura":    {"wynik": wynik_temp,      "maks": 15, "opis": opis_temp},
            "sezon_gatunek":  {"wynik": wynik_sezon,     "maks": 20, "opis": opis_sezon},
            "solunar":        {"wynik": wynik_solunar,   "maks": 15, "opis": opis_solunar},
            "warunki_ogolne": {"wynik": wynik_pogoda,    "maks":  5, "opis": opis_pogoda}
        },
        "rekomendacja": rekomendacja,
        "gatunek_cel": gatunek_cel,
        "lowisko": lowisko,
        "metoda": metoda,
        "glebokosc_rekomendowana": glebokosc,
        "dopasowanie_preferencji": dopasowanie,
        "ostrzezenia": ostrzezenia,
        # FIX (ichtiolog): dane ochronne dla AKTUALNEGO celu połowu
        "ochrona": {
            "wymiar_cm":      ochr_cel.get("wymiar_cm"),
            "okres_ochronny": ochr_cel.get("okres_ochronny", []),
            "zakaz":          ochr_cel.get("zakaz", False),
            "uwaga":          ochr_cel.get("uwaga")
        } if ochr_cel else None
    }


# =====================================================================
# FUNKCJE POMOCNICZE — bez zmian w logice, tylko poprawione opisy
# =====================================================================

def _ocen_cisnienie(aktualna: dict, tendencja: dict) -> tuple[int, str]:
    """Ocena ciśnienia: max 25 pkt."""
    cisnienie  = aktualna.get("cisnienie_hpa", 1013)
    ocena_tend = tendencja.get("ocena", "stabilne")
    zmiana_3h  = tendencja.get("zmiana_3h", 0)
    zmiana_24h = tendencja.get("zmiana_24h", 0)

    if ocena_tend == "gwaltowne":
        wynik = 3
        opis  = f"Gwałtowne zmiany ciśnienia ({zmiana_24h:+.1f} hPa/24h) — ryby niereaktywne"
    elif ocena_tend == "spadajace" and -6 <= zmiana_24h <= -2:
        wynik = 22
        opis  = f"Lekki spadek ciśnienia ({zmiana_24h:+.1f} hPa/24h) — idealne warunki przed frontem"
    elif ocena_tend == "stabilne":
        if cisnienie and cisnienie > 1015:
            wynik = 16
            opis  = f"Stabilne wysokie ciśnienie ({cisnienie:.0f} hPa) — przeciętne branie"
        elif cisnienie and cisnienie < 1005:
            wynik = 12
            opis  = f"Stabilne niskie ciśnienie ({cisnienie:.0f} hPa) — słabsze branie"
        else:
            wynik = 15
            opis  = f"Stabilne ciśnienie ({cisnienie:.0f} hPa) — umiarkowane warunki"
    elif ocena_tend == "rosnace":
        wynik = 18
        opis  = f"Rosnące ciśnienie ({zmiana_24h:+.1f} hPa/24h) — warunki się poprawiają"
    else:
        wynik = 12
        opis  = "Brak danych ciśnienia"

    return wynik, opis


def _ocen_wiatr(aktualna: dict, jezioro: dict) -> tuple[int, str]:
    """Ocena wiatru: max 20 pkt."""
    predkosc = aktualna.get("predkosc_wiatru_kmh") or 0
    kierunek = aktualna.get("kierunek_wiatru_text", "")

    if predkosc < 3:
        wynik = 8
        opis  = f"Cisza wietrzna ({predkosc:.0f} km/h) — brak cyrkulacji, ryby mniej aktywne"
    elif predkosc <= 10:
        wynik = 18
        opis  = f"Lekki wiatr ({predkosc:.0f} km/h) — idealne warunki"
    elif predkosc <= 20:
        wynik = 20
        opis  = f"Umiarkowany wiatr ({predkosc:.0f} km/h) — optymalne warunki, aktywna woda"
    elif predkosc <= 30:
        wynik = 14
        opis  = f"Wiatr {predkosc:.0f} km/h — dopuszczalne, utrudnione rzuty"
    elif predkosc <= 45:
        wynik = 6
        opis  = f"Silny wiatr ({predkosc:.0f} km/h) — trudne warunki"
    else:
        wynik = 0
        opis  = f"Bardzo silny wiatr ({predkosc:.0f} km/h) — nie zalecane wędkowanie"

    if any(k in kierunek for k in ["Zachodni", "Południowo-zachodni", "Południowy"]):
        if 5 <= predkosc <= 25:
            wynik = min(wynik + 2, 20)
            opis += f"; {kierunek} przynosi tlen i pokarm do brzegu"

    return wynik, opis


def _ocen_temperature(aktualna: dict, miesiac: int) -> tuple[int, str]:
    """Ocena temperatury: max 15 pkt."""
    temp_powietrza = aktualna.get("temperatura_c")
    temp_wody      = aktualna.get("temperatura_wody_c")

    if temp_powietrza is None:
        return 8, "Brak danych temperatury"

    if miesiac in [5, 6, 7, 8, 9]:
        optimum_wody, opis_sez = (18, 26), "letni"
    elif miesiac in [3, 4]:
        optimum_wody, opis_sez = (10, 18), "wiosenny"
    elif miesiac in [10, 11]:
        optimum_wody, opis_sez = (10, 15), "jesienny"
    else:
        optimum_wody, opis_sez = (2, 8),   "zimowy"

    wynik = 10
    if temp_wody is not None:
        if optimum_wody[0] <= temp_wody <= optimum_wody[1]:
            wynik = 15
            opis  = f"Temp. wody {temp_wody}°C w optimum sezonu {opis_sez}"
        elif temp_wody < optimum_wody[0] - 5 or temp_wody > optimum_wody[1] + 5:
            wynik = 5
            opis  = f"Temp. wody {temp_wody}°C poza optimum sezonu {opis_sez}"
        else:
            wynik = 10
            opis  = f"Temp. wody {temp_wody}°C blisko optimum"
    else:
        opis = f"Temp. powietrza {temp_powietrza}°C (sezon {opis_sez})"

    if temp_powietrza < 5 and miesiac in [5, 6, 7, 8, 9]:
        wynik  = max(wynik - 3, 0)
        opis  += "; chłodny dzień w sezonie ciepłym"

    return wynik, opis


def _ocen_sezon(jezioro: dict, miesiac: int, aktualna: dict,
                preferencje: Optional[dict] = None) -> tuple[int, str, Optional[str]]:
    """Ocena sezonowości: max 20 pkt."""
    gatunki_aktywne = [
        g for g in jezioro.get("gatunki", [])
        if miesiac in g.get("sezon", [])
        and not OCHRONA_GATUNKOW.get(g["nazwa"], {}).get("zakaz", False)  # wyklucz zakazane
    ]

    if not gatunki_aktywne:
        return 5, "Poza sezonem dla wszystkich gatunków tego jeziora", None

    n        = len(gatunki_aktywne)
    wynik_bazowy = 20 if n >= 4 else 15 if n >= 2 else 10
    nazwy    = ", ".join(g["nazwa"] for g in gatunki_aktywne[:4])

    # Parsuj listę preferowanych gatunków (obsługa multi-select)
    _raw = (preferencje or {}).get("gatunek", "")
    if isinstance(_raw, list):
        gatunki_pref = [g.strip() for g in _raw if g.strip()]
    elif _raw:
        gatunki_pref = [g.strip() for g in _raw.split(",") if g.strip()]
    else:
        gatunki_pref = []

    if gatunki_pref:
        # 1. Szukaj pierwszego preferowanego gatunku aktywnego W TYM jeziorze
        for gat in gatunki_pref:
            if any(g["nazwa"] == gat for g in gatunki_aktywne):
                etykieta = gat if len(gatunki_pref) == 1 else f"{gat} (z: {', '.join(gatunki_pref)})"
                opis = f"Twój cel: {etykieta} aktywny ✓ ({n} gat. w sezonie: {nazwy})"
                return wynik_bazowy, opis, gat

        # 2. Żaden nie jest aktywny — czy któryś jest w jeziorze?
        for gat in gatunki_pref:
            if any(g["nazwa"] == gat for g in jezioro.get("gatunki", [])):
                alt  = gatunki_aktywne[0]["nazwa"]
                pref_txt = ", ".join(gatunki_pref)
                opis = f"{pref_txt} — poza sezonem; alternatywa: {alt} ({n} gat.: {nazwy})"
                return max(wynik_bazowy - 3, 5), opis, alt

        # 3. Żaden nie żyje w tym jeziorze
        alt      = gatunki_aktywne[0]["nazwa"]
        pref_txt = ", ".join(gatunki_pref)
        opis     = f"{pref_txt} — brak w tym jeziorze; zamiast: {alt} ({nazwy})"
        return max(wynik_bazowy - 5, 5), opis, alt

    gatunek = gatunki_aktywne[0]["nazwa"]
    return wynik_bazowy, f"Aktywne gatunki ({n}): {nazwy}", gatunek


def _ocen_solunar(solunar: dict) -> tuple[int, str]:
    """Przepisuje wynik solunarny do skali 0-15."""
    if not solunar:
        return 5, "Brak danych solunarnych"

    aktywne_teraz = solunar.get("aktywne_teraz", False)
    nastepne      = solunar.get("nastepne_okno")

    if aktywne_teraz:
        wynik = 15
        opis  = "Aktywne okno solunarne — teraz jest najlepsza pora!"
    elif nastepne:
        wynik = 8
        opis  = f"Następne okno: {nastepne.get('szczyt', '')} ({nastepne.get('typ', '')})"
    else:
        wynik = 5
        opis  = "Brak bliskich okien solunarnych"

    faza = solunar.get("faza_ksiezyca", {})
    if faza:
        opis += f" | Faza: {faza.get('nazwa', '')} ({faza.get('oswietlenie_proc', 0):.0f}%)"

    return wynik, opis


def _ocen_pogode_ogolna(aktualna: dict) -> tuple[int, str]:
    """Ocena ogólna pogody: max 5 pkt."""
    zachmurzenie = aktualna.get("zachmurzenie_proc", 50)
    opady        = aktualna.get("opady_mm", 0) or 0
    kod          = aktualna.get("kod_pogody", 0) or 0

    # Burza jest obsługiwana wcześniej — tutaj nie wystąpi
    if opady > 5:
        return 1, f"Silne opady ({opady} mm) — utrudnione warunki"
    elif opady > 1:
        return 3, f"Lekki deszcz ({opady} mm) — ryby mogą być aktywne"
    elif 30 <= zachmurzenie <= 70:
        return 5, "Częściowe zachmurzenie — optymalne dla wędkarza"
    elif zachmurzenie < 30:
        return 4, "Słonecznie — dobre warunki, unikaj pełni słońca w południe"
    else:
        return 3, "Całkowite zachmurzenie — przeciętne warunki"


def _wybierz_lowisko(jezioro: dict, gatunek: Optional[str], miesiac: int,
                     preferencje: Optional[dict] = None):
    """Dobiera łowisko, metodę i głębokość."""
    if not gatunek:
        return None, None, None

    metoda_pref = (preferencje or {}).get("metoda", "")

    lowiska = [l for l in jezioro.get("lowiska", []) if gatunek in l.get("gatunki", [])]
    if lowiska:
        nazwa_lowiska = lowiska[0]["nazwa"]
        gl            = lowiska[0].get("glebokosc_m", [0, 0])
        opis_gl       = f"{gl[0]}–{gl[1]} m" if gl[0] != gl[1] else f"{gl[0]} m"
    else:
        nazwa_lowiska = "Krawędź roślinności / strefa przybrzeżna"
        opis_gl       = "2–5 m"

    metody_gatunku = []
    for g in jezioro.get("gatunki", []):
        if g["nazwa"] == gatunek:
            metody_gatunku = g.get("metody", [])
            break

    if metoda_pref and metoda_pref in metody_gatunku:
        metoda = metoda_pref
    elif metody_gatunku:
        metoda = metody_gatunku[0]
    else:
        metoda = "spławik"

    return nazwa_lowiska, metoda, opis_gl


def _ocen_dopasowanie(jezioro: dict, gatunek_cel: Optional[str],
                      metoda: Optional[str], miesiac: int,
                      preferencje: Optional[dict] = None) -> Optional[dict]:
    """Oblicza % dopasowania do preferencji użytkownika."""
    if not preferencje:
        return None

    # Parsuj listę preferowanych gatunków
    _raw = preferencje.get("gatunek", "")
    if isinstance(_raw, list):
        gatunki_pref_lista = [g.strip() for g in _raw if g.strip()]
    elif _raw:
        gatunki_pref_lista = [g.strip() for g in _raw.split(",") if g.strip()]
    else:
        gatunki_pref_lista = []

    metoda_pref  = preferencje.get("metoda", "")
    jezioro_pref = preferencje.get("jezioro_pref", "")

    if not gatunki_pref_lista and not metoda_pref and not jezioro_pref:
        return None

    punkty, maks, opisy = 0, 0, []

    if gatunki_pref_lista:
        maks += 50
        # Znajdź najlepsze dopasowanie z listy (aktywny > w jeziorze > brak)
        best_pts, best_opis = 0, ""
        for gat in gatunki_pref_lista:
            aktywny    = any(
                g["nazwa"] == gat and miesiac in g.get("sezon", [])
                for g in jezioro.get("gatunki", [])
            )
            w_jeziorze = any(g["nazwa"] == gat for g in jezioro.get("gatunki", []))
            if aktywny and best_pts < 50:
                best_pts, best_opis = 50, f"{gat} w sezonie ✓"
                break   # nie trzeba szukać lepiej
            elif w_jeziorze and best_pts < 15:
                best_pts, best_opis = 15, f"{gat} poza sezonem"
        if best_pts:
            punkty += best_pts
            opisy.append(best_opis)
        else:
            pref_txt = ", ".join(gatunki_pref_lista)
            opisy.append(f"{pref_txt} — brak w tym jeziorze")

    if metoda_pref:
        maks += 30
        metody_jezior = {m for g in jezioro.get("gatunki", []) for m in g.get("metody", [])}
        if metoda_pref in metody_jezior:
            punkty += 30
            dopas_m = "✓" if metoda == metoda_pref else "(możliwa)"
            opisy.append(f"metoda {metoda_pref} {dopas_m}")
        else:
            opisy.append(f"metoda {metoda_pref} rzadko stosowana")

    if jezioro_pref:
        maks += 20
        if jezioro_pref == jezioro.get("id"):
            punkty += 20
            opisy.append("Twoje jezioro ✓")

    procent = round(punkty / maks * 100) if maks else 0
    return {"procent": procent, "opis": "; ".join(opisy)}


def _generuj_rekomendacje(wynik: int, nazwa_jeziora: str,
                          gatunek: Optional[str],
                          lowisko: Optional[str],
                          metoda: Optional[str]) -> str:
    """Generuje tekstową rekomendację na podstawie wyniku."""
    if wynik >= 80:
        ocena, emoji = "Doskonałe warunki", "★★★"
    elif wynik >= 65:
        ocena, emoji = "Dobre warunki", "★★☆"
    elif wynik >= 50:
        ocena, emoji = "Przeciętne warunki", "★☆☆"
    elif wynik >= 35:
        ocena, emoji = "Słabe warunki", "☆☆☆"
    else:
        ocena, emoji = "Niezalecane", "✗"

    opis = f"{emoji} {ocena} na {nazwa_jeziora}"
    if gatunek:
        opis += f" — cel: {gatunek}"
    if lowisko:
        opis += f", łowisko: {lowisko}"
    if metoda:
        opis += f" ({metoda})"
    return opis


def _oblicz_szanse_polowu(wynik_total: int, gatunek_cel: Optional[str],
                          jezioro: dict, miesiac: int, solunar: dict) -> int:
    """
    Szacuje % szans złowienia gatunku_cel w aktualnych warunkach.
    Skala: 3 % (najgorsze) … 93 % (idealne).
    Nigdy 0% (zawsze można coś złapać) i nigdy 100% (ryba to nie automat).
    """
    # Baza: wynik 0→3 %, 50→44 %, 100→85 %
    szansa = max(3, min(85, round(wynik_total * 0.82 + 3)))

    if gatunek_cel:
        gatunek_obj = next(
            (g for g in jezioro.get("gatunki", []) if g["nazwa"] == gatunek_cel), None
        )
        if not gatunek_obj:
            # Gatunek nie żyje w tym jeziorze
            szansa = max(3, szansa - 25)
        else:
            if miesiac in gatunek_obj.get("sezon", []):
                # Szczyt sezonu dla tego gatunku
                szansa = min(93, szansa + 7)
            else:
                # Poza sezonem
                szansa = max(3, szansa - 18)

    # Bonus — aktywne okno solunarne teraz
    if solunar and solunar.get("aktywne_teraz"):
        szansa = min(93, szansa + 5)

    return szansa


def porownaj_jeziora(ocena_1: dict, ocena_2: dict, nazwa_1: str, nazwa_2: str) -> dict:
    """Porównuje dwa jeziora i wskazuje lepsze z uzasadnieniem."""
    w1, w2  = ocena_1.get("wynik", 0), ocena_2.get("wynik", 0)
    roznica = abs(w1 - w2)

    if roznica < 5:
        werdykt  = f"Praktycznie remis ({nazwa_1}: {w1}, {nazwa_2}: {w2}) — wybierz bliższe"
        zwyciezca = None
    elif w1 > w2:
        werdykt  = f"Lepsze: {nazwa_1} ({w1}/100 vs {w2}/100)"
        zwyciezca = "jezioro_1"
    else:
        werdykt  = f"Lepsze: {nazwa_2} ({w2}/100 vs {w1}/100)"
        zwyciezca = "jezioro_2"

    return {
        "werdykt": werdykt, "zwyciezca": zwyciezca,
        "wynik_1": w1, "wynik_2": w2, "roznica": roznica
    }
