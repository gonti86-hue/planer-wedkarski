"""
ai_ocena_ryby.py — analiza zdjęcia ryby przez Claude Vision API.
Szacuje gatunek, długość i sprawdza wymiar ochronny.

Wymaga: pip install anthropic
Klucz API: plik .env z linią  ANTHROPIC_API_KEY=sk-ant-...
           lub zmienna środowiskowa ANTHROPIC_API_KEY
"""

import base64
import json
import os
import re
from pathlib import Path

from config import zaladuj_env

# Wczytaj .env przez wspólny loader (bez duplikowania parsera)
zaladuj_env()

try:
    from anthropic import Anthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

MODEL = "claude-3-5-sonnet-20241022"

_PROMPT = """Jesteś ekspertem wędkarskim z Polski. Przeanalizuj to zdjęcie połowu.

Oceń rybę:
1. Zidentyfikuj gatunek (polska nazwa)
2. Oszacuj długość — szukaj obiektów odniesienia na zdjęciu:
   • linijka / taśma miernicza → odczytaj dokładnie
   • dłoń dorosłego          → ≈ 19 cm (szerokość)
   • smartfon leżący obok    → ≈ 15 cm (krótszy bok)
   • kartka A4               → 21 × 29,7 cm
   • brak odniesienia        → szacuj z proporcji ciała ryby i tła

3. Sprawdź wymiar ochronny (PZW Warmia-Mazury):
   Szczupak 45 cm, Sandacz 45 cm, Okoń 15 cm, Leszcz 25 cm, Lin 25 cm,
   Płoć 15 cm, Sum 70 cm, Miętus 25 cm, Sieja 35 cm, Karp 30 cm,
   Amur biały 50 cm, Jaź 25 cm, Karaś 15 cm, Krąp 15 cm, Wzdręga 15 cm.

Odpowiedz WYŁĄCZNIE tym JSON (zero dodatkowego tekstu):
{
  "gatunek": "polska nazwa gatunku",
  "dlugosc_cm_min": liczba_całkowita,
  "dlugosc_cm_max": liczba_całkowita,
  "pewnosc": "wysoka|srednia|niska",
  "odniesienie": "linijka|dlonia|smartfon|kartka|brak",
  "opis": "1-2 zdania po polsku z opisem ryby i metody pomiaru",
  "wymiar_ochronny_cm": liczba_lub_null,
  "spelnia_wymiar": true_lub_false_lub_null
}"""


def ocen_ryby(sciezka_zdjecia: str) -> dict:
    """
    Analizuje zdjęcie ryby i zwraca słownik z gatunkiem, rozmiarem i oceną.
    W razie błędu zwraca {"blad": "opis błędu"}.
    """
    if not _ANTHROPIC_OK:
        return {
            "blad": (
                "Pakiet anthropic nie jest zainstalowany.\n"
                "Uruchom: venv\\Scripts\\pip install anthropic"
            )
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "blad": (
                "Brak klucza API. Utwórz plik .env w folderze aplikacji "
                "i dodaj linię:\nANTHROPIC_API_KEY=sk-ant-..."
            )
        }

    sciezka = Path(sciezka_zdjecia)
    if not sciezka.exists():
        return {"blad": f"Nie znaleziono pliku: {sciezka_zdjecia}"}

    ext = sciezka.suffix.lower()
    # Formaty obsługiwane przez Claude Vision. HEIC NIE jest wspierany —
    # filtrowany już na wejściu (app.py), tutaj zostają tylko bezpieczne typy.
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(ext, "image/jpeg")

    try:
        with open(sciezka, "rb") as f:
            obraz_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
    except OSError as e:
        return {"blad": f"Błąd odczytu pliku zdjęcia: {e}"}

    try:
        client = Anthropic(api_key=api_key)
        odpowiedz = client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": obraz_b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
    except Exception as e:
        return {"blad": f"Błąd API Claude: {str(e)[:300]}"}

    tekst = odpowiedz.content[0].text.strip()

    # Wyciągnij JSON — bądź odporny na markdown code block
    dopasowanie = re.search(r"\{.*\}", tekst, re.DOTALL)
    if not dopasowanie:
        return {"blad": "AI zwróciło nieoczekiwany format odpowiedzi.", "raw": tekst[:400]}

    try:
        return json.loads(dopasowanie.group())
    except json.JSONDecodeError:
        return {"blad": "Błąd parsowania odpowiedzi AI.", "raw": tekst[:400]}
