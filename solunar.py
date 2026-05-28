"""
solunar.py — obliczenia okien solunarnych i fazy księżyca.
Solunar Theory (John Alden Knight, 1926): ryby są najbardziej aktywne
podczas górowania i dolowania Księżyca oraz Słońca (główne okna)
oraz w połowie między nimi (mniejsze okna).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import ephem  # biblioteka astronomiczna (pip install ephem)


def faza_ksiezyca(data: Optional[datetime] = None) -> dict:
    """
    Oblicza fazę księżyca dla podanej daty (domyślnie: teraz).
    Zwraca: faza (0-1), nazwa, oświetlenie (%), wschodOrazu zachód.
    """
    if data is None:
        data = datetime.now(timezone.utc)

    ks = ephem.Moon(data)
    faza = ks.phase  # 0-100 % oświetlenia

    # Czy księżyc rośnie, czy maleje? Porównaj oświetlenie za 12 h.
    pozniej = ephem.Moon(data + timedelta(hours=12)).phase
    rosnacy = pozniej > faza

    if faza < 6:
        nazwa = "Nów"
    elif faza > 96:
        nazwa = "Pełnia"
    elif faza < 45:
        nazwa = "Sierp rosnący" if rosnacy else "Sierp malejący"
    elif faza < 55:
        nazwa = "Pierwsza kwadra" if rosnacy else "Ostatnia kwadra"
    else:  # 55–96 %
        nazwa = "Garbata rosnąca" if rosnacy else "Garbata malejąca"

    # Sprawdź dokładniej fazę numeryczną (0=nów, 0.5=pełnia)
    faza_eph = faza / 100.0  # 0-1

    return {
        "oswietlenie_proc": round(faza, 1),
        "faza_0_1": round(faza_eph, 2),
        "nazwa": nazwa,
        "komentarz": _komentarz_fazy(faza)
    }


def _komentarz_fazy(oswietlenie: float) -> str:
    """Wędkarski komentarz do fazy księżyca."""
    if oswietlenie < 15:
        return "Nów — bardzo dobre warunki nocne, ryby aktywne"
    elif 45 < oswietlenie < 60:
        return "Kwadra — umiarkowana aktywność"
    elif oswietlenie > 85:
        return "Pełnia — intensywna aktywność nocna, w dzień może być słabiej"
    return "Przejściowa faza — standardowa aktywność"


def oblicz_okna_solunarne(lat: float, lon: float, data: Optional[datetime] = None) -> dict:
    """
    Oblicza główne i mniejsze okna solunarnego dla podanej lokalizacji i daty.

    Główne okna: ±1h od górowania i dolowania Księżyca (2h każde).
    Mniejsze okna: ±30min od wschodu i zachodu Księżyca (1h każde).
    """
    if data is None:
        data = datetime.now(timezone.utc)

    # Lokalizacja jako obiekt ephem
    obserwator = ephem.Observer()
    obserwator.lat = str(lat)
    obserwator.lon = str(lon)
    obserwator.date = data.strftime("%Y/%m/%d")
    obserwator.pressure = 0  # wyłącz korektę refrakcji dla obliczeń górowania

    ksiezyc = ephem.Moon()

    # Wschód i zachód Księżyca
    try:
        wschod_ks = ephem.localtime(obserwator.next_rising(ksiezyc, start=obserwator.date))
        zachod_ks = ephem.localtime(obserwator.next_setting(ksiezyc, start=obserwator.date))
    except ephem.AlwaysUpError:
        wschod_ks = zachod_ks = None
    except ephem.NeverUpError:
        wschod_ks = zachod_ks = None

    # Górowanie i dolowanie Księżyca (transit)
    try:
        gorowanie_ks = ephem.localtime(obserwator.next_transit(ksiezyc, start=obserwator.date))
        dolowanie_ks = gorowanie_ks + timedelta(hours=12.4)  # przybliżenie półokresu
    except Exception:
        gorowanie_ks = dolowanie_ks = None

    # Słońce — wschód i zachód
    slonce = ephem.Sun()
    try:
        wschod_sl = ephem.localtime(obserwator.next_rising(slonce, start=obserwator.date))
        zachod_sl = ephem.localtime(obserwator.next_setting(slonce, start=obserwator.date))
    except Exception:
        wschod_sl = zachod_sl = None

    okna = []
    teraz = datetime.now()

    def dodaj_okno(bazowy_czas, typ, margin_min):
        if bazowy_czas is None:
            return
        # Konwertuj do datetime bez strefy
        if hasattr(bazowy_czas, 'tzinfo') and bazowy_czas.tzinfo:
            baz = bazowy_czas.replace(tzinfo=None)
        else:
            baz = bazowy_czas
        start = baz - timedelta(minutes=margin_min)
        koniec = baz + timedelta(minutes=margin_min)
        aktywne = start <= teraz <= koniec
        okna.append({
            "typ": typ,
            "szczyt": baz.strftime("%H:%M"),
            "start": start.strftime("%H:%M"),
            "koniec": koniec.strftime("%H:%M"),
            "aktywne": aktywne
        })

    dodaj_okno(gorowanie_ks, "Główne — górowanie Księżyca", 60)
    dodaj_okno(dolowanie_ks, "Główne — dolowanie Księżyca", 60)
    dodaj_okno(wschod_ks, "Mniejsze — wschód Księżyca", 30)
    dodaj_okno(zachod_ks, "Mniejsze — zachód Księżyca", 30)

    # Okna solunarno-słoneczne (świt i zmierzch zawsze aktywne)
    dodaj_okno(wschod_sl, "Świt (szczupak, sandacz, okoń)", 45)
    dodaj_okno(zachod_sl, "Zmierzch (węgorz, leszcz, sandacz)", 45)

    # Posortuj okna chronologicznie
    okna_posortowane = sorted(okna, key=lambda x: x["szczyt"])

    # Następne okno — pierwsze dzisiaj po bieżącej godzinie;
    # jeśli wszystkie minęły, „zawiń" do najwcześniejszego (jutro rano).
    teraz_hhmm = teraz.strftime("%H:%M")
    nastepne = next((o for o in okna_posortowane if o["szczyt"] > teraz_hhmm), None)
    if nastepne is None and okna_posortowane:
        nastepne = okna_posortowane[0]

    return {
        "okna": okna_posortowane,
        "nastepne_okno": nastepne,
        "wschod_slonca": wschod_sl.strftime("%H:%M") if wschod_sl else "N/D",
        "zachod_slonca": zachod_sl.strftime("%H:%M") if zachod_sl else "N/D",
        "faza_ksiezyca": faza_ksiezyca(data),
        "aktywne_teraz": any(o["aktywne"] for o in okna)
    }
