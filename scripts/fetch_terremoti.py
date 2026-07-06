"""
Aggiorna data/feed.json con gli ultimi terremoti dell'area etnea, presi dal
webservice ufficiale INGV (FDSN event), licenza CC-BY 4.0.

Pensato per essere eseguito periodicamente da GitHub Actions (vedi
.github/workflows/update-feed.yml), ma è un normale script Python:
si può lanciare anche a mano per testarlo, una volta che gira su una rete
che raggiunge webservices.ingv.it (qui in sandbox non è raggiungibile).

    python3 scripts/fetch_terremoti.py

Non tocca gli item di tipo diverso da 'sismicita' già presenti nel feed
(tremore, comunicati, bollettini verranno aggiunti da script analoghi):
li rilegge, li mescola con i nuovi terremoti, ordina per data decrescente
e taglia a MAX_ITEMS.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

INGV_ENDPOINT = "https://webservices.ingv.it/fdsnws/event/1/query"

# Bounding box che copre l'edificio vulcanico etneo e le zone sismogenetiche
# limitrofe (versante nord, ionico, Val di Noto). Volutamente un po' largo:
# meglio scartare qualche evento marginale dopo che perdere eventi veri.
BBOX = {
    "minlatitude": 37.55,
    "maxlatitude": 37.95,
    "minlongitude": 14.75,
    "maxlongitude": 15.25,
}

MIN_MAGNITUDE = 1.0      # sotto 1.0 il rumore è troppo alto per un pubblico non tecnico
LOOKBACK_DAYS = 14        # quanto indietro guardare a ogni esecuzione
MAX_ITEMS = 25            # finestra fissa del feed, come deciso nel progetto

FEED_PATH = Path(__file__).resolve().parent.parent / "data" / "feed.json"


def parse_ingv_time(raw) -> str:
    """Normalizza il campo 'time' del geojson INGV in una stringa ISO UTC.

    In pratica INGV lo restituisce come stringa (es. '2026-06-15T12:28:45.130Z'),
    ma per sicurezza gestiamo anche il caso in cui arrivi come epoch numerico
    (ms), così lo script non si rompe se il formato cambia di nuovo in futuro.
    """
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).isoformat()

    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # fallback estremo: tronca i microsecondi se il formato non standard fallisce
        dt = datetime.fromisoformat(text.split(".")[0] + "+00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def fetch_new_events() -> list[dict]:
    """Interroga INGV e restituisce una lista di item nel formato del feed."""
    starttime = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "format": "geojson",
        "starttime": starttime,
        "minmagnitude": MIN_MAGNITUDE,
        **BBOX,
        "orderby": "time",
    }

    resp = requests.get(INGV_ENDPOINT, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    items = []
    for feature in payload.get("features", []):
        props = feature["properties"]
        event_id = str(feature.get("id") or props.get("eventId"))
        ts = parse_ingv_time(props["time"])
        mag = props.get("mag")
        place = props.get("place") or "area etnea"

        items.append({
            "id": f"eq-{event_id}",
            "timestamp": ts,
            "type": "sismicita",
            "title": f"Evento sismico Ml {mag:.1f}" if mag is not None else "Evento sismico",
            "summary": f"Localizzato: {place}.",
            "level": "alto" if (mag or 0) >= 3.0 else ("medio" if (mag or 0) >= 2.0 else "basso"),
        })
    return items


def load_existing_feed() -> dict:
    if FEED_PATH.exists():
        return json.loads(FEED_PATH.read_text(encoding="utf-8"))
    return {"items": []}


def merge_and_trim(existing_items: list[dict], new_events: list[dict]) -> list[dict]:
    # Rimuove i vecchi item di tipo 'sismicita' (verranno sostituiti dai nuovi,
    # evitando duplicati se un evento viene rivisto da INGV) e tiene il resto.
    others = [it for it in existing_items if it.get("type") != "sismicita"]

    # Deduplica per id, i nuovi vincono sui vecchi in caso di revisione
    by_id = {it["id"]: it for it in others}
    for ev in new_events:
        by_id[ev["id"]] = ev

    merged = list(by_id.values())
    merged.sort(key=lambda it: it["timestamp"], reverse=True)
    return merged[:MAX_ITEMS]


def main() -> int:
    try:
        new_events = fetch_new_events()
    except requests.RequestException as exc:
        print(f"Errore nel contattare INGV: {exc}", file=sys.stderr)
        return 1

    feed = load_existing_feed()
    feed["items"] = merge_and_trim(feed.get("items", []), new_events)
    feed["generated_at"] = datetime.now(timezone.utc).isoformat()
    feed["source"] = "INGV Osservatorio Etneo — webservice FDSN event (CC-BY 4.0)"
    feed["max_items"] = MAX_ITEMS

    FEED_PATH.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"feed.json aggiornato: {len(feed['items'])} elementi, {len(new_events)} nuovi eventi sismici trovati.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
