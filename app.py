"""
app.py — główna aplikacja Flask do planowania wędkowania.
Łączy moduły pogoda, solunar, ocena, jeziora, dziennik, auth i db.
Uruchomienie:
  Lokalnie:    python app.py
  Produkcja:   gunicorn --bind 0.0.0.0:8080 app:app
"""

import functools
import os
import shutil
import uuid
import copy
from datetime import datetime

from config import (
    DATA_DIR, APP_DIR, IS_PRODUCTION,
    zaladuj_env, pobierz_secret_key,
)

# Wczytaj .env (lokalny development) — jedno miejsce zamiast duplikatów
zaladuj_env()

from flask import (
    Flask, render_template, jsonify, request,
    send_from_directory, session, redirect, url_for
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

import db
from pogoda import pobierz_pogode
from solunar import oblicz_okna_solunarne
from ocena import ocen_jezioro, porownaj_jeziora
from jeziora import (
    wczytaj_jeziora, pobierz_jezioro, wczytaj_punkty_gpx,
    polacz_punkty_z_gpx, zastosuj_gps_uzytkownika, istnieje_lowisko,
)
from dziennik import pobierz_wpisy, dodaj_wpis, usun_wpis, statystyki
from ai_ocena_ryby import ocen_rybye
from auth import zarejestruj, weryfikuj

app = Flask(__name__)

# Za reverse-proxy (Fly.io) — poprawny adres klienta i schemat (https)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.secret_key = pobierz_secret_key()
app.config.update(
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,        # max 10 MB upload
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",              # blokuje cross-site wysyłkę ciasteczka
    SESSION_COOKIE_SECURE=IS_PRODUCTION,        # tylko HTTPS w produkcji
    WTF_CSRF_TIME_LIMIT=None,                   # token ważny przez całą sesję
)

# Ochrona CSRF (formularze + nagłówek X-CSRFToken dla fetch)
csrf = CSRFProtect(app)

# Limit prób (anti-brute-force). Pamięć procesu — wystarcza dla 1 maszyny.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

UPLOAD_FOLDER  = os.path.join(DATA_DIR, "uploads")
ZDJECIA_FOLDER = os.path.join(UPLOAD_FOLDER, "zdjecia")

_DOZWOLONE_ZDJECIA = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


# ── Inicjalizacja danych ──────────────────────────────────────────────────────

def _init_data():
    """Tworzy katalogi i kopiuje współdzielony jeziora.json przy pierwszym starcie."""
    os.makedirs(ZDJECIA_FOLDER, exist_ok=True)
    dest = os.path.join(DATA_DIR, "jeziora.json")
    src  = os.path.join(APP_DIR,  "jeziora.json")
    if not os.path.exists(dest) and os.path.exists(src):
        shutil.copy2(src, dest)


_init_data()
db.init_db()


# ── Błąd CSRF → czytelna odpowiedź ─────────────────────────────────────────────

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"blad": "Sesja wygasła (CSRF) — odśwież stronę", "redirect": "/login"}), 400
    return redirect(url_for("login_page"))


# ── Dekorator wymagający zalogowania ─────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"blad": "Wymagane logowanie", "redirect": "/login"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


# ── Pomocniki GPX / GPS (per-użytkownik) ──────────────────────────────────────

def _sciezka_gpx(jezior_id: str, username: str) -> str:
    """Prywatna ścieżka pliku GPX — osobna dla każdego użytkownika i jeziora."""
    bez_u = "".join(c for c in username.lower() if c.isalnum() or c in "_-")
    bez_j = "".join(c for c in jezior_id.lower() if c.isalnum() or c in "_-")
    return os.path.join(UPLOAD_FOLDER, f"gpx_{bez_u}_{bez_j}.gpx")


def _wczytaj_gpx_jezior(jezioro: dict, username: str) -> dict:
    sciezka = _sciezka_gpx(jezioro["id"], username)
    if not os.path.exists(sciezka):
        return jezioro
    try:
        punkty = wczytaj_punkty_gpx(sciezka)
        return polacz_punkty_z_gpx(jezioro, punkty)
    except Exception:
        return jezioro


def _przygotuj_jezioro(jezioro: dict, username: str, overrides: dict) -> dict:
    """Nakłada prywatne pozycje GPS i punkty GPX użytkownika na dane jeziora."""
    jez = zastosuj_gps_uzytkownika(jezioro, overrides)
    return _wczytaj_gpx_jezior(jez, username)


def _pobierz_pelne_dane(username: str, preferencje: dict = None) -> dict:
    dane_jezior = wczytaj_jeziora()
    overrides   = db.gps_overrides(username)

    wulpinskie = _przygotuj_jezioro(pobierz_jezioro(dane_jezior, "wulpinskie"), username, overrides)
    sarag      = _przygotuj_jezioro(pobierz_jezioro(dane_jezior, "sarag"),      username, overrides)
    miesiac    = datetime.now().month

    pogoda_w = pobierz_pogode(wulpinskie["wspolrzedne"]["lat"], wulpinskie["wspolrzedne"]["lon"])
    pogoda_s = pobierz_pogode(sarag["wspolrzedne"]["lat"],      sarag["wspolrzedne"]["lon"])

    solunar_w = oblicz_okna_solunarne(wulpinskie["wspolrzedne"]["lat"], wulpinskie["wspolrzedne"]["lon"])
    solunar_s = oblicz_okna_solunarne(sarag["wspolrzedne"]["lat"],      sarag["wspolrzedne"]["lon"])

    ocena_w  = ocen_jezioro(pogoda_w, solunar_w, wulpinskie, miesiac, preferencje)
    ocena_s  = ocen_jezioro(pogoda_s, solunar_s, sarag,      miesiac, preferencje)
    porownanie = porownaj_jeziora(ocena_w, ocena_s, wulpinskie["nazwa"], sarag["nazwa"])

    return {
        "czas_odswiezenia": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "miesiac": miesiac,
        "jeziora": {
            "wulpinskie": {"dane": wulpinskie, "pogoda": pogoda_w, "solunar": solunar_w, "ocena": ocena_w},
            "sarag":      {"dane": sarag,       "pogoda": pogoda_s, "solunar": solunar_s, "ocena": ocena_s},
        },
        "porownanie": porownanie,
    }


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 60 per hour", methods=["POST"])
def login_page():
    if session.get("user"):
        return redirect(url_for("index"))
    blad_l = blad_r = None

    if request.method == "POST":
        akcja = request.form.get("akcja", "login")

        if akcja == "login":
            user = request.form.get("username", "").strip().lower()
            pwd  = request.form.get("password", "")
            if weryfikuj(user, pwd):
                session.clear()
                session["user"] = user
                return redirect(url_for("index"))
            blad_l = "Błędny nick lub hasło."

        elif akcja == "register":
            user = request.form.get("reg_username", "").strip()
            pwd  = request.form.get("reg_password", "")
            pwd2 = request.form.get("reg_password2", "")
            if pwd != pwd2:
                blad_r = "Hasła nie są identyczne."
            else:
                ok, komunikat = zarejestruj(user, pwd)
                if ok:
                    session.clear()
                    session["user"] = user.lower()
                    return redirect(url_for("index"))
                blad_r = komunikat

    return render_template("login.html", blad_l=blad_l, blad_r=blad_r)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Strona główna ─────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session["user"])


# ── Dane planera ──────────────────────────────────────────────────────────────

@app.route("/api/dane")
@login_required
def api_dane():
    preferencje = {
        "gatunek":      request.args.get("gatunek",       "").strip(),
        "metoda":       request.args.get("metoda",         "").strip(),
        "jezioro_pref": request.args.get("jezioro_pref",  "").strip(),
    }
    preferencje = {k: v for k, v in preferencje.items() if v}
    try:
        dane = _pobierz_pelne_dane(session["user"], preferencje or None)
        return jsonify({"sukces": True, "dane": dane})
    except Exception as e:
        return jsonify({"sukces": False, "blad": str(e)}), 500


@app.route("/api/pogoda/<jezior_id>")
@login_required
def api_pogoda(jezior_id: str):
    dane_jezior = wczytaj_jeziora()
    j = pobierz_jezioro(dane_jezior, jezior_id)
    if not j:
        return jsonify({"blad": f"Nieznane jezioro: {jezior_id}"}), 404
    return jsonify(pobierz_pogode(j["wspolrzedne"]["lat"], j["wspolrzedne"]["lon"]))


@app.route("/api/upload-gpx/<jezior_id>", methods=["POST"])
@login_required
def upload_gpx(jezior_id: str):
    # Walidacja: jezior_id musi być znanym jeziorem (ochrona przed path traversal)
    if not pobierz_jezioro(wczytaj_jeziora(), jezior_id):
        return jsonify({"blad": f"Nieznane jezioro: {jezior_id}"}), 404
    if "plik" not in request.files:
        return jsonify({"blad": "Brak pliku w żądaniu"}), 400
    plik = request.files["plik"]
    if not (plik.filename or "").lower().endswith(".gpx"):
        return jsonify({"blad": "Plik musi mieć rozszerzenie .gpx"}), 400
    sciezka = _sciezka_gpx(jezior_id, session["user"])
    plik.save(sciezka)
    try:
        punkty = wczytaj_punkty_gpx(sciezka)
        return jsonify({"sukces": True, "komunikat": f"Wczytano {len(punkty)} punktów z GPX", "punkty": punkty})
    except Exception as e:
        return jsonify({"blad": str(e)}), 400


@app.route("/api/jeziora")
@login_required
def api_jeziora():
    dane      = wczytaj_jeziora()
    overrides = db.gps_overrides(session["user"])
    if overrides:
        dane = copy.deepcopy(dane)
        for jez in dane.get("jeziora", []):
            jid = jez.get("id")
            for low in jez.get("lowiska", []):
                ov = overrides.get((jid, low.get("id")))
                if ov:
                    low["gps"] = {"lat": ov["lat"], "lon": ov["lon"], "placeholder": False}
    return jsonify(dane)


@app.route("/api/lowisko-gps/<jezior_id>/<lowisko_id>", methods=["POST"])
@login_required
def api_ustaw_gps(jezior_id: str, lowisko_id: str):
    dane = request.get_json(silent=True)
    if not dane or "lat" not in dane or "lon" not in dane:
        return jsonify({"blad": "Wymagane pola: lat, lon"}), 400
    try:
        lat = float(dane["lat"])
        lon = float(dane["lon"])
    except (TypeError, ValueError):
        return jsonify({"blad": "Nieprawidłowe współrzędne — wymagane liczby"}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"blad": "Współrzędne poza zakresem"}), 400
    if not istnieje_lowisko(jezior_id, lowisko_id):
        return jsonify({"blad": f"Nie znaleziono: {jezior_id}/{lowisko_id}"}), 404
    # Zapis prywatny dla użytkownika — nie dotyka danych innych osób
    db.zapisz_gps(session["user"], jezior_id, lowisko_id, lat, lon)
    return jsonify({"sukces": True, "lat": round(lat, 6), "lon": round(lon, 6)})


# ── Dziennik połowów (per-user) ───────────────────────────────────────────────

@app.route("/api/dziennik/ocen-ryby", methods=["POST"])
@login_required
def api_ocen_ryby():
    if "zdjecie" not in request.files:
        return jsonify({"blad": "Brak pliku zdjęcia (pole: 'zdjecie')"}), 400
    plik = request.files["zdjecie"]
    ext  = os.path.splitext(plik.filename or "")[1].lower()
    if ext not in _DOZWOLONE_ZDJECIA:
        return jsonify({"blad": f"Nieobsługiwany format. Dozwolone: {', '.join(_DOZWOLONE_ZDJECIA)}"}), 400
    os.makedirs(ZDJECIA_FOLDER, exist_ok=True)
    nazwa_pliku = f"{uuid.uuid4().hex[:14]}{ext}"
    sciezka     = os.path.join(ZDJECIA_FOLDER, nazwa_pliku)
    plik.save(sciezka)
    wynik = ocen_rybye(sciezka)
    return jsonify({"sukces": True, "wynik": wynik, "zdjecie_id": nazwa_pliku})


@app.route("/api/dziennik/wpisy", methods=["GET"])
@login_required
def api_dziennik_wpisy():
    user = session["user"]
    return jsonify({"sukces": True, "wpisy": pobierz_wpisy(user), "statystyki": statystyki(user)})


@app.route("/api/dziennik/dodaj", methods=["POST"])
@login_required
def api_dziennik_dodaj():
    dane = request.get_json(silent=True)
    if not dane:
        return jsonify({"blad": "Brak danych JSON"}), 400
    wpis = dodaj_wpis(session["user"], dane)
    return jsonify({"sukces": True, "wpis": wpis})


@app.route("/api/dziennik/usun/<wpis_id>", methods=["DELETE"])
@login_required
def api_dziennik_usun(wpis_id: str):
    if usun_wpis(session["user"], wpis_id):
        return jsonify({"sukces": True})
    return jsonify({"blad": "Nie znaleziono wpisu"}), 404


@app.route("/uploads/zdjecia/<nazwa_pliku>")
@login_required
def serwuj_zdjecie(nazwa_pliku: str):
    return send_from_directory(ZDJECIA_FOLDER, nazwa_pliku)


@app.route("/api/ja")
def api_ja():
    user = session.get("user")
    return jsonify({"zalogowany": bool(user), "user": user})


# ── Start (lokalny development) ───────────────────────────────────────────────

if __name__ == "__main__":
    # ngrok (opcjonalnie — token w .env lub zmiennej środowiskowej NGROK_TOKEN)
    ngrok_token = os.environ.get("NGROK_TOKEN", "").strip()
    public_url  = None
    if ngrok_token:
        try:
            from pyngrok import ngrok as _ngrok, conf as _conf
            _conf.get_default().auth_token = ngrok_token
            tunnel = _ngrok.connect(5000)
            public_url = tunnel.public_url
        except Exception as e:
            print(f"[ngrok] Błąd: {e}")

    print("=" * 60)
    print("  Planer Wędkarski — Wulpińskie & Sarąg")
    print(f"  Lokalnie:  http://127.0.0.1:5000")
    if public_url:
        print(f"  Publiczny: {public_url}")
    print("=" * 60)

    app.run(debug=True, host="0.0.0.0", port=5000)
