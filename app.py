"""
app.py — główna aplikacja Flask do planowania wędkowania.
Łączy moduły pogoda, solunar, ocena, jeziora, dziennik i auth.
Uruchomienie:
  Lokalnie:    python app.py
  Produkcja:   gunicorn --bind 0.0.0.0:8080 app:app
"""

import functools
import os
import shutil
import uuid
import json
from datetime import datetime
from pathlib import Path

# ── Załaduj .env (lokalny development) ───────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

from flask import (
    Flask, render_template, jsonify, request,
    send_from_directory, session, redirect, url_for
)

from config import DATA_DIR, APP_DIR
from pogoda import pobierz_pogode
from solunar import oblicz_okna_solunarne
from ocena import ocen_jezioro, porownaj_jeziora
from jeziora import wczytaj_jeziora, pobierz_jezioro, wczytaj_punkty_gpx, polacz_punkty_z_gpx, zapisz_gps_lowiska
from dziennik import pobierz_wpisy, dodaj_wpis, usun_wpis, statystyki
from ai_ocena_ryby import ocen_rybye
from auth import zarejestruj, weryfikuj

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # max 10 MB

UPLOAD_FOLDER  = os.path.join(DATA_DIR, "uploads")
ZDJECIA_FOLDER = os.path.join(UPLOAD_FOLDER, "zdjecia")

_DOZWOLONE_ZDJECIA = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


# ── Inicjalizacja katalogu danych ────────────────────────────────────────────

def _init_data():
    """
    Tworzy strukturę katalogów DATA_DIR i kopiuje jeziora.json
    z katalogu aplikacji, jeśli jeszcze nie istnieje w DATA_DIR.
    Wywoływane przy imporcie modułu (działa zarówno z python app.py
    jak i z gunicorn app:app).
    """
    os.makedirs(os.path.join(DATA_DIR, "uploads", "zdjecia"), exist_ok=True)

    dest = os.path.join(DATA_DIR, "jeziora.json")
    src  = os.path.join(APP_DIR,  "jeziora.json")
    if not os.path.exists(dest) and os.path.exists(src):
        shutil.copy2(src, dest)


_init_data()


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


# ── Pomocniki GPX ─────────────────────────────────────────────────────────────

def _wczytaj_gpx_jezior(jezioro: dict) -> dict:
    sciezka = os.path.join(UPLOAD_FOLDER, f"{jezioro['id']}.gpx")
    if not os.path.exists(sciezka):
        return jezioro
    try:
        punkty = wczytaj_punkty_gpx(sciezka)
        return polacz_punkty_z_gpx(jezioro, punkty)
    except Exception:
        return jezioro


def _pobierz_pelne_dane(preferencje: dict = None) -> dict:
    dane_jezior = wczytaj_jeziora()
    wulpinskie = _wczytaj_gpx_jezior(pobierz_jezioro(dane_jezior, "wulpinskie"))
    sarag      = _wczytaj_gpx_jezior(pobierz_jezioro(dane_jezior, "sarag"))
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
        dane = _pobierz_pelne_dane(preferencje or None)
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
    if "plik" not in request.files:
        return jsonify({"blad": "Brak pliku w żądaniu"}), 400
    plik = request.files["plik"]
    if not plik.filename.lower().endswith(".gpx"):
        return jsonify({"blad": "Plik musi mieć rozszerzenie .gpx"}), 400
    sciezka = os.path.join(UPLOAD_FOLDER, f"{jezior_id}.gpx")
    plik.save(sciezka)
    try:
        punkty = wczytaj_punkty_gpx(sciezka)
        return jsonify({"sukces": True, "komunikat": f"Wczytano {len(punkty)} punktów z GPX", "punkty": punkty})
    except Exception as e:
        return jsonify({"blad": str(e)}), 400


@app.route("/api/jeziora")
@login_required
def api_jeziora():
    return jsonify(wczytaj_jeziora())


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
    if zapisz_gps_lowiska(jezior_id, lowisko_id, lat, lon):
        return jsonify({"sukces": True, "lat": lat, "lon": lon})
    return jsonify({"blad": f"Nie znaleziono: {jezior_id}/{lowisko_id}"}), 404


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
