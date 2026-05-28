# Planer Wędkarski — Wulpińskie & Sarąg

Aplikacja webowa (Flask + HTML/JS) do codziennej oceny warunków wędkarskich na dwóch jeziorach woj. warmińsko-mazurskiego: **Jezioro Wulpińskie** i **Jezioro Sarąg**.

## Funkcje

- Pobiera aktualne dane pogodowe z **Open-Meteo API** (bezpłatne, bez klucza)
- Oblicza **okna solunarne** (górowanie/dolowanie Księżyca, wschód/zachód Słońca)
- Wystawia ocenę **0–100** dla każdego jeziora osobno
- Wskazuje **lepsze jezioro** z uzasadnieniem
- Rekomenduje **gatunek, łowisko, metodę i głębokość** dopasowane do sezonu
- Obsługa wgrywania własnych punktów łowiskowych z pliku **GPX**

## Wymagania

- Python 3.10 lub nowszy
- pip

## Instalacja krok po kroku

### 1. Utwórz wirtualne środowisko (zalecane)

```bash
python -m venv venv
```

**Windows:**
```
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 2. Zainstaluj zależności

```bash
pip install -r requirements.txt
```

### 3. Uruchom aplikację

```bash
python app.py
```

### 4. Otwórz przeglądarkę

Przejdź pod adres: **http://127.0.0.1:5000**

---

## Struktura projektu

```
fishing_planner/
├── app.py              # Główna aplikacja Flask (routing, API endpoints)
├── pogoda.py           # Pobieranie i przetwarzanie danych z Open-Meteo API
├── solunar.py          # Obliczenia okien solunarnych (ephem)
├── ocena.py            # Algorytm oceny warunków (0–100 pkt)
├── jeziora.py          # Wczytywanie danych jezior + parsowanie GPX
├── jeziora.json        # Dane strukturalne o jeziorach (edytowalne)
├── requirements.txt
├── README.md
├── static/
│   ├── style.css
│   └── script.js
├── templates/
│   └── index.html
└── uploads/            # Wgrane pliki GPX (tworzone automatycznie)
```

## Dostosowanie

### Zmiana współrzędnych GPS jezior

Edytuj plik `jeziora.json` — zmień wartości `lat` i `lon` w sekcji `wspolrzedne` każdego jeziora.

### Uzupełnienie punktów łowiskowych

W pliku `jeziora.json` odszukaj łowiska z `"placeholder": true` i zastąp wartości `lat`/`lon` rzeczywistymi współrzędnymi. Możesz też wgrać plik GPX bezpośrednio przez interfejs webowy.

### Format pliku GPX

Aplikacja obsługuje standardowe pliki GPX 1.0 i 1.1 z punktami `<wpt>`. Eksportuj punkty trasy z urządzenia GPS lub aplikacji (np. Garmin BaseCamp, OsmAnd, Mapy.cz).

## Algorytm oceny (max 100 pkt)

| Składowa             | Maks. pkt | Opis                                              |
|----------------------|-----------|---------------------------------------------------|
| Ciśnienie            | 25        | Tendencja: lekki spadek = najlepsze branie        |
| Wiatr                | 20        | Optimum 5–20 km/h; kierunek SW/W = premia         |
| Temperatura          | 15        | Woda w optimum sezonowym                          |
| Sezon / gatunek      | 20        | Liczba gatunków aktywnych w danym miesiącu        |
| Okna solunarne       | 15        | Aktywne okno +15 pkt; faza księżyca +5 pkt        |
| Warunki ogólne       | 5         | Zachmurzenie, opady, burzowa pogoda               |

## Dane pogodowe

- **Źródło:** [Open-Meteo](https://open-meteo.com/) — bezpłatne, bez rejestracji
- **Odświeżanie:** kliknij przycisk „Odśwież" lub uruchom ponownie
- **Historyczne:** pobierane 48h wstecz (do analizy tendencji ciśnienia)

## Uwagi

- Temperatura wody jest **szacunkowa** — obliczona z uśrednionej temp. powietrza z ostatnich dni (brak bezpośrednich pomiarów)
- Okna solunarne to teoria wędkarska — traktuj je jako wskazówkę, nie pewnik
- Aplikacja działa offline po pierwszym uruchomieniu (dane są cachowane przez przeglądarkę); nowe dane wymagają połączenia z internetem
- Wędkuj zgodnie z regulaminem PZW i obowiązującymi przepisami

## Licencja

Do użytku prywatnego / edukacyjnego.
