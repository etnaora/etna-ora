"""
Aggiorna data/hotspot.json con lo stato termico satellitare dell'Etna,
usando il servizio NASA FIRMS (rilevamento anomalie termiche via sensori
VIIRS a bordo dei satelliti Suomi-NPP / NOAA-20 / NOAA-21).

Richiede una chiave gratuita (FIRMS_MAP_KEY), passata come variabile
d'ambiente — su GitHub Actions arriva dal secret omonimo, in locale la
puoi esportare a mano per un test:

    export FIRMS_MAP_KEY="la-tua-chiave"
    python3 scripts/fetch_hotspot.py

Documentazione ufficiale dell'endpoint:
https://firms.modaps.eosdis.nasa.gov/api/area/
"""

import csv
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from json import dumps

import requests

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# Bounding box stretta intorno ai crateri sommitali (poche centinaia di
# metri di raggio reale, ma allargata per sicurezza sulla precisione del
# sensore satellitare): west, south, east, north
AREA = "14.95,37.70,15.05,37.80"

SOURCE = "VIIRS_SNPP_NRT"   # sensore VIIRS, dati quasi in tempo reale
DAY_RANGE = 1                # solo le ultime 24 ore, ci basta per lo stato attuale

# Soglie per decidere lo stato mostrato sul sito (in FRP, "fire radiative
# power", proxy dell'intensità termica rilevata dal satellite, in MW)
SOGLIA_MODERATA = 10
SOGLIA_ALTA = 50

HOTSPOT_PATH = Path(__file__).resolve().parent.parent / "data" / "hotspot.json"


def fetch_hotspots(map_key: str) -> list[dict]:
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{SOURCE}/{AREA}/{DAY_RANGE}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    # Un errore di chiave non valida spesso torna comunque HTTP 200 ma con
    # un corpo di testo che non è un CSV valido: lo intercettiamo a parte.
    text = resp.text.strip()
    if not text or "latitude" not in text.splitlines()[0]:
        raise ValueError(f"Risposta FIRMS inattesa (chiave non valida?): {text[:200]!r}")

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def build_status(rows: list[dict]) -> dict:
    now = datetime.now(timezone.utc)

    if not rows:
        return {
            "generated_at": now.isoformat(),
            "source": "NASA FIRMS (VIIRS_SNPP_NRT) — https://firms.modaps.eosdis.nasa.gov",
            "status": "quiete",
            "notes": "Nessuna anomalia termica rilevata dal satellite nelle ultime 24 ore.",
            "last_significant_event": None,
        }

    max_frp = max(float(r.get("frp", 0) or 0) for r in rows)

    if max_frp >= SOGLIA_ALTA:
        status = "alta"
        notes = f"Anomalia termica significativa rilevata dal satellite (FRP massimo {max_frp:.1f} MW)."
    elif max_frp >= SOGLIA_MODERATA:
        status = "moderata"
        notes = f"Attività termica rilevata dal satellite (FRP massimo {max_frp:.1f} MW)."
    else:
        status = "quiete"
        notes = f"Anomalie termiche minime rilevate (FRP massimo {max_frp:.1f} MW), nella norma del degassamento."

    return {
        "generated_at": now.isoformat(),
        "source": "NASA FIRMS (VIIRS_SNPP_NRT) — https://firms.modaps.eosdis.nasa.gov",
        "status": status,
        "notes": notes,
        "last_significant_event": now.isoformat() if status != "quiete" else None,
        "hotspot_count_24h": len(rows),
    }


def main() -> int:
    map_key = os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        print("Variabile d'ambiente FIRMS_MAP_KEY mancante.", file=sys.stderr)
        return 1

    try:
        rows = fetch_hotspots(map_key)
    except (requests.RequestException, ValueError) as exc:
        print(f"Errore nel contattare NASA FIRMS: {exc}", file=sys.stderr)
        return 1

    status = build_status(rows)
    HOTSPOT_PATH.write_text(dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"hotspot.json aggiornato: stato '{status['status']}', {len(rows)} rilevazioni nelle ultime 24h.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
