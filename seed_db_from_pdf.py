# seed_db_from_pdf.py
# Build efb_avv.db from an EfB certificate PDF (PyMuPDF).
#
# Usage:
#   python seed_db_from_pdf.py --pdf "EFB.pdf" --out "efb_avv.db"

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF


def normalize_avv(s: str) -> Optional[str]:
    digits = re.sub(r"\D", "", s or "")
    if len(digits) == 6:
        return digits
    if len(digits) == 5:
        return digits.zfill(6)
    return None


def parse_codes_with_context(text: str) -> List[Dict[str, str]]:
    lines = [ln.strip() for ln in text.splitlines()]
    entries: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None

    ignore = {
        "Abfallschlüssel",
        "(ggf. mit „*“-Eintrag)",
        "Abfallbezeichnung",
        "Einschränkungen/Bemerkungen",
        "4. Abfallarten nach dem Anhang zur AVV:",
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "alle Abfallarten",
        "alle nicht gefährlichen Abfälle",
        "alle gefährlichen Abfälle",
        "bestimmte Abfallarten",
    }

    for ln in lines:
        if not ln:
            continue
        if ln.startswith("Seite "):
            continue

        m = re.match(r"^(\d{2}\s?\d{2}\s?\d{2}|\d{6})(\*?)$", ln)
        if m:
            code = normalize_avv(m.group(1))
            if code and 1 <= int(code[:2]) <= 20:
                if current:
                    entries.append(current)
                current = {"code": code, "text": ""}
            continue

        m = re.match(r"^(\d{2}\s?\d{2}\s?\d{2}|\d{6})(\*?)\s+(.+)$", ln)
        if m:
            code = normalize_avv(m.group(1))
            if code and 1 <= int(code[:2]) <= 20:
                if current:
                    entries.append(current)
                current = {"code": code, "text": m.group(3).strip()}
            continue

        if current:
            if ln in ignore:
                continue
            current["text"] = (current["text"] + " " + ln).strip()

    if current:
        entries.append(current)

    seen = set()
    out: List[Dict[str, str]] = []
    for e in entries:
        if e["code"] not in seen:
            seen.add(e["code"])
            out.append(e)
    return out


def parse_beiblatt(text: str, annex_no: int) -> Dict[str, str]:
    beiblatt: Dict[str, str] = {}
    pattern = r"Beiblatt Einschränkungen/Bemerkungen\s+" + str(annex_no) + r".*?\n"
    parts = re.split(pattern, text)
    if len(parts) <= 1:
        return {}

    for part in parts[1:]:
        block = re.split(r"\nSeite|\n2\. |\nAnlage \d+ zum Zertifikat", part)[0]
        lines = [ln.strip() for ln in block.splitlines()]

        current: Optional[str] = None
        buf: List[str] = []

        for ln in lines:
            if not ln:
                continue
            m = re.match(r"^(\d{2}\s?\d{2}\s?\d{2}|\d{6})(\*?)\s*(.*)$", ln)
            code = normalize_avv(m.group(1)) if m else None
            if code:
                if current:
                    beiblatt[current] = (beiblatt.get(current, "") + " " + " ".join([b for b in buf if b])).strip()
                current = code
                tail = (m.group(3) or "").strip()
                buf = [tail] if tail else []
            else:
                if current:
                    buf.append(ln)

        if current:
            beiblatt[current] = (beiblatt.get(current, "") + " " + " ".join([b for b in buf if b])).strip()

    return {k: v for k, v in beiblatt.items() if v}


def extract_annex_start_pages(doc: "fitz.Document") -> List[Tuple[int, int]]:
    occ = []
    for i in range(len(doc)):
        txt = doc[i].get_text("text")
        m = re.search(r"Anlage\s+(\d+)\s+zum Zertifikat", txt)
        if m:
            occ.append((int(m.group(1)), i + 1))
    return sorted(occ)


def parse_annex(doc: "fitz.Document", annex_no: int, start_page: int, end_page: int) -> Dict:
    text = "\n".join(doc[p - 1].get_text("text") for p in range(start_page, end_page + 1))

    def extract(pattern: str) -> Optional[str]:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    standort = {
        "bezeichnung": extract(r"1\.1\s+Bezeichnung des Standorts:\s*(.+)"),
        "strasse": extract(r"1\.2\s+Straße:\s*(.+)"),
        "plz": extract(r"Postleitzahl:\s*(\d{4,5})"),
        "ort": (extract(r"Ort:\s*([A-Za-zÄÖÜäöüß\-/\.\s]+)") or "").strip() or None,
        "bundesland": extract(r"Bundesland:\s*([A-Z]{2})"),
    }

    m = re.search(r"3\.\s+Beschreibung.*?:\s*\n(.+?)(?:\nSeite|\n4\.)", text, flags=re.S)
    taetigkeit = " ".join(line.strip() for line in m.group(1).splitlines() if line.strip()) if m else None

    codes = parse_codes_with_context(text)
    beiblatt = parse_beiblatt(text, annex_no)

    avv = []
    for c in codes:
        t = c["text"]
        if c["code"] in beiblatt:
            t = (t + " | " if t else "") + f"Beiblatt: {beiblatt[c['code']]}"
        avv.append({"code": c["code"], "text": t})

    return {
        "annex": annex_no,
        "pages": [start_page, end_page],
        "standort": standort,
        "taetigkeit": taetigkeit,
        "avv": avv,
    }


def is_biogas_site(taetigkeit: Optional[str]) -> bool:
    if not taetigkeit:
        return False
    d = taetigkeit.lower()
    return any(k in d for k in ["biogasanlage", "vergärungsanlage", "trockenvergärung", "nass-", "abfallvergärungsanlage"])


def build_db(out_path: str, source_pdf: str, sites: List[Dict]):
    con = sqlite3.connect(out_path)
    cur = con.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode=WAL;
        DROP TABLE IF EXISTS meta;
        DROP TABLE IF EXISTS sites;
        DROP TABLE IF EXISTS avv;

        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);

        CREATE TABLE sites (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          annex INTEGER,
          pages_start INTEGER,
          pages_end INTEGER,
          bezeichnung TEXT,
          strasse TEXT,
          plz TEXT,
          ort TEXT,
          bundesland TEXT,
          taetigkeit TEXT,
          lat REAL,
          lon REAL
        );

        CREATE TABLE avv (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          site_id INTEGER NOT NULL,
          code TEXT NOT NULL,
          text TEXT,
          FOREIGN KEY(site_id) REFERENCES sites(id)
        );

        CREATE INDEX idx_avv_site_code ON avv(site_id, code);
        """
    )
    cur.execute("INSERT INTO meta(k,v) VALUES (?,?)", ("source_pdf", source_pdf))
    cur.execute("INSERT INTO meta(k,v) VALUES (?,?)", ("generated_at_utc", dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"))

    for s in sites:
        stnd = s["standort"]
        cur.execute(
            """
            INSERT INTO sites(annex,pages_start,pages_end,bezeichnung,strasse,plz,ort,bundesland,taetigkeit,lat,lon)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                s.get("annex"),
                s.get("pages", [None, None])[0],
                s.get("pages", [None, None])[1],
                stnd.get("bezeichnung"),
                stnd.get("strasse"),
                stnd.get("plz"),
                stnd.get("ort"),
                stnd.get("bundesland"),
                s.get("taetigkeit"),
                None,
                None,
            ),
        )
        site_id = cur.lastrowid
        for row in s.get("avv", []):
            cur.execute("INSERT INTO avv(site_id,code,text) VALUES (?,?,?)", (site_id, row.get("code"), row.get("text")))
    con.commit()
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="Pfad zur EfB-PDF")
    ap.add_argument("--out", default="efb_avv.db", help="Ausgabe DB (SQLite)")
    ap.add_argument("--source", default="", help="Optionale Quellenbeschreibung (z. B. Zertifikatsnummer)")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)

    occ = extract_annex_start_pages(doc)
    annexes = []
    for idx, (annex_no, start_pg) in enumerate(occ):
        end_pg = (occ[idx + 1][1] - 1) if idx + 1 < len(occ) else len(doc)
        annexes.append(parse_annex(doc, annex_no, start_pg, end_pg))

    biogas = [a for a in annexes if is_biogas_site(a.get("taetigkeit"))]

    source = args.source.strip() or os.path.basename(args.pdf)
    build_db(args.out, source, biogas)
    print(f"DB erstellt: {args.out} (Standorte: {len(biogas)})")


if __name__ == "__main__":
    import os
    main()
