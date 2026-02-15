# EfB-AVV Checker (Streamlit) – lokale DB + Karte ohne Google API

## Was macht das Tool?
- Standort auswählen + AVV eingeben → ✅/❌, ob der AVV-Code am Standort im EfB-Zertifikat enthalten ist.
- Anzeige von Adresse & Tätigkeitsbeschreibung.
- Karte ohne Google API: **Geocoding via OpenStreetMap (Nominatim)** + Kartenlayer via **OpenStreetMap/Esri**.

## Start
```bash
pip install -r requirements.txt
streamlit run efb_avv_checker_app.py
```

## Datenquelle / DB
- Die App nutzt **efb_avv.db** (SQLite) im selben Ordner.
- Bei neuem EfB-Zertifikat: `seed_db_from_pdf.py` verwenden (liegt im Paket).

## Logo
- Das Logo ist **fest**: `logo.png` im selben Ordner.
- Wenn ihr euer Firmenlogo nutzen wollt: Datei einfach durch euer `logo.png` ersetzen (gleiches Dateinamenschema).
