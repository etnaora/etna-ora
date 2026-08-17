"""
Aggiorna data/aviation.json con l'ultimo avviso ufficiale per l'aviazione
sull'Etna pubblicato dal VAAC di Tolosa (Volcanic Ash Advisory Center,
Météo-France) — l'ente ICAO responsabile della sorveglianza delle ceneri
vulcaniche per il traffico aereo nell'area euro-mediterranea.

Perché VAAC e non il sito dell'aeroporto di Catania: vedi
PROGETTO_NOTE.md §12.4 — aeroporto.catania.it è una SPA Next.js non
scrapabile senza browser headless, VAAC Toulouse pubblica invece testo
semplice, stabile, pensato apposta per essere letto da un programma.

    python3 scripts/fetch_aviation.py

Documentazione/fonte: https://vaac.meteo.fr/volcanoes/etna/
"""

import re
import socket
import sys
from datetime import datetime, timezone
from json import dumps, loads
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import urllib3.util.connection as urllib3_cn

# Fix di rete IPv4 (stessa causa/stessa soluzione di fetch_hotspot.py: alcuni
# runner GitHub Actions instradano male l'IPv6 verso alcuni host).
def _forza_ipv4():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = _forza_ipv4

VOLCANO_PAGE = "https://vaac.meteo.fr/volcanoes/etna/"
ETNA_CODE = "211060"  # codice volcano ICAO/VAAC per l'Etna, compare in ogni URL/testo avviso

AVIATION_PATH = Path(__file__).resolve().parent.parent / "data" / "aviation.json"

SLUG_RE = re.compile(r"/advisory/(\d{4})/(" + ETNA_CODE + r"_(\d{14}))/")

FIELD_RE = {
    "dtg": re.compile(r"^DTG:\s*(\S+)", re.MULTILINE),
    "advisory_nr": re.compile(r"^ADVISORY NR:\s*(\S+)", re.MULTILINE),
    "colour_code": re.compile(r"^AVIATION COLOUR CODE:\s*(\S+)", re.MULTILINE),
    "eruption_details": re.compile(r"^ERUPTION DETAILS:\s*(.+)", re.MULTILINE),
    "remark": re.compile(r"^RMK:\s*(.+)", re.MULTILINE),
    "next_advisory": re.compile(r"^NXT ADVISORY:\s*(.+?)=?\s*$", re.MULTILINE),
}


def _parse_dtg(raw: str) -> str | None:
    """'20260815/0725Z' -> '2026-08-15T07:25:00+00:00'. None se il formato
    non è quello atteso (non blocchiamo tutto per un campo secondario)."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})/(\d{2})(\d{2})Z?", raw)
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def trova_url_ultimo_avviso() -> str:
    """Trova, sulla pagina Etna di VAAC Toulouse, l'URL del file .txt
    dell'avviso più recente. Gli avvisi sono organizzati in cartelle con
    slug tipo '211060_20260815072511' (codice volcano + timestamp); non ci
    fidiamo dell'ordine con cui compaiono nella pagina (potrebbe cambiare)
    e scegliamo invece quello con il timestamp più alto."""
    resp = requests.get(VOLCANO_PAGE, timeout=20, headers={"User-Agent": "etna-ora-bot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    candidati = []  # (timestamp_int, slug, anno)
    for a in soup.find_all("a", href=True):
        m = SLUG_RE.search(a["href"])
        if m:
            anno, slug, ts = m.groups()
            candidati.append((int(ts), slug, anno))

    if not candidati:
        raise ValueError("Nessun avviso Etna trovato sulla pagina VAAC (struttura pagina cambiata?)")

    candidati.sort(key=lambda c: c[0], reverse=True)
    _, slug, anno = candidati[0]
    return f"https://vaac.meteo.fr/advisory/{anno}/{slug}/{slug}_vaa.txt"


def fetch_avviso() -> dict:
    txt_url = trova_url_ultimo_avviso()
    resp = requests.get(txt_url, timeout=20, headers={"User-Agent": "etna-ora-bot/1.0"})
    resp.raise_for_status()
    testo = resp.text

    campi = {}
    for chiave, pattern in FIELD_RE.items():
        m = pattern.search(testo)
        campi[chiave] = m.group(1).strip() if m else None

    eruption_details = campi["eruption_details"] or ""
    # Due booleani "best effort" derivati dal testo libero ufficiale (che
    # resta comunque salvato per intero: se la deduzione qui sotto sbaglia,
    # il dato grezzo mostrato in pagina resta corretto).
    eruption_ongoing = None
    if "ONGOING ERUPTION" in eruption_details.upper() and "ENDED" not in eruption_details.upper():
        eruption_ongoing = True
    elif "ENDED" in eruption_details.upper():
        eruption_ongoing = False

    colour_raw = (campi["colour_code"] or "").strip().upper()
    colour = colour_raw.lower() if colour_raw in ("RED", "ORANGE", "YELLOW", "GREEN", "UNKNOWN") else "unknown"

    return {
        "advisory_id": None,  # riempito da chi chiama, non è nel .txt
        "advisory_url": txt_url.rsplit("_vaa.txt", 1)[0] + "/",
        "dtg": _parse_dtg(campi["dtg"]) if campi["dtg"] else None,
        "advisory_nr": campi["advisory_nr"],
        "aviation_colour_code": colour,
        "eruption_details_raw": eruption_details or None,
        "eruption_ongoing": eruption_ongoing,
        "remark_raw": campi["remark"],
        "next_advisory_raw": campi["next_advisory"],
        "raw_text": testo.strip(),
    }


def write_stale_fallback(now: datetime, errore: Exception) -> None:
    """Stesso pattern di fetch_hotspot.py: se VAAC non è raggiungibile non
    lasciamo il file intatto e silenzioso, lo riscriviamo mantenendo
    l'ultimo dato noto ma marcato esplicitamente 'stale', con la ragione
    del fallimento odierno."""
    precedente = {}
    if AVIATION_PATH.exists():
        try:
            precedente = loads(AVIATION_PATH.read_text(encoding="utf-8"))
        except Exception:
            precedente = {}

    last_success_at = precedente.get("last_success_at") or precedente.get("generated_at")

    aggiornato = {
        **precedente,
        "checked_at": now.isoformat(),
        "last_success_at": last_success_at,
        "stale": True,
        "stale_reason": f"VAAC Toulouse non raggiungibile ({errore})",
    }
    aggiornato.setdefault("generated_at", now.isoformat())
    aggiornato.setdefault("aviation_colour_code", "unknown")

    AVIATION_PATH.write_text(dumps(aggiornato, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"aviation.json aggiornato come STALE (ultimo successo: {last_success_at}). Motivo: {errore}", file=sys.stderr)


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        avviso = fetch_avviso()
    except (requests.RequestException, ValueError) as exc:
        print(f"Errore nel contattare VAAC Toulouse: {exc}", file=sys.stderr)
        write_stale_fallback(now, exc)
        return 1

    avviso["advisory_id"] = "ETNA." + (avviso["advisory_nr"].split("/")[-1] if avviso["advisory_nr"] else "?")
    avviso["generated_at"] = now.isoformat()
    avviso["last_success_at"] = now.isoformat()
    avviso["stale"] = False
    avviso.pop("stale_reason", None)

    AVIATION_PATH.write_text(dumps(avviso, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"aviation.json aggiornato: {avviso['advisory_id']}, codice colore {avviso['aviation_colour_code']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
