"""
Aggiorna data/feed.json con gli ultimi comunicati ufficiali INGV sull'Etna
(comunicati di attività vulcanica, non i bollettini settimanali), letti
dalla pagina pubblica della Sala Operativa dell'Osservatorio Etneo.

La pagina non espone un'API strutturata (JSON/RSS), quindi qui si fa un
piccolo "scraping" leggero della sua tabella HTML — per questo lo script
è scritto per essere tollerante a piccole variazioni di formato: se la
struttura della pagina cambia in modo sostanziale andrà comunque rivista,
ma non dovrebbe rompersi per dettagli minori.

    python3 scripts/fetch_comunicati.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

INGV_PAGE = "https://www.ct.ingv.it/sezioniesterne/Comunicati/ComunicatiVulcanici.php?I=0"

MAX_ITEMS = 25
FEED_PATH = Path(__file__).resolve().parent.parent / "data" / "feed.json"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")


def fetch_comunicati_etna() -> list[dict]:
    resp = requests.get(INGV_PAGE, timeout=20, headers={"User-Agent": "etna-ora-bot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for link in soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE)):
        href = link.get("href", "")
        if "ETNA" not in href.upper():
            continue  # scartiamo i comunicati relativi ad altri vulcani (es. Stromboli)

        # risaliamo alla riga/blocco che contiene data e descrizione
        container = link.find_parent("tr") or link.find_parent("li") or link.parent
        text = container.get_text(" ", strip=True) if container else link.get_text(strip=True)

        date_match = DATE_RE.search(text)
        if not date_match:
            continue
        ts_raw = date_match.group(1)
        try:
            ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

        # la descrizione è il testo tra la data e il nome del link/file
        description = text.replace(ts_raw, "").strip()
        description = re.sub(r"\s*ETNA\s*$", "", description, flags=re.IGNORECASE).strip(" -")
        if not description:
            description = "Comunicato di attività vulcanica"

        pdf_url = href if href.startswith("http") else f"https://www.ct.ingv.it{href}"
        item_id = "com-" + re.sub(r"\W+", "", href.split("/")[-1])

        items.append({
            "id": item_id,
            "timestamp": ts,
            "type": "comunicato",
            "title": description.capitalize(),
            "summary": "Comunicato ufficiale INGV Osservatorio Etneo sull'attività dell'Etna.",
            "level": "medio",
            "url": pdf_url,
        })

    return items


def load_existing_feed() -> dict:
    if FEED_PATH.exists():
        return json.loads(FEED_PATH.read_text(encoding="utf-8"))
    return {"items": []}


def merge_and_trim(existing_items: list[dict], new_items: list[dict]) -> list[dict]:
    others = [it for it in existing_items if it.get("type") != "comunicato"]
    by_id = {it["id"]: it for it in others}
    for it in new_items:
        by_id[it["id"]] = it
    merged = list(by_id.values())
    merged.sort(key=lambda it: it["timestamp"], reverse=True)
    return merged[:MAX_ITEMS]


def main() -> int:
    try:
        new_items = fetch_comunicati_etna()
    except requests.RequestException as exc:
        print(f"Errore nel contattare INGV: {exc}", file=sys.stderr)
        return 1

    if not new_items:
        print("Nessun comunicato Etna trovato: controlla se la struttura della pagina è cambiata.", file=sys.stderr)
        # non è un errore fatale: lasciamo il feed com'era, non sovrascriviamo con vuoto
        return 0

    feed = load_existing_feed()
    feed["items"] = merge_and_trim(feed.get("items", []), new_items)
    feed["generated_at"] = datetime.now(timezone.utc).isoformat()
    feed["max_items"] = MAX_ITEMS

    FEED_PATH.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"feed.json aggiornato: {len(new_items)} comunicati Etna trovati, {len(feed['items'])} elementi totali.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
