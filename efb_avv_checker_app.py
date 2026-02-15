# efb_avv_checker_app.py
# Streamlit App: EfB-Check AVV je Standort (SQLite) + Karte ohne Google API
#
# Start:
#   pip install -r requirements.txt
#   streamlit run efb_avv_checker_app.py
#
# Hinweis:
# - Die App erwartet eine Datei "efb_avv.db" im selben Ordner.
# - Das Logo ist fest: "logo.png" im selben Ordner (austauschbar durch Datei ersetzen).

from __future__ import annotations

import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

import streamlit as st
import requests
import folium
from streamlit_folium import st_folium


DB_FILENAME = "efb_avv.db"
LOGO_FILENAME = "logo.png"
BRAND_NAME = "BioCycling"
APP_TITLE = "EfB-Check: AVV je Standort"


# ----------------------------
# Basics
# ----------------------------

def normalize_avv(s: str) -> Optional[str]:
    digits = re.sub(r"\D", "", s or "")
    if len(digits) == 6:
        return digits
    if len(digits) == 5:
        return digits.zfill(6)
    return None


def inject_css():
    # Moderner Hintergrund mit Grid + Glow
    st.markdown(
        """
        <style>
          :root{
            --bg: #070b12;
            --panel: rgba(255,255,255,0.06);
            --panel2: rgba(255,255,255,0.08);
            --text: rgba(255,255,255,0.92);
            --muted: rgba(255,255,255,0.64);
            --border: rgba(255,255,255,0.10);
            --accent: #2dd4bf;
            --good: #22c55e;
            --bad: #ef4444;
          }

          html, body, [class*="css"] { color: var(--text); }

          .stApp {
            background:
              radial-gradient(900px 600px at 20% 0%, rgba(45,212,191,0.12), transparent 60%),
              radial-gradient(900px 600px at 80% 10%, rgba(99,102,241,0.12), transparent 60%),
              linear-gradient(to bottom, rgba(255,255,255,0.03), transparent 35%),
              /* Grid pattern */
              linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px),
              var(--bg);
            background-size:
              auto,
              auto,
              auto,
              48px 48px,
              48px 48px,
              auto;
            background-position:
              center,
              center,
              center,
              0 0,
              0 0,
              center;
          }

          section[data-testid="stSidebar"] {
            background: rgba(255,255,255,0.03);
            border-right: 1px solid var(--border);
          }

          .block-container { padding-top: 1.4rem; padding-bottom: 2.0rem; }

          h1 { font-weight: 780; letter-spacing: .2px; margin-bottom: 0.2rem; }
          h2 { font-weight: 700; }
          h3 { font-weight: 650; }

          .bc-card{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 16px 18px;
            box-shadow: 0 14px 40px rgba(0,0,0,0.25);
          }
          .bc-kicker { font-size: 0.9rem; color: var(--muted); margin-bottom: 6px; }
          .bc-title { font-size: 1.15rem; font-weight: 720; margin: 0 0 6px 0; }
          .bc-sub { color: var(--muted); font-size: 0.95rem; line-height: 1.45; }

          .bc-status{
            border-radius: 18px;
            padding: 16px 18px;
            border: 1px solid var(--border);
            background: var(--panel2);
          }
          .bc-status.good { border-left: 6px solid var(--good); }
          .bc-status.bad  { border-left: 6px solid var(--bad); }
          .bc-status .big { font-size: 1.2rem; font-weight: 820; margin-bottom: 6px; }
          .bc-status .small { color: var(--muted); font-size: 0.95rem; }

          div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
          }

          input, textarea { border-radius: 14px !important; }

          .stButton button {
            border-radius: 14px;
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.06);
          }
          .stButton button:hover { border-color: rgba(45,212,191,0.55); }

          .bc-footer { color: var(--muted); font-size: 0.85rem; margin-top: 10px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_block(ok: bool, headline: str, detail: str):
    cls = "good" if ok else "bad"
    st.markdown(
        f"""
        <div class="bc-status {cls}">
          <div class="big">{headline}</div>
          <div class="small">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_logo_bytes() -> Optional[bytes]:
    try:
        here = os.path.dirname(__file__)
        p = os.path.join(here, LOGO_FILENAME)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
    except Exception:
        return None
    return None


def render_header(logo_bytes: Optional[bytes], meta_source: str):
    left, right = st.columns([1, 3], vertical_alignment="center")
    with left:
        if logo_bytes:
            st.image(logo_bytes, use_container_width=True)
        else:
            st.markdown(
                "<div class='bc-card'><div class='bc-title'>EfB • AVV</div><div class='bc-sub'>Checker</div></div>",
                unsafe_allow_html=True,
            )
    with right:
        st.markdown(f"<div class='bc-kicker'>{BRAND_NAME}</div>", unsafe_allow_html=True)
        st.markdown("<h1 style='margin-top:0.15rem'>EfB-Check: AVV je Standort</h1>", unsafe_allow_html=True)
        if meta_source:
            st.markdown(f"<div class='bc-sub'>Datenquelle: {meta_source}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='bc-sub'>Standort auswählen → AVV eingeben → Sofort-Check</div>", unsafe_allow_html=True)


def build_site_label(ort: str, bundesland: str, annex: int) -> str:
    ort = ort or "—"
    bundesland = bundesland or ""
    return f"{ort} ({bundesland}) • Anlage {annex}"


def full_address(strasse: str, plz: str, ort: str, bundesland: str) -> str:
    parts = []
    if strasse:
        parts.append(strasse)
    line2 = " ".join([p for p in [plz, ort] if p])
    if line2:
        parts.append(line2)
    if bundesland:
        parts.append(bundesland)
    parts.append("Deutschland")
    return ", ".join(parts)


# ----------------------------
# DB Access
# ----------------------------

@st.cache_resource(show_spinner=False)
def open_db(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def db_get_meta(con: sqlite3.Connection) -> Dict[str, str]:
    cur = con.cursor()
    cur.execute("SELECT k,v FROM meta")
    return {r["k"]: r["v"] for r in cur.fetchall()}


def db_list_sites(con: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, annex, pages_start, pages_end, bezeichnung, strasse, plz, ort, bundesland, taetigkeit, lat, lon
        FROM sites
        ORDER BY ort, annex
        """
    )
    return cur.fetchall()


def db_get_avv_for_site(con: sqlite3.Connection, site_id: int) -> List[sqlite3.Row]:
    cur = con.cursor()
    cur.execute("SELECT code, text FROM avv WHERE site_id=? ORDER BY code", (site_id,))
    return cur.fetchall()


def db_find_avv(con: sqlite3.Connection, site_id: int, code: str) -> Optional[sqlite3.Row]:
    cur = con.cursor()
    cur.execute("SELECT code, text FROM avv WHERE site_id=? AND code=? LIMIT 1", (site_id, code))
    return cur.fetchone()


def suggest_similar(rows: List[sqlite3.Row], avv_code: str, limit: int = 10) -> List[sqlite3.Row]:
    chap = avv_code[:2]
    group = avv_code[:4]
    same_group = [r for r in rows if str(r["code"]).startswith(group)]
    same_chap = [r for r in rows if str(r["code"]).startswith(chap)]
    out = same_group + [r for r in same_chap if r not in same_group]
    return out[:limit]


# ----------------------------
# Geocoding (ohne API-Key)
# ----------------------------

@st.cache_data(show_spinner=False, ttl=60 * 60 * 24 * 14)  # 14 Tage
def nominatim_geocode(address: str) -> Optional[Tuple[float, float]]:
    """
    Kostenloses Geocoding über OpenStreetMap Nominatim.
    Achtung: Rate-Limits beachten (Caching reduziert Calls).
    """
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "EfB-AVV-Checker/1.0 (internal use)"}
    r = requests.get(url, params={"q": address, "format": "json", "limit": 1}, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def make_map(lat: float, lon: float, tile_style: str) -> folium.Map:
    m = folium.Map(location=[lat, lon], zoom_start=16, control_scale=True, tiles=None)

    # Basemaps ohne Key
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
        control=True,
    ).add_to(m)

    # Satellit (Esri) ohne Key (public tiles; Nutzung gemäß Esri/ArcGIS Terms)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Satellit (Esri)",
        attr="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        control=True,
    ).add_to(m)

    if tile_style == "Satellit (Esri)":
        # initial layer selection: not perfect in folium, but we can add layers then user can toggle
        pass

    folium.Marker([lat, lon], tooltip="Anlage", icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


# ----------------------------
# App
# ----------------------------

st.set_page_config(page_title=APP_TITLE, page_icon="✅", layout="wide")
inject_css()

with st.sidebar:
    st.markdown("### Eingabe")
    avv_input = st.text_input("AVV-Abfallschlüssel", value="20 01 08", help="Beispiele: 20 01 08 / 200108 / 20.01.08")
    st.markdown("---")
    st.markdown("### Karte")
    show_map = st.toggle("Karte anzeigen", value=True)
    tile_style = st.selectbox("Kartenstil", ["OpenStreetMap", "Satellit (Esri)"], index=0)
    st.caption("Ohne Google API: Geocoding via OpenStreetMap (Nominatim) + Kartenlayer via OSM/Esri.")

# Locate DB in app directory
here = os.path.dirname(__file__)
db_path = os.path.join(here, DB_FILENAME)

if not os.path.exists(db_path):
    st.markdown(
        "<div class='bc-card'><div class='bc-title'>Datenbank fehlt</div>"
        f"<div class='bc-sub'>Ich finde <code>{DB_FILENAME}</code> nicht im App-Ordner.</div></div>",
        unsafe_allow_html=True,
    )
    st.stop()

con = open_db(db_path)
meta = db_get_meta(con)
sites = db_list_sites(con)

logo_bytes = load_logo_bytes()
render_header(logo_bytes, meta.get("source_pdf", ""))

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

if not sites:
    st.markdown(
        "<div class='bc-card'><div class='bc-title'>Keine Standorte in der DB</div>"
        "<div class='bc-sub'>Die Datenbank enthält keine Sites.</div></div>",
        unsafe_allow_html=True,
    )
    st.stop()

labels = [build_site_label(s["ort"], s["bundesland"], s["annex"]) for s in sites]
label_to_site = {labels[i]: sites[i] for i in range(len(sites))}

tab_check, tab_standorte = st.tabs(["✅ Check", "📍 Standorte & AVV-Liste"])

with tab_check:
    colL, colR = st.columns([2, 3], gap="large")

    with colL:
        st.markdown("<div class='bc-card'>", unsafe_allow_html=True)
        site_label = st.selectbox("Standort auswählen (Biogasanlagen)", labels, index=0)
        site = label_to_site[site_label]

        stnd_title = f"{site['ort'] or '—'} ({site['bundesland'] or ''})"
        st.markdown("<div class='bc-kicker'>Standort</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='bc-title'>{stnd_title}</div>", unsafe_allow_html=True)

        addr = full_address(site["strasse"], site["plz"], site["ort"], site["bundesland"])
        st.markdown(f"<div class='bc-sub'>{addr}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='bc-sub' style='margin-top:8px'><b>Anlage {site['annex']}</b> • Seiten {site['pages_start']}–{site['pages_end']}</div>",
            unsafe_allow_html=True,
        )

        if site["taetigkeit"]:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            st.markdown("<div class='bc-kicker'>Tätigkeitsbeschreibung (Auszug)</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='bc-sub'>{site['taetigkeit']}</div>", unsafe_allow_html=True)

        if show_map:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            st.markdown("<div class='bc-kicker'>Karte</div>", unsafe_allow_html=True)

            lat = site["lat"]
            lon = site["lon"]

            if lat is None or lon is None:
                try:
                    with st.spinner("Adresse wird geocodiert (OpenStreetMap)…"):
                        coords = nominatim_geocode(addr)
                    if coords:
                        lat, lon = coords
                except Exception as e:
                    st.warning(f"Geocoding fehlgeschlagen: {e}")

            if lat is None or lon is None:
                st.info("Koordinaten konnten nicht ermittelt werden. Ich zeige Links zur Karten-Öffnung.")
                st.markdown(f"[In OpenStreetMap öffnen](https://www.openstreetmap.org/search?query={requests.utils.quote(addr)})")
                st.markdown(f"[In Google Maps öffnen](https://www.google.com/maps/search/?api=1&query={requests.utils.quote(addr)})")
            else:
                m = make_map(float(lat), float(lon), tile_style)
                st_folium(m, use_container_width=True, height=460)

        st.markdown("</div>", unsafe_allow_html=True)

        rows_all = db_get_avv_for_site(con, int(site["id"]))
        s1, s2 = st.columns(2)
        with s1:
            st.metric("Freigegebene AVV", value=len(rows_all))
        with s2:
            with_hint = sum(1 for r in rows_all if (r["text"] or "").strip())
            st.metric("mit Hinweistext", value=with_hint)

    with colR:
        st.markdown("<div class='bc-card'>", unsafe_allow_html=True)
        st.markdown("<div class='bc-kicker'>AVV-Check</div>", unsafe_allow_html=True)

        avv_norm = normalize_avv(avv_input)
        if not avv_norm:
            status_block(False, "Ungültige Eingabe", "Bitte einen AVV-Abfallschlüssel mit 6 Ziffern eingeben (z. B. 200108).")
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

        match = db_find_avv(con, int(site["id"]), avv_norm)

        if match:
            status_block(True, f"✅ POSITIV: {avv_norm}", f"Der AVV ist am Standort „{site_label}“ im EfB enthalten.")
            if match["text"]:
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                st.markdown("<div class='bc-kicker'>Beschreibung / Einschränkungen (aus dem Zertifikat)</div>", unsafe_allow_html=True)
                st.info(match["text"])
        else:
            status_block(False, f"❌ NEGATIV: {avv_norm}", f"Der AVV ist am Standort „{site_label}“ nicht aufgeführt.")

            suggestions = suggest_similar(rows_all, avv_norm)
            if suggestions:
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                st.markdown("<div class='bc-kicker'>Ähnliche AVV am Standort (Hinweis)</div>", unsafe_allow_html=True)
                st.dataframe(
                    [{"AVV": r["code"], "Hinweis": (r["text"] or "")[:250]} for r in suggestions],
                    use_container_width=True,
                    hide_index=True,
                )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        with st.expander("Alle am Standort freigegebenen AVV anzeigen", expanded=False):
            filt = st.text_input("Filter (Code oder Text)", value="", key="filter_all_avv")
            rows = rows_all
            if filt.strip():
                f = filt.strip().lower()
                rows = [r for r in rows if f in str(r["code"]).lower() or f in (r["text"] or "").lower()]
            st.dataframe(
                [{"AVV": r["code"], "Hinweis": r["text"] or ""} for r in rows],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='bc-footer'>Hinweis: Das Tool prüft ausschließlich, ob der AVV-Code im EfB-Zertifikat am gewählten Standort aufgeführt ist. "
        "Weitere Anforderungen (Annahmekriterien, Genehmigungen, Sperrlisten, Kundenfreigaben usw.) sind separat zu prüfen.</div>",
        unsafe_allow_html=True,
    )

with tab_standorte:
    st.markdown("<div class='bc-card'>", unsafe_allow_html=True)
    st.markdown("<div class='bc-title'>Standorte in der Datenbank</div>", unsafe_allow_html=True)
    st.markdown("<div class='bc-sub'>Übersicht inkl. AVV-Anzahl und Adresse.</div>", unsafe_allow_html=True)

    overview = []
    for s in sites:
        rows = db_get_avv_for_site(con, int(s["id"]))
        overview.append(
            {
                "Standort": (s["ort"] or "—"),
                "BL": (s["bundesland"] or ""),
                "Anlage": s["annex"],
                "Seiten": f"{s['pages_start']}–{s['pages_end']}",
                "AVV-Anzahl": len(rows),
                "Adresse": full_address(s["strasse"], s["plz"], s["ort"], s["bundesland"]),
            }
        )
    st.dataframe(overview, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)
