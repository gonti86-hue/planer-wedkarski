/* script.js — logika frontendu aplikacji wędkarskiej */

let daneCache = null;

/* ===== KONFIGURACJA MAP LEAFLET ===== */
const LEAFLET_CFG = {
    wulpinskie: {
        lat: 53.7135, lon: 20.3210, zoom: 14,
        osmQuery: '[out:json][timeout:15];way["natural"="water"]["name"~"Wulp",i](53.69,20.28,53.74,20.37);out geom;'
    },
    sarag: {
        lat: 53.6930, lon: 20.4050, zoom: 15,
        osmQuery: '[out:json][timeout:15];way["natural"="water"]["name"~"Sar",i](53.68,20.38,53.71,20.43);out geom;'
    }
};

const mapaInstancje = {};  // Leaflet map instances
const pendingMaps   = {};  // { prefix: { dane, gotowe } }

/* ===== KONFIGURACJA BATYMIETRII ===== */
const BATYMIETRIA_CFG = {
    wulpinskie: {
        // Jezioro rynnowe, max 54 m — 4 strefy
        strefy: [
            { inset_km: 0,     fill: '#caf0f8', etykieta: 'Strefa brzegowa  0–5 m'  },
            { inset_km: 0.025, fill: '#90e0ef', etykieta: 'Sublitoral       5–15 m' },
            { inset_km: 0.075, fill: '#0096c7', etykieta: 'Głęboka         15–30 m' },
            { inset_km: 0.130, fill: '#023e8a', etykieta: 'Rynna           30–54 m' }
        ]
    },
    sarag: {
        // Jezioro eutroficzne, max 16 m — 3 strefy
        strefy: [
            { inset_km: 0,     fill: '#b7e4c7', etykieta: 'Strefa brzegowa  0–3 m'  },
            { inset_km: 0.040, fill: '#52b788', etykieta: 'Środkowa         3–8 m'  },
            { inset_km: 0.085, fill: '#1b4332', etykieta: 'Głęboczek       8–16 m'  }
        ]
    }
};

/* ===== ZDJĘCIA RYB (Wikipedia REST API) ===== */
const RYBA_WIKI_EN = {
    "Szczupak":          "Esox_lucius",
    "Okoń":              "European_perch",
    "Leszcz":            "Common_bream",
    "Lin":               "Tench",
    "Sandacz":           "Zander",
    "Sieja":             "Common_whitefish",
    "Sielawa":           "Vendace",
    "Płoć":              "Common_roach",
    "Karaś":             "Crucian_carp",
    "Karaś srebrzysty":  "Prussian_carp",
    "Karp":              "Common_carp",
    "Węgorz":            "European_eel",
    "Jazgarz":           "Ruffe",
    "Jaź":               "Ide_(fish)",
    "Sum":               "Wels_catfish",
    "Miętus":            "Burbot",
    "Wzdręga":           "Rudd",
    "Krąp":              "White_bream",
    "Amur biały":        "Grass_carp"
};

var _rybaZdjeciaCache = {};  // gatunek → URL zdjęcia lub null

async function pobierzZdjecieRyby(gatunek) {
    if (!gatunek) return null;
    if (gatunek in _rybaZdjeciaCache) return _rybaZdjeciaCache[gatunek];

    var wikiName = RYBA_WIKI_EN[gatunek];
    if (!wikiName) { _rybaZdjeciaCache[gatunek] = null; return null; }

    var ctrl = new AbortController();
    var tid  = setTimeout(function() { ctrl.abort(); }, 4000);
    try {
        var resp = await fetch(
            'https://en.wikipedia.org/api/rest_v1/page/summary/' + encodeURIComponent(wikiName),
            { signal: ctrl.signal }
        );
        clearTimeout(tid);
        var data = await resp.json();
        var url  = (data.thumbnail && data.thumbnail.source) || null;
        _rybaZdjeciaCache[gatunek] = url;
        return url;
    } catch(e) {
        clearTimeout(tid);
        _rybaZdjeciaCache[gatunek] = null;
        return null;
    }
}

/* ===== INICJALIZACJA ===== */
document.addEventListener("DOMContentLoaded", () => {
    wczytajUIPreferencje();
    odswiezDane();
    _initCheckboxGatunkow();
});

/* ===== CHECKBOXY GATUNKÓW — JS-driven toggle (niezawodny cross-browser) ===== */
function _initCheckboxGatunkow() {
    document.querySelectorAll('input[name="pref-gatunek"]').forEach(function(cb) {
        cb.addEventListener('change', function() {
            this.closest('.pref-radio').classList.toggle('active', this.checked);
            var checked = Array.from(
                document.querySelectorAll('input[name="pref-gatunek"]:checked')
            ).map(function(c) { return c.value; });
            _aktualizujLicznikGatunkow(checked);
        });
    });
}

/* ===== PREFERENCJE ===== */
function pobierzPreferencje() {
    try { return JSON.parse(localStorage.getItem("wedkar_pref") || "{}"); }
    catch (e) { return {}; }
}

function zapiszPreferencjeDoLS(pref) {
    localStorage.setItem("wedkar_pref", JSON.stringify(pref));
}

function wczytajUIPreferencje() {
    var pref = pobierzPreferencje();
    // Jezioro
    document.querySelectorAll('input[name="pref-jezioro"]').forEach(function(r) {
        r.checked = (r.value === (pref.jezioro || ""));
    });
    // Gatunki (multi-checkbox) — checked + klasa active
    var gatunki = pref.gatunki || [];
    document.querySelectorAll('input[name="pref-gatunek"]').forEach(function(cb) {
        var zaznaczony = gatunki.indexOf(cb.value) !== -1;
        cb.checked = zaznaczony;
        cb.closest('.pref-radio').classList.toggle('active', zaznaczony);
    });
    _aktualizujLicznikGatunkow(gatunki);
    // Metoda
    document.querySelectorAll('input[name="pref-metoda"]').forEach(function(r) {
        r.checked = (r.value === (pref.metoda || ""));
    });
    aktualizujPodsumowaie(pref);
}

function aktualizujPodsumowaie(pref) {
    var czesci = [];
    if (pref.jezioro === "wulpinskie") czesci.push("Wulpińskie");
    else if (pref.jezioro === "sarag") czesci.push("Sarąg");
    var gatunki = pref.gatunki || [];
    if (gatunki.length === 1) czesci.push(gatunki[0]);
    else if (gatunki.length > 1) czesci.push(gatunki.slice(0, 3).join(", ") + (gatunki.length > 3 ? "…" : ""));
    if (pref.metoda) czesci.push(pref.metoda);
    var el = document.getElementById("pref-podsumowanie");
    if (el) el.textContent = czesci.length ? czesci.join(" · ") : "brak preferencji";
}

function _aktualizujLicznikGatunkow(gatunki) {
    var el = document.getElementById("pref-gatunki-liczba");
    if (!el) return;
    el.textContent = gatunki.length ? "(" + gatunki.length + " wybranych)" : "";
}

function wyczyscGatunki(e) {
    if (e) e.stopPropagation();
    document.querySelectorAll('input[name="pref-gatunek"]').forEach(function(cb) {
        cb.checked = false;
        cb.closest('.pref-radio').classList.remove('active');
    });
    _aktualizujLicznikGatunkow([]);
}

function zastosujPreferencje() {
    var jezioro = document.querySelector('input[name="pref-jezioro"]:checked');
    var metoda  = document.querySelector('input[name="pref-metoda"]:checked');
    var gatunki = [];
    document.querySelectorAll('input[name="pref-gatunek"]:checked').forEach(function(cb) {
        gatunki.push(cb.value);
    });
    var pref = {
        jezioro: jezioro ? jezioro.value : "",
        gatunki: gatunki,
        metoda:  metoda  ? metoda.value  : ""
    };
    zapiszPreferencjeDoLS(pref);
    _aktualizujLicznikGatunkow(gatunki);
    aktualizujPodsumowaie(pref);
    odswiezDane();
}

function resetujPreferencje() {
    localStorage.removeItem("wedkar_pref");
    document.querySelectorAll('input[name="pref-jezioro"]').forEach(function(r) { r.checked = r.value === ""; });
    document.querySelectorAll('input[name="pref-metoda"]').forEach(function(r)  { r.checked = r.value === ""; });
    document.querySelectorAll('input[name="pref-gatunek"]').forEach(function(cb) { cb.checked = false; });
    _aktualizujLicznikGatunkow([]);
    aktualizujPodsumowaie({});
    odswiezDane();
}

function togglePreferencje() {
    var panel = document.getElementById("pref-panel");
    var strzalka = document.getElementById("pref-strzalka");
    var ukryty = panel.classList.toggle("hidden");
    strzalka.classList.toggle("open", !ukryty);
}

/* ===== ODŚWIEŻANIE DANYCH ===== */
async function odswiezDane() {
    pokazLoader(true);
    ukryjBlad();

    var pref = pobierzPreferencje();
    var params = new URLSearchParams();
    if (pref.jezioro) params.set("jezioro_pref", pref.jezioro);
    // Obsługa multi-gatunki (nowe) i fallback dla starych preferencji (gatunek jako string)
    var gatunkiLista = pref.gatunki && pref.gatunki.length ? pref.gatunki
                     : (pref.gatunek ? [pref.gatunek] : []);
    if (gatunkiLista.length) params.set("gatunek", gatunkiLista.join(","));
    if (pref.metoda)  params.set("metoda",  pref.metoda);
    var url = "/api/dane" + (params.toString() ? "?" + params.toString() : "");

    try {
        const resp = await fetch(url);
        if (resp.status === 401) { window.location.href = "/login"; return; }
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const json = await resp.json();
        if (!json.sukces) throw new Error(json.blad || "Nieznany błąd serwera");

        daneCache = json.dane;
        renderujDane(daneCache);
        document.getElementById("czas-odswiezenia").textContent =
            "Ostatnia aktualizacja: " + daneCache.czas_odswiezenia;
    } catch (err) {
        pokazBlad("Nie udało się pobrać danych: " + err.message);
    } finally {
        pokazLoader(false);
    }
}

/* ===== RENDEROWANIE GŁÓWNE ===== */
function renderujDane(dane) {
    const { jeziora, porownanie } = dane;
    const w = jeziora.wulpinskie;
    const s = jeziora.sarag;

    // Werdykt główny
    renderujWerdykt(porownanie);

    // Karty jezior
    renderujKarte("w", w, porownanie.zwyciezca === "jezioro_1");
    renderujKarte("s", s, porownanie.zwyciezca === "jezioro_2");

    document.getElementById("tresc-glowna").classList.remove("hidden");
}

function renderujWerdykt(por) {
    const el = document.getElementById("werdykt-tekst");
    if (!por.zwyciezca) {
        el.innerHTML = `🎣 ${esc(por.werdykt)}`;
        el.className = "werdykt-tekst werdykt-remis";
    } else {
        el.innerHTML = `🏆 ${esc(por.werdykt)}`;
        el.className = "werdykt-tekst werdykt-zwyciezca";
    }
}

function renderujKarte(prefix, daneJeziora, zwyciezca) {
    const { dane, pogoda, solunar, ocena } = daneJeziora;
    const wynik = ocena.wynik || 0;

    // Klasa zwycięzcy i preferencji
    var jezId = prefix === "w" ? "wulpinskie" : "sarag";
    const karta = document.getElementById("karta-" + jezId);
    if (zwyciezca) karta.classList.add("karta-zwyciezca");
    else karta.classList.remove("karta-zwyciezca");
    var pref = pobierzPreferencje();
    if (pref.jezioro && pref.jezioro === jezId) {
        karta.classList.add("pref-jezioro");
    } else {
        karta.classList.remove("pref-jezioro");
    }

    // Badge wyniku
    const badge = document.getElementById(`wynik-${prefix}-badge`);
    badge.textContent = wynik;
    badge.className = "wynik-badge " + klasaBadge(wynik);

    // Pasek
    const fill = document.getElementById(`fill-${prefix}`);
    setTimeout(() => { fill.style.width = wynik + "%"; }, 100);
    document.getElementById(`wynik-${prefix}-liczba`).textContent = wynik + "/100";

    // (rekomendacja renderowana razem z dopasowaniem preferencji powyżej)

    // Banner "Twoje jezioro" + dopasowanie preferencji
    var rekomEl = document.getElementById("rekomendacja-" + prefix);
    var dopas = ocena.dopasowanie_preferencji;
    var bannerHTML = "";
    if (pref.jezioro === jezId) {
        bannerHTML += '<span class="pref-banner">⭐ Twoje preferowane jezioro</span><br>';
    }
    if (dopas) {
        var klasaDopas = dopas.procent >= 80 ? "dopas-doskonale"
                       : dopas.procent >= 60 ? "dopas-dobre"
                       : dopas.procent >= 40 ? "dopas-srednie"
                       : "dopas-slabe";
        bannerHTML += '<span class="dopas-badge ' + klasaDopas + '">🎯 Dopasowanie do preferencji: '
            + dopas.procent + '% — ' + esc(dopas.opis) + '</span>';
    }
    if (bannerHTML) {
        rekomEl.innerHTML = bannerHTML + "<br>" + esc(ocena.rekomendacja || "–");
    } else {
        rekomEl.textContent = ocena.rekomendacja || "–";
    }

    // Cel chips
    const celEl = document.getElementById(`cel-${prefix}`);
    celEl.innerHTML = "";
    if (ocena.gatunek_cel) celEl.innerHTML += chip(ocena.gatunek_cel, "cel-chip");
    if (ocena.metoda) celEl.innerHTML += chip("⚙ " + ocena.metoda, "cel-chip metoda");
    if (ocena.lowisko) celEl.innerHTML += chip("📍 " + ocena.lowisko, "cel-chip lowisko");
    if (ocena.glebokosc_rekomendowana) celEl.innerHTML += chip("↕ " + ocena.glebokosc_rekomendowana, "cel-chip glebokosc");

    // FIX (ichtiolog): chipy ochrony gatunków
    var ochr = ocena.ochrona;
    var aktMiesiac = daneCache ? daneCache.miesiac : (new Date().getMonth() + 1);
    if (ochr) {
        if (ochr.zakaz) {
            celEl.innerHTML += '<span class="cel-chip chip-zakaz">⛔ ZAKAZ POŁOWU</span>';
        } else if (ochr.okres_ochronny && ochr.okres_ochronny.indexOf(aktMiesiac) !== -1) {
            celEl.innerHTML += '<span class="cel-chip chip-ochron">⚠ Okres ochronny</span>';
        }
        if (ochr.wymiar_cm) {
            celEl.innerHTML += '<span class="cel-chip chip-wymiar">📏 min. ' + ochr.wymiar_cm + ' cm</span>';
        }
    }

    // FIX (UX): ostrzeżenia pod chipami
    var ostrzEl = document.getElementById('ostrzez-' + prefix);
    if (!ostrzEl) {
        ostrzEl = document.createElement('div');
        ostrzEl.id = 'ostrzez-' + prefix;
        celEl.parentNode.insertBefore(ostrzEl, celEl.nextSibling);
    }
    ostrzEl.innerHTML = '';
    (ocena.ostrzezenia || []).forEach(function(o) {
        ostrzEl.innerHTML += '<div class="ostrzezenie-item">' + esc(o) + '</div>';
    });

    // Karta ryby (zdjęcie + % szans)
    _renderujKarteRyby(prefix, ocena.gatunek_cel, ocena.szansa_polowu_proc);

    // Szczegóły — rozbicie
    renderujRozbicie(prefix, ocena.rozbicie);

    // Pogoda
    renderujPogode(prefix, pogoda);

    // Solunar
    renderujSolunar(prefix, solunar);

    // Strefy głębokości
    renderujStrefy(prefix, dane.strefy_glebokosci || []);

    // Łowiska
    renderujLowiska(prefix, dane.lowiska || []);

    // Mapa poglądowa
    renderujMape(prefix, daneJeziora);

    // FIX (frontend dev): jeśli panel szczegółów już otwarty — reinicjuj mapę z nowymi danymi
    var szczegolyEl = document.getElementById('szczegoly-' + jezId);
    if (szczegolyEl && !szczegolyEl.classList.contains('hidden')) {
        pendingMaps[prefix].gotowe = true;
        setTimeout(function() { initLeafletMap(prefix, daneJeziora); }, 60);
    }
}

/* ===== KARTA RYBY — zdjęcie + szansa połowu ===== */
function _renderujKarteRyby(prefix, gatunek, szansa) {
    // Znajdź lub utwórz element karty
    var celEl = document.getElementById('cel-' + prefix);
    if (!celEl) return;

    var kartaId = 'ryba-karta-' + prefix;
    var karta   = document.getElementById(kartaId);
    if (!karta) {
        karta = document.createElement('div');
        karta.id = kartaId;
        karta.className = 'ryba-karta';
        // Wstaw po cel-box i ostrzeżeniach, przed przyciskiem szczegółów
        var btn = celEl.parentNode.querySelector('.btn-szczegoly');
        if (btn) celEl.parentNode.insertBefore(karta, btn);
        else celEl.parentNode.appendChild(karta);
    }

    if (!gatunek || szansa == null) {
        karta.innerHTML = '';
        karta.style.display = 'none';
        return;
    }
    karta.style.display = '';

    // Klasa koloru szansy
    var klasaSz = szansa >= 65 ? 'szansa-dobra'
                : szansa >= 40 ? 'szansa-srednia'
                : 'szansa-slaba';

    // Placeholder dopóki nie załadujemy zdjęcia
    karta.innerHTML = _rybaKartaHTML(prefix, gatunek, szansa, klasaSz, null);

    // Załaduj zdjęcie asynchronicznie
    pobierzZdjecieRyby(gatunek).then(function(url) {
        var imgEl   = document.getElementById('ryba-img-'   + prefix);
        var emojiEl = document.getElementById('ryba-emoji-' + prefix);
        if (!imgEl) return;
        if (url) {
            imgEl.src          = url;
            imgEl.style.display   = 'block';
            if (emojiEl) emojiEl.style.display = 'none';
        }
    });

    // Animuj pasek szansy po chwili
    setTimeout(function() {
        var pasek = document.getElementById('szansa-fill-' + prefix);
        if (pasek) pasek.style.width = szansa + '%';
    }, 120);
}

function _rybaKartaHTML(prefix, gatunek, szansa, klasaSz, imgUrl) {
    var emojiStyle = 'font-size:2.4rem;line-height:1;display:flex;align-items:center;justify-content:center;'
        + 'width:72px;height:72px;background:#f1f5f9;border-radius:8px;flex-shrink:0;';
    return '<img id="ryba-img-' + prefix + '" '
            + 'src="' + (imgUrl || '') + '" '
            + 'alt="' + esc(gatunek) + '" '
            + 'style="width:72px;height:72px;object-fit:cover;border-radius:8px;flex-shrink:0;'
            + 'display:' + (imgUrl ? 'block' : 'none') + '" '
            + 'onerror="this.style.display=\'none\';'
            + 'var e=document.getElementById(\'ryba-emoji-' + prefix + '\');'
            + 'if(e)e.style.display=\'flex\'">'
        + '<span id="ryba-emoji-' + prefix + '" style="' + emojiStyle
            + 'display:' + (imgUrl ? 'none' : 'flex') + '">🐟</span>'
        + '<div class="ryba-info">'
            + '<div class="ryba-nazwa">' + esc(gatunek) + '</div>'
            + '<div class="ryba-szansa-row">'
                + '<span class="szansa-label">Szansa połowu dziś:</span>'
                + '<span class="szansa-badge ' + klasaSz + '">' + szansa + '%</span>'
            + '</div>'
            + '<div class="szansa-pasek-wrap">'
                + '<div class="szansa-fill ' + klasaSz + '" id="szansa-fill-' + prefix + '" style="width:0%"></div>'
            + '</div>'
            + '<div class="szansa-opis">'
                + (szansa >= 65 ? '✔ Dobre warunki na ' + esc(gatunek)
                  : szansa >= 40 ? '~ Przeciętne warunki'
                  : '✘ Niekorzystne warunki dziś') + '</div>'
        + '</div>';
}

/* ===== ROZBICIE PUNKTACJI ===== */
function renderujRozbicie(prefix, rozbicie) {
    if (!rozbicie) return;
    const el = document.getElementById(`rozbicie-${prefix}`);
    const kolejnosc = [
        ["cisnienie", "Ciśnienie", 25],
        ["wiatr", "Wiatr", 20],
        ["temperatura", "Temperatura", 15],
        ["sezon_gatunek", "Sezon/Gatunek", 20],
        ["solunar", "Solunar", 15],
        ["warunki_ogolne", "Warunki ogólne", 5]
    ];

    el.innerHTML = kolejnosc.map(([klucz, etykieta, maks]) => {
        const p = rozbicie[klucz] || { wynik: 0, opis: "" };
        const proc = (p.wynik / maks) * 100;
        const klasaBar = proc >= 75 ? "" : proc >= 40 ? "bar-sredni" : "bar-slaby";
        return `
        <div class="rozbicie-item">
            <span class="rozbicie-label">${esc(etykieta)}</span>
            <div class="rozbicie-bar-wrap">
                <div class="rozbicie-bar ${klasaBar}" style="width:${proc}%"></div>
            </div>
            <span class="rozbicie-wynik">${p.wynik}/${maks}</span>
            <span class="rozbicie-opis">${esc(p.opis || "")}</span>
        </div>`;
    }).join("");
}

/* ===== POGODA ===== */
function renderujPogode(prefix, pogoda) {
    const el = document.getElementById(`pogoda-${prefix}`);
    if (!pogoda || pogoda.blad) {
        el.innerHTML = `<p style="color:#dc2626">${esc(pogoda?.blad || "Brak danych")}</p>`;
        return;
    }

    const a = pogoda.aktualna || {};
    const tend = pogoda.tendencja_cisnienia || {};

    const tendCls = {
        "rosnace": "tend-rosnace",
        "spadajace": "tend-spadajace",
        "stabilne": "tend-stabilne",
        "gwaltowne": "tend-gwaltowne",
        "brak_danych": "tend-stabilne"
    }[tend.ocena] || "tend-stabilne";

    const tendTxt = {
        "rosnace": "Rosnące",
        "spadajace": "Spadające",
        "stabilne": "Stabilne",
        "gwaltowne": "Gwałtowne!",
        "brak_danych": "–"
    }[tend.ocena] || tend.ocena || "–";

    const kafelki = [
        { ikona: "🌡️", wartosc: fmt(a.temperatura_c, "°C"), etykieta: "Temp. powietrza" },
        { ikona: "💧", wartosc: fmt(a.temperatura_wody_c, "°C"), etykieta: "Temp. wody (est.)" },
        { ikona: "🔵", wartosc: fmt(a.cisnienie_hpa, " hPa"), etykieta: "Ciśnienie" },
        { ikona: "💨", wartosc: fmt(a.predkosc_wiatru_kmh, " km/h"), etykieta: "Wiatr" },
        { ikona: "🧭", wartosc: a.kierunek_wiatru_text || "–", etykieta: "Kierunek" },
        { ikona: "☁️", wartosc: fmt(a.zachmurzenie_proc, "%"), etykieta: "Zachmurzenie" },
        { ikona: "🌧️", wartosc: fmt(a.opady_mm, " mm"), etykieta: "Opady" },
        { ikona: "📊", wartosc: tendTxt, etykieta: `Tendencja (${fmt(tend.zmiana_3h, " hPa/3h")})` }
    ];

    el.innerHTML = kafelki.map(k => `
        <div class="pogoda-tile">
            <div class="pogoda-ikona">${k.ikona}</div>
            <div class="pogoda-wartosc">${esc(k.wartosc)}</div>
            <div class="pogoda-etykieta">${esc(k.etykieta)}</div>
            ${k.etykieta.startsWith("Tendencja") ?
                `<span class="tendencja-chip ${tendCls}">${esc(tendTxt)}</span>` : ""}
        </div>`).join("");
}

/* ===== SOLUNAR ===== */
function renderujSolunar(prefix, solunar) {
    const el = document.getElementById(`solunar-${prefix}`);
    if (!solunar) { el.innerHTML = "<p>Brak danych solunarnych</p>"; return; }

    const faza = solunar.faza_ksiezyca || {};
    const ks = fazaKsiężycIkona(faza.oswietlenie_proc);

    el.innerHTML = `
        <div class="solunar-faza">
            <span class="solunar-ksiezyc">${ks.ikona}</span>
            <div>
                <strong>${esc(faza.nazwa || "–")}</strong>
                <div style="font-size:.8rem;opacity:.7">${esc(faza.komentarz || "")}</div>
                <div style="font-size:.8rem;opacity:.7">Oświetlenie: ${fmt(faza.oswietlenie_proc, "%")}</div>
            </div>
            <div style="margin-left:auto;text-align:right;font-size:.8rem;opacity:.75">
                ☀ Wschód ${esc(solunar.wschod_slonca || "–")}<br>
                ☀ Zachód ${esc(solunar.zachod_slonca || "–")}
            </div>
        </div>
        <div class="solunar-okna">
            ${(solunar.okna || []).map(o => {
                const typOkna = o.typ.startsWith("Główne") ? "glowne" :
                                o.typ.startsWith("Mniejsze") ? "mniejsze" : "swit";
                return `
                <div class="okno-item${o.aktywne ? " aktywne" : ""}">
                    <span class="okno-czas">${esc(o.szczyt)}</span>
                    <span class="okno-typ">${esc(o.typ)} (${esc(o.start)}–${esc(o.koniec)})</span>
                    <span class="okno-badge ${o.aktywne ? "aktyw" : typOkna}">
                        ${o.aktywne ? "TERAZ!" : typOkna === "glowne" ? "Główne" : "Mniejsze"}
                    </span>
                </div>`;
            }).join("")}
        </div>
        ${solunar.nastepne_okno && !solunar.aktywne_teraz ? `
        <p style="font-size:.8rem;color:#64748b;margin-top:10px">
            Następne okno: <strong>${esc(solunar.nastepne_okno.szczyt)}</strong>
            — ${esc(solunar.nastepne_okno.typ)}
        </p>` : ""}
    `;
}

/* ===== STREFY GŁĘBOKOŚCI ===== */
function renderujStrefy(prefix, strefy) {
    const el = document.getElementById(`strefy-${prefix}`);
    el.innerHTML = strefy.map((s, i) => `
        <div class="strefa-item">
            <div class="strefa-kolor strefa-${i}"></div>
            <div class="strefa-info">
                <div class="strefa-nazwa">${esc(s.nazwa)}</div>
                <div class="strefa-zakres">${esc(s.zakres_m[0])}–${esc(s.zakres_m[1])} m · ${esc(s.opis)}</div>
            </div>
        </div>`).join("");
}

/* ===== ŁOWISKA ===== */
function renderujLowiska(prefix, lowiska) {
    const el = document.getElementById(`lowiska-${prefix}`);
    el.innerHTML = lowiska.map(l => {
        const gps = l.gps;
        const gpsInfo = gps.placeholder
            ? `<div class="lowisko-gps gps-placeholder">⚠ GPS do uzupełnienia — edytuj jeziora.json</div>`
            : `<div class="lowisko-gps">📍 ${fmt(gps.lat, "°N")}, ${fmt(gps.lon, "°E")}</div>`;
        return `
        <div class="lowisko-item">
            <div class="lowisko-naglowek">
                <span class="lowisko-nazwa">${esc(l.nazwa)}</span>
                <span class="lowisko-id">${esc(l.id)}</span>
            </div>
            <div class="lowisko-opis">${esc(l.opis)}</div>
            <div class="lowiska-gatunki">${(l.gatunki || []).map(g =>
                `<span class="gatunek-tag">${esc(g)}</span>`).join("")}</div>
            ${gpsInfo}
        </div>`;
    }).join("");
}

/* ===== MAPA POGLĄDOWA (Leaflet — dane 1:1 z OpenStreetMap) ===== */

function renderujMape(prefix, daneJeziora) {
    // Tylko zapamiętaj dane — mapa inicjuje się przy pierwszym otwarciu szczegółów
    pendingMaps[prefix] = { dane: daneJeziora, gotowe: false };
}

async function initLeafletMap(prefix, daneJeziora) {
    var jezId  = prefix === 'w' ? 'wulpinskie' : 'sarag';
    var el     = document.getElementById('mapa-' + prefix);
    var legEl  = document.getElementById('mapa-legenda-' + prefix);
    if (!el) return;

    // Usuń poprzednią instancję (np. po odświeżeniu danych)
    if (mapaInstancje[prefix]) {
        mapaInstancje[prefix].remove();
        delete mapaInstancje[prefix];
    }
    el.innerHTML = '';

    var cfg     = LEAFLET_CFG[jezId];
    var lowiska = (daneJeziora.dane && daneJeziora.dane.lowiska) || [];

    // Wszystkie łowiska z jakimikolwiek współrzędnymi (nie 0,0)
    var spotsAll = lowiska.filter(function(l) {
        return l.gps && l.gps.lat !== 0 && l.gps.lon !== 0;
    });
    var spotsPlh = lowiska.filter(function(l) {
        return !l.gps || (l.gps.lat === 0 && l.gps.lon === 0);
    });

    /* Inicjalizacja mapy */
    var mapa = L.map(el, { center: [cfg.lat, cfg.lon], zoom: cfg.zoom, zoomControl: true });
    mapaInstancje[prefix] = mapa;

    /* Warstwy kafelkowe */
    var osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    });
    var satelitaLayer = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '© Esri, Maxar, GeoEye', maxZoom: 18
    });
    var topoLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenTopoMap (CC-BY-SA)', maxZoom: 17
    });

    osmLayer.addTo(mapa);
    L.control.layers(
        { 'Mapa': osmLayer, 'Satelita': satelitaLayer, 'Topografia': topoLayer },
        {},
        { position: 'topright', collapsed: true }
    ).addTo(mapa);

    /* Markery łowisk */
    var bounds = [];
    spotsAll.forEach(function(spot, i) {
        var nr         = i + 1;
        var isPrecise  = !spot.gps.placeholder;
        var isGPX      = spot.id.startsWith('GPX_');
        var fill       = isGPX ? '#f77f00' : (isPrecise ? '#e63946' : '#7c3aed');
        var border     = isPrecise ? 'white' : '#ddd6fe';
        var borderStyle = isPrecise ? 'solid' : 'dashed';
        var label      = isPrecise ? String(nr) : '~';

        var icon = L.divIcon({
            html: '<div style="background:' + fill + ';color:#fff;width:28px;height:28px;'
                + 'border-radius:50%;display:flex;align-items:center;justify-content:center;'
                + 'font-weight:800;font-size:12px;border:2.5px ' + borderStyle + ' ' + border + ';'
                + 'box-shadow:0 2px 6px rgba(0,0,0,.45);line-height:1">' + label + '</div>',
            className: '', iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -16]
        });

        var gl = spot.glebokosc_m && spot.glebokosc_m[0] !== spot.glebokosc_m[1]
            ? spot.glebokosc_m[0] + '–' + spot.glebokosc_m[1] + ' m'
            : (spot.glebokosc_m ? spot.glebokosc_m[0] + ' m' : '');

        var precyzujBtn = '<br><button onclick="_wejdzTrybGPS(\''
            + prefix + '\',\'' + jezId + '\',\'' + esc(spot.id) + '\',\''
            + esc(spot.nazwa.replace(/'/g,"\\'" )) + '\')" '
            + 'style="margin-top:6px;background:#7c3aed;color:#fff;border:none;'
            + 'padding:4px 10px;border-radius:5px;cursor:pointer;font-size:11px;width:100%">'
            + (isPrecise ? '✎ Przesuń marker' : '📍 Ustaw dokładną pozycję') + '</button>';

        var popup = '<div style="font-family:system-ui;max-width:230px;line-height:1.5">'
            + '<strong style="font-size:13px">' + esc(spot.nazwa) + '</strong>';
        if (!isPrecise)
            popup += '<br><span style="color:#7c3aed;font-size:10px">⚠ Pozycja przybliżona</span>';
        if (spot.opis)
            popup += '<br><span style="color:#475569;font-size:11px">' + esc(spot.opis) + '</span>';
        if (gl)
            popup += '<br><span style="color:#0077b6;font-size:11px">Głębokość: ' + gl + '</span>';
        if (spot.gatunki && spot.gatunki.length)
            popup += '<br><span style="color:#2d6a4f;font-size:11px">Gatunki: '
                + esc(spot.gatunki.join(', ')) + '</span>';
        popup += precyzujBtn + '</div>';

        L.marker([spot.gps.lat, spot.gps.lon], { icon: icon })
            .addTo(mapa)
            .bindPopup(popup);
        bounds.push([spot.gps.lat, spot.gps.lon]);
    });

    // Dopasuj widok do wszystkich markerów
    if (bounds.length > 1) {
        mapa.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    }

    /* Pobierz kontur jeziora z Overpass API — nałóż batymietrię */
    // FIX (UX): loader podczas oczekiwania na OSM
    var loaderOSM = L.DomUtil.create('div', 'mapa-osm-loader');
    loaderOSM.id  = 'mapa-osm-loader-' + prefix;
    loaderOSM.innerHTML = '⟳ Pobieranie konturu jeziora z OSM…';
    el.appendChild(loaderOSM);

    pobierzKontourJeziora(cfg.osmQuery).then(function(geojson) {
        var ld = document.getElementById('mapa-osm-loader-' + prefix);
        if (ld) ld.remove();
        if (!geojson) return;
        dodajBatymietrie(mapa, geojson, jezId);
    }).catch(function() {
        var ld = document.getElementById('mapa-osm-loader-' + prefix);
        if (ld) ld.remove();
    });

    /* Legenda łowisk (HTML poniżej mapy) */
    if (!legEl) return;
    var legHTML = '';

    if (spotsAll.length > 0) {
        legHTML += '<div class="mapa-spot-legenda">'
            + '<div class="spot-leg-naglowek">Łowiska na mapie (kliknij marker aby precyzować pozycję):</div>'
            + '<div class="spot-leg-grid">';
        spotsAll.forEach(function(spot, i) {
            var isPrecise = !spot.gps.placeholder;
            var isGPX     = spot.id.startsWith('GPX_');
            var fill      = isGPX ? '#f77f00' : (isPrecise ? '#e63946' : '#7c3aed');
            var label     = isPrecise ? String(i + 1) : '~';
            legHTML += '<div class="spot-leg-item" style="border-left-color:' + fill + '">'
                + '<span class="spot-leg-nr" style="background:' + fill + '">' + label + '</span>'
                + '<div class="spot-leg-info">'
                + '<strong>' + esc(spot.nazwa) + '</strong>'
                + '<span>' + esc((spot.opis || '').substring(0, 70))
                + (spot.opis && spot.opis.length > 70 ? '…' : '') + '</span>'
                + (isPrecise ? '' : '<span style="color:#7c3aed;font-size:.7rem">pozycja przybliżona</span>')
                + '</div></div>';
        });
        legHTML += '</div></div>';
    }
    if (spotsPlh.length > 0) {
        legHTML += '<div class="mapa-plh-box"><span class="mapa-plh-title">⚠ Bez współrzędnych:</span> '
            + spotsPlh.map(function(s) {
                return '<span class="mapa-plh-tag">' + esc(s.nazwa) + '</span>';
            }).join('') + '</div>';
    }
    legEl.innerHTML = legHTML;
}

async function pobierzKontourJeziora(query) {
    var url = 'https://overpass-api.de/api/interpreter?data=' + encodeURIComponent(query);
    var ctrl = new AbortController();
    var tid  = setTimeout(function() { ctrl.abort(); }, 12000);
    try {
        var resp = await fetch(url, { signal: ctrl.signal });
        clearTimeout(tid);
        var data = await resp.json();
        var elementy = (data.elements || []).filter(function(e) {
            return e.type === 'way' && e.geometry && e.geometry.length > 3;
        });
        if (!elementy.length) return null;
        // Użyj pierwszego/największego way
        elementy.sort(function(a, b) { return b.geometry.length - a.geometry.length; });
        var coords = elementy[0].geometry.map(function(pt) { return [pt.lon, pt.lat]; });
        return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } };
    } catch(e) {
        clearTimeout(tid);
        return null;
    }
}

/* ===== BATYMIETRIA (strefy głębokości na mapie) ===== */
function dodajBatymietrie(mapa, kontur, jezId) {
    var cfg = BATYMIETRIA_CFG[jezId];
    if (!cfg) return;

    /* Warstwy od najszerszej (płytkiej) do najwęższej (głębokiej) */
    cfg.strefy.forEach(function(strefa, i) {
        var poly;
        if (i === 0) {
            poly = kontur;
        } else if (typeof turf !== 'undefined') {
            try { poly = turf.buffer(kontur, -strefa.inset_km, { units: 'kilometers' }); }
            catch(e) { poly = null; }
        } else {
            poly = null;
        }
        if (!poly) return;
        L.geoJSON(poly, {
            style: { weight: 0, fillColor: strefa.fill, fillOpacity: 0.70 }
        }).addTo(mapa);
    });

    /* Obrys jeziora na wierzchu */
    L.geoJSON(kontur, {
        style: { color: '#005f8a', weight: 2, fillOpacity: 0, dashArray: '5,4' }
    }).addTo(mapa);

    /* Legenda głębokości — prawy dolny róg */
    var legendCtrl = L.control({ position: 'bottomright' });
    legendCtrl.onAdd = function() {
        var div = L.DomUtil.create('div', 'leaflet-depth-legend');
        div.innerHTML = '<div class="depth-leg-title">Głębokość</div>';
        cfg.strefy.forEach(function(s) {
            div.innerHTML += '<div class="depth-leg-item">'
                + '<span class="depth-leg-swatch" style="background:' + s.fill + '"></span>'
                + '<span>' + esc(s.etykieta) + '</span></div>';
        });
        return div;
    };
    legendCtrl.addTo(mapa);
}

/* ===== UPLOAD GPX ===== */
async function uploadGPX(jeziorId) {
    const prefix = jeziorId === "wulpinskie" ? "w" : "s";
    const input = document.getElementById(`gpx-${prefix}`);
    const wynikEl = document.getElementById(`gpx-${prefix}-wynik`);

    if (!input.files || !input.files[0]) {
        wynikEl.textContent = "Wybierz plik GPX.";
        wynikEl.className = "gpx-wynik blad";
        return;
    }

    const formData = new FormData();
    formData.append("plik", input.files[0]);

    try {
        const resp = await fetch(`/api/upload-gpx/${jeziorId}`, { method: "POST", body: formData });
        const json = await resp.json();
        if (json.sukces) {
            wynikEl.textContent = json.komunikat;
            wynikEl.className = "gpx-wynik";
        } else {
            wynikEl.textContent = "Błąd: " + (json.blad || "nieznany");
            wynikEl.className = "gpx-wynik blad";
        }
    } catch (e) {
        wynikEl.textContent = "Błąd przesyłania: " + e.message;
        wynikEl.className = "gpx-wynik blad";
    }
}

/* ===== TOGGLE SZCZEGÓŁÓW ===== */
function toggleSzczegoly(jeziorId) {
    var el  = document.getElementById('szczegoly-' + jeziorId);
    var btn = el.previousElementSibling;
    var ukryty = el.classList.toggle('hidden');
    btn.textContent = ukryty ? '▼ Szczegóły analizy' : '▲ Zwiń szczegóły';

    var prefix = jeziorId === 'wulpinskie' ? 'w' : 's';
    if (!ukryty) {
        if (pendingMaps[prefix] && !pendingMaps[prefix].gotowe) {
            // Pierwsze otwarcie — zainicjuj mapę Leaflet
            pendingMaps[prefix].gotowe = true;
            initLeafletMap(prefix, pendingMaps[prefix].dane);
        } else if (mapaInstancje[prefix]) {
            // Kolejne otwarcie — odśwież rozmiar (div mógł być ukryty)
            setTimeout(function() { mapaInstancje[prefix].invalidateSize(); }, 60);
        }
    }
}

/* ===== POMOCNICZE ===== */
function pokazLoader(show) {
    document.getElementById("loader").classList.toggle("hidden", !show);
    if (show) document.getElementById("tresc-glowna").classList.add("hidden");
}

function pokazBlad(msg) {
    document.getElementById("blad-tresc").textContent = msg;
    document.getElementById("baner-blad").classList.remove("hidden");
}

function ukryjBlad() {
    document.getElementById("baner-blad").classList.add("hidden");
}

function klasaBadge(wynik) {
    if (wynik >= 80) return "badge-doskonale";
    if (wynik >= 65) return "badge-dobre";
    if (wynik >= 50) return "badge-przecietne";
    if (wynik >= 35) return "badge-slabe";
    return "badge-niezalecane";
}

function fmt(val, jednostka = "") {
    if (val === null || val === undefined) return "–";
    if (typeof val === "number") return val.toFixed(val % 1 === 0 ? 0 : 1) + jednostka;
    return String(val) + jednostka;
}

function chip(tekst, klasy) {
    return `<span class="${klasy}">${esc(tekst)}</span>`;
}

function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function fazaKsiężycIkona(oswietlenie) {
    if (oswietlenie === null || oswietlenie === undefined) return { ikona: "🌑" };
    if (oswietlenie < 6) return { ikona: "🌑" };
    if (oswietlenie < 35) return { ikona: "🌒" };
    if (oswietlenie < 55) return { ikona: "🌓" };
    if (oswietlenie < 80) return { ikona: "🌔" };
    if (oswietlenie < 95) return { ikona: "🌕" };
    return { ikona: "🌕" };
}

/* =====================================================================
   TRYB PRECYZOWANIA GPS ŁOWISKA
   ===================================================================== */

var _gpsMode = null;   // { prefix, jeziorId, lowiskoId, tempMarker }

function _wejdzTrybGPS(prefix, jeziorId, lowiskoId, nazwaLowiska) {
    var mapa = mapaInstancje[prefix];
    if (!mapa) return;

    // Zamknij popup
    mapa.closePopup();

    // Porzuć poprzedni tryb jeśli był aktywny
    _opuscTrybGPS(false);

    _gpsMode = { prefix: prefix, jeziorId: jeziorId, lowiskoId: lowiskoId };

    // Baner instrukcji na mapie
    var baner = document.getElementById('gps-baner-' + prefix);
    if (!baner) {
        baner = document.createElement('div');
        baner.id = 'gps-baner-' + prefix;
        baner.className = 'gps-tryb-baner';
        document.getElementById('mapa-' + prefix).appendChild(baner);
    }
    baner.innerHTML = '📍 Kliknij na mapie aby ustawić <strong>' + esc(nazwaLowiska) + '</strong>'
        + ' &nbsp;<button onclick="_opuscTrybGPS(true)" class="gps-baner-anuluj">✕ Anuluj</button>';
    baner.style.display = 'block';

    // Zmień kursor
    mapa.getContainer().style.cursor = 'crosshair';

    // Jednorazowy nasłuch kliknięcia
    mapa.once('click', function(e) {
        if (!_gpsMode) return;
        var lat = parseFloat(e.latlng.lat.toFixed(6));
        var lon = parseFloat(e.latlng.lng.toFixed(6));
        _zapiszGPSLowiska(prefix, jeziorId, lowiskoId, lat, lon, nazwaLowiska);
    });
}

function _opuscTrybGPS(przywrocKursor) {
    if (!_gpsMode) return;
    var prefix = _gpsMode.prefix;
    var mapa   = mapaInstancje[prefix];
    if (mapa) {
        if (przywrocKursor) mapa.getContainer().style.cursor = '';
        mapa.off('click');  // usuń niezrealizowany nasłuch
    }
    var baner = document.getElementById('gps-baner-' + prefix);
    if (baner) baner.style.display = 'none';
    _gpsMode = null;
}

async function _zapiszGPSLowiska(prefix, jeziorId, lowiskoId, lat, lon, nazwaLowiska) {
    _opuscTrybGPS(true);
    var mapa = mapaInstancje[prefix];

    try {
        var resp = await fetch('/api/lowisko-gps/' + encodeURIComponent(jeziorId)
            + '/' + encodeURIComponent(lowiskoId), {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ lat: lat, lon: lon })
        });
        var json = await resp.json();
        if (!json.sukces) throw new Error(json.blad || 'Błąd serwera');

        // Komunikat sukcesu na chwilę
        if (mapa) {
            var info = L.popup({ closeButton: false, autoClose: true, closeOnClick: true })
                .setLatLng([lat, lon])
                .setContent('<div style="font-size:12px;padding:4px 6px">'
                    + '✅ Pozycja <strong>' + esc(nazwaLowiska) + '</strong> zapisana</div>')
                .openOn(mapa);
            setTimeout(function() { mapa.closePopup(info); }, 2500);
        }

        // Odśwież całą mapę z nowymi danymi
        odswiezDane();

    } catch(e) {
        alert('Błąd zapisu pozycji: ' + e.message);
    }
}

/* =====================================================================
   DZIENNIK POŁOWÓW
   ===================================================================== */

var dziennikAiWynik      = null;   // wynik z Claude Vision
var dziennikZdjecieNazwa = null;   // uuid nazwy pliku na serwerze

// ── Toggle sekcji ────────────────────────────────────────────────────

function toggleDziennik() {
    var panel    = document.getElementById('dziennik-panel');
    var strzalka = document.getElementById('dziennik-strzalka');
    var ukryty   = panel.classList.toggle('hidden');
    strzalka.classList.toggle('open', !ukryty);
    if (!ukryty) zaladujDziennik();
}

// ── Ładowanie danych ─────────────────────────────────────────────────

async function zaladujDziennik() {
    try {
        var resp = await fetch('/api/dziennik/wpisy');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        var json = await resp.json();
        if (!json.sukces) throw new Error(json.blad || 'Błąd serwera');
        renderujListeWpisow(json.wpisy  || []);
        renderujStatystyki (json.statystyki || {});
        aktualizujStatsMini(json.statystyki || {});
    } catch (e) {
        console.error('Błąd dziennika:', e);
    }
}

// ── Formularz ────────────────────────────────────────────────────────

function pokazFormularzWpisu() {
    document.getElementById('dziennik-formularz').classList.remove('hidden');
    // Domyślna data = teraz (lokalny czas)
    var teraz = new Date();
    var local = new Date(teraz.getTime() - teraz.getTimezoneOffset() * 60000)
        .toISOString().slice(0, 16);
    document.getElementById('wpis-data').value = local;
    document.getElementById('dziennik-formularz').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function anulujWpis() {
    document.getElementById('dziennik-formularz').classList.add('hidden');
    _resetujFormularz();
}

function _resetujFormularz() {
    ['wpis-gatunek','wpis-dlugosc','wpis-masa','wpis-jezioro',
     'wpis-metoda','wpis-przyneta','wpis-notatki'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    var cb = document.getElementById('wpis-wypuszczono');
    if (cb) cb.checked = false;
    document.getElementById('dziennik-zdjecie').value = '';
    var img = document.getElementById('foto-img');
    if (img) img.src = '';
    document.getElementById('foto-podglad').classList.add('hidden');
    document.getElementById('ai-wynik-karta').classList.add('hidden');
    document.getElementById('ai-wynik-tresc').classList.add('hidden');
    document.getElementById('ai-wynik-loader').classList.add('hidden');
    document.getElementById('ai-zastosuj-btn').classList.add('hidden');
    dziennikAiWynik      = null;
    dziennikZdjecieNazwa = null;
}

// ── Obsługa zdjęcia + AI ─────────────────────────────────────────────

async function obsluzdZdjecie(plik) {
    if (!plik) return;

    // Podgląd natychmiastowy
    var reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('foto-img').src  = e.target.result;
        document.getElementById('foto-link').href = e.target.result;
        document.getElementById('foto-podglad').classList.remove('hidden');
    };
    reader.readAsDataURL(plik);

    // Pokaż kartę AI z loaderem
    document.getElementById('ai-wynik-karta').classList.remove('hidden');
    document.getElementById('ai-wynik-loader').classList.remove('hidden');
    document.getElementById('ai-wynik-tresc').classList.add('hidden');
    document.getElementById('ai-zastosuj-btn').classList.add('hidden');

    // Wyślij do API
    var fd = new FormData();
    fd.append('zdjecie', plik);
    try {
        var resp = await fetch('/api/dziennik/ocen-ryby', { method: 'POST', body: fd });
        var json = await resp.json();
        document.getElementById('ai-wynik-loader').classList.add('hidden');

        if (json.sukces && json.wynik) {
            dziennikAiWynik      = json.wynik;
            dziennikZdjecieNazwa = json.zdjecie_id || null;
            if (!json.wynik.blad) {
                _renderujAiWynik(json.wynik);
                document.getElementById('ai-zastosuj-btn').classList.remove('hidden');
            } else {
                document.getElementById('ai-wynik-tresc').innerHTML =
                    '<p class="ai-blad">⚠ ' + esc(json.wynik.blad) + '</p>';
                document.getElementById('ai-wynik-tresc').classList.remove('hidden');
            }
        } else {
            document.getElementById('ai-wynik-tresc').innerHTML =
                '<p class="ai-blad">⚠ ' + esc((json.wynik && json.wynik.blad) || json.blad || 'Błąd analizy') + '</p>';
            document.getElementById('ai-wynik-tresc').classList.remove('hidden');
        }
    } catch (e) {
        document.getElementById('ai-wynik-loader').classList.add('hidden');
        document.getElementById('ai-wynik-tresc').innerHTML =
            '<p class="ai-blad">⚠ Błąd połączenia: ' + esc(e.message) + '</p>';
        document.getElementById('ai-wynik-tresc').classList.remove('hidden');
    }
}

function _renderujAiWynik(w) {
    var pelnosc = w.pewnosc === 'wysoka'  ? 'ai-pewnosc-wysoka'  :
                  w.pewnosc === 'srednia' ? 'ai-pewnosc-srednia' : 'ai-pewnosc-niska';

    var dlTxt = (w.dlugosc_cm_min && w.dlugosc_cm_max)
        ? (w.dlugosc_cm_min === w.dlugosc_cm_max
            ? w.dlugosc_cm_min + ' cm'
            : w.dlugosc_cm_min + '–' + w.dlugosc_cm_max + ' cm')
        : '–';

    var spelniaTxt = '';
    if      (w.spelnia_wymiar === true)   spelniaTxt = '<span class="ai-spelnia ok">✓ Spełnia wymiar</span>';
    else if (w.spelnia_wymiar === false)  spelniaTxt = '<span class="ai-spelnia nie">✗ Poniżej wymiaru!</span>';
    else if (w.wymiar_ochronny_cm)        spelniaTxt = '<span class="ai-spelnia brak">? Sprawdź wymiar</span>';

    document.getElementById('ai-wynik-tresc').innerHTML =
        '<div class="ai-wynik-row">'
            + '<span class="ai-wynik-label">Gatunek:</span>'
            + '<span class="ai-gatunek">' + esc(w.gatunek || '–') + '</span>'
        + '</div>'
        + '<div class="ai-wynik-row">'
            + '<span class="ai-wynik-label">Długość:</span>'
            + '<span class="ai-dlugosc">' + esc(dlTxt) + '</span>'
            + spelniaTxt
        + '</div>'
        + (w.wymiar_ochronny_cm
            ? '<div class="ai-wynik-row"><span class="ai-wynik-label">Wymiar ochr.:</span><span>'
              + esc(w.wymiar_ochronny_cm) + ' cm</span></div>'
            : '')
        + '<div class="ai-wynik-row">'
            + '<span class="ai-wynik-label">Pewność:</span>'
            + '<span class="ai-pewnosc ' + pelnosc + '">' + esc(w.pewnosc || '–') + '</span>'
            + '<span class="ai-odniesienie">Ref: ' + esc(w.odniesienie || 'brak') + '</span>'
        + '</div>'
        + (w.opis ? '<div class="ai-opis">' + esc(w.opis) + '</div>' : '');

    document.getElementById('ai-wynik-tresc').classList.remove('hidden');
}

function zastosujAI() {
    if (!dziennikAiWynik) return;
    var w = dziennikAiWynik;

    // Gatunek — szukamy dokładnego dopasowania w select
    if (w.gatunek) {
        var sel = document.getElementById('wpis-gatunek');
        var znaleziono = false;
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].text === w.gatunek || sel.options[i].value === w.gatunek) {
                sel.selectedIndex = i;
                znaleziono = true;
                break;
            }
        }
        if (!znaleziono) sel.value = ''; // nieznany gatunek
    }

    // Długość — średnia z przedziału
    if (w.dlugosc_cm_min) {
        var sr = w.dlugosc_cm_max
            ? Math.round((w.dlugosc_cm_min + w.dlugosc_cm_max) / 2 * 2) / 2  // zaokrągl do 0.5
            : w.dlugosc_cm_min;
        document.getElementById('wpis-dlugosc').value = sr;
    }
}

function usunZdjecie() {
    document.getElementById('dziennik-zdjecie').value = '';
    document.getElementById('foto-img').src = '';
    document.getElementById('foto-link').href = '#';
    document.getElementById('foto-podglad').classList.add('hidden');
    document.getElementById('ai-wynik-karta').classList.add('hidden');
    dziennikAiWynik      = null;
    dziennikZdjecieNazwa = null;
}

// ── Zapis wpisu ──────────────────────────────────────────────────────

async function zapiszWpis() {
    var dl  = document.getElementById('wpis-dlugosc').value;
    var mas = document.getElementById('wpis-masa').value;
    var dane = {
        gatunek:    (document.getElementById('wpis-gatunek').value  || '').trim(),
        dlugosc_cm: dl  ? parseFloat(dl)  : null,
        masa_g:     mas ? parseFloat(mas) : null,
        jezioro:    document.getElementById('wpis-jezioro').value   || '',
        metoda:     document.getElementById('wpis-metoda').value    || '',
        przyneta:   (document.getElementById('wpis-przyneta').value || '').trim(),
        data_polowu: document.getElementById('wpis-data').value     || '',
        notatki:    (document.getElementById('wpis-notatki').value  || '').trim(),
        wypuszczono: document.getElementById('wpis-wypuszczono').checked,
        zdjecie_id: dziennikZdjecieNazwa || null,
    };

    try {
        var resp = await fetch('/api/dziennik/dodaj', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(dane)
        });
        var json = await resp.json();
        if (!json.sukces) throw new Error(json.blad || 'Błąd serwera');
        document.getElementById('dziennik-formularz').classList.add('hidden');
        _resetujFormularz();
        zaladujDziennik();
    } catch (e) {
        alert('Błąd zapisu wpisu: ' + e.message);
    }
}

// ── Usuwanie wpisu ───────────────────────────────────────────────────

async function usunWpis(id) {
    if (!confirm('Usunąć ten wpis z dziennika?')) return;
    try {
        var resp = await fetch('/api/dziennik/usun/' + encodeURIComponent(id), { method: 'DELETE' });
        var json = await resp.json();
        if (!json.sukces) throw new Error(json.blad || 'Błąd');
        // Usuń element z DOM od razu bez pełnego przeładowania
        var el = document.getElementById('wpis-' + id);
        if (el) el.remove();
        zaladujDziennik();   // odśwież statystyki
    } catch (e) {
        alert('Błąd usuwania: ' + e.message);
    }
}

// ── Renderowanie listy wpisów ────────────────────────────────────────

function renderujListeWpisow(wpisy) {
    var el      = document.getElementById('dziennik-lista');
    var pustyEl = document.getElementById('dziennik-pusty');
    if (!wpisy.length) {
        el.innerHTML = '';
        pustyEl.classList.remove('hidden');
        return;
    }
    pustyEl.classList.add('hidden');

    el.innerHTML = wpisy.map(function(w) {
        var gatunek  = w.gatunek || 'Nieznany gatunek';
        var nazwaJez = w.jezioro === 'wulpinskie' ? 'Wulpińskie'
                     : w.jezioro === 'sarag'       ? 'Sarąg'
                     : (w.jezioro || '');
        var dataTxt  = w.data_polowu || w.data_dodania || '';
        var dlTxt    = w.dlugosc_cm ? w.dlugosc_cm + ' cm' : '';
        var masTxt   = w.masa_g
            ? (w.masa_g >= 1000
                ? (w.masa_g / 1000).toFixed(2).replace(/\.?0+$/, '') + ' kg'
                : w.masa_g + ' g')
            : '';
        var crBadge  = w.wypuszczono ? '<span class="cr-badge">C&amp;R</span>' : '';

        var zdjecieHTML = '';
        if (w.zdjecie_id) {
            var url = '/uploads/zdjecia/' + esc(w.zdjecie_id);
            zdjecieHTML = '<a href="' + url + '" target="_blank" class="wpis-thumb-link">'
                + '<img class="wpis-thumb" src="' + url + '" '
                + 'alt="Zdjęcie ' + esc(gatunek) + '" loading="lazy"></a>';
        }

        var tagi = [];
        if (w.metoda)   tagi.push('<span class="wpis-tag tag-metoda">' + esc(w.metoda) + '</span>');
        if (w.przyneta) tagi.push('<span class="wpis-tag tag-przyneta">🪝 ' + esc(w.przyneta) + '</span>');

        var szczegolyEl = '';
        if (dlTxt || masTxt || nazwaJez) {
            szczegolyEl = '<div class="wpis-szczegoly">'
                + (dlTxt    ? '<span>📏 ' + esc(dlTxt)   + '</span>' : '')
                + (masTxt   ? '<span>⚖ '  + esc(masTxt)  + '</span>' : '')
                + (nazwaJez ? '<span>🗺 '  + esc(nazwaJez)+ '</span>' : '')
                + '</div>';
        }
        var notatkiEl = w.notatki
            ? '<div class="wpis-notatki">' + esc(w.notatki) + '</div>' : '';

        return '<div class="wpis-item" id="wpis-' + esc(w.id) + '">'
            + zdjecieHTML
            + '<div class="wpis-tresc">'
                + '<div class="wpis-naglowek">'
                    + '<span class="wpis-gatunek">' + esc(gatunek) + '</span>'
                    + crBadge
                    + '<span class="wpis-data">' + esc(dataTxt) + '</span>'
                    + '<button class="btn-usun-wpis" onclick="usunWpis(\'' + esc(w.id) + '\')" title="Usuń wpis">✕</button>'
                + '</div>'
                + szczegolyEl
                + '<div class="wpis-tagi">' + tagi.join('') + '</div>'
                + notatkiEl
            + '</div>'
        + '</div>';
    }).join('');
}

// ── Renderowanie statystyk ───────────────────────────────────────────

function renderujStatystyki(stats) {
    var el = document.getElementById('dziennik-statystyki');
    if (!stats || !stats.total) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');

    var top3 = Object.entries(stats.gatunki || {}).slice(0, 3)
        .map(function(kv) { return esc(kv[0]) + ' (' + kv[1] + ')'; }).join(', ');

    var rekordHTML = '';
    if (stats.rekord) {
        rekordHTML = '<span class="stat-rekord">🏆 Rekord: <strong>'
            + esc(stats.rekord.gatunek || '?') + ' '
            + esc(String(stats.rekord.dlugosc_cm)) + ' cm</strong></span>';
    }

    el.innerHTML =
        '<div class="stat-kafelek">'
            + '<span class="stat-liczba">' + stats.total + '</span>'
            + '<span class="stat-nazwa">połowów</span>'
        + '</div>'
        + '<div class="stat-kafelek">'
            + '<span class="stat-liczba">' + (stats.sr_dlugosc || '–') + '</span>'
            + '<span class="stat-nazwa">śr. cm</span>'
        + '</div>'
        + '<div class="stat-gatunki">Top: ' + (top3 || '–') + '</div>'
        + rekordHTML;
}

function aktualizujStatsMini(stats) {
    var el = document.getElementById('dziennik-stats-mini');
    if (!el) return;
    el.textContent = stats.total ? stats.total + ' wpisów' : 'brak wpisów';
}
