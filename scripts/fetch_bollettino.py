"""
Aggiorna data/bollettino.json con la sintesi del Bollettino Settimanale
INGV sul monitoraggio vulcanico, geochimico e sismico dell'Etna.

Perché un solo script per gas E dati scientifici (vedi PROGETTO_NOTE.md
§12.4/§12.5): il bollettino è UN documento PDF con una sezione iniziale
numerata ("1. SINTESI STATO DI ATTIVITA'") che contiene, punto per punto,
esattamente i campi che servono a entrambi i tab futuri — non ha senso
scaricare due volte lo stesso PDF con due script diversi. Il tab "gas"
(questa sessione) usa solo la sezione 5 (geochimica/SO2); il tab
"dati scientifici" (prossima sessione) userà le sezioni 2-4 e 6, già
presenti in questo stesso file JSON da subito.

    python3 scripts/fetch_bollettino.py

Fonte: https://www.ct.ingv.it/index.php/monitoraggio-e-sorveglianza/prodotti-del-monitoraggio/bollettini-settimanali-multidisciplinari
"""

import io
import re
import socket
import sys
from datetime import datetime, timezone
from json import dumps, loads
from pathlib import Path

import pdfplumber
import requests
import urllib3.util.connection as urllib3_cn

# Fix di rete IPv4 (stessa causa/stessa soluzione degli altri script).
def _forza_ipv4():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = _forza_ipv4

LISTING_PAGE = "https://www.ct.ingv.it/index.php/monitoraggio-e-sorveglianza/prodotti-del-monitoraggio/bollettini-settimanali-multidisciplinari"
BOLLETTINO_PATH = Path(__file__).resolve().parent.parent / "data" / "bollettino.json"

# Cattura id numerico + data SOLO per i bollettini SETTIMANALI dell'Etna
# (la stessa pagina elenca, mischiati, anche Stromboli e Vulcano, e anche i
# bollettini MENSILI dell'Etna — esclusi perché la stringa "Settimanale" è
# parte del pattern).
LINK_RE = re.compile(
    r"/(\d+)-bollettino-Settimanale-sul-monitoraggio-vulcanico-geochimico-e-sismico-del-vulcano-Etna-del-(\d{4}-\d{2}-\d{2})/file"
)

# Ordine e nomi ESATTI delle sezioni numerate nella "SINTESI STATO DI
# ATTIVITA'" del bollettino — verificato su più bollettini reali (vedi
# PROGETTO_NOTE.md per i riferimenti). "ALTRE OSSERVAZIONI" (7) non è
# sempre presente: è normale che risulti None in quel caso.
SEZIONI = [
    ("1", "vulcanologiche", "OSSERVAZIONI VULCANOLOGICHE"),
    ("2", "sismologia", "SISMOLOGIA"),
    ("3", "infrasuono", "INFRASUONO"),
    ("4", "deformazioni", "DEFORMAZIONI DEL SUOLO"),
    ("5", "geochimica", "GEOCHIMICA"),
    ("6", "satellitare", "OSSERVAZIONI SATELLITARI"),
    ("7", "altre_osservazioni", "ALTRE OSSERVAZIONI"),
]

HEADER_RE = re.compile(
    r"(\d)\)\s*(OSSERVAZIONI VULCANOLOGICHE|SISMOLOGIA|INFRASUONO|DEFORMAZIONI DEL SUOLO|GEOCHIMICA|OSSERVAZIONI SATELLITARI|ALTRE OSSERVAZIONI)\s*:\s*"
)

SO2_RE = re.compile(
    r"Flusso di SO2(.*?)(?=Flusso di CO2|Pressione parziale|Rapporto isotopico|$)",
    re.IGNORECASE,
)

# Marcatori che segnalano che siamo usciti dal blocco "SINTESI STATO DI
# ATTIVITA'" (footer di pagina ripetuto in ogni pagina, o inizio di un
# capitolo vero e proprio più avanti nel documento, es. "2. SISMOLOGIA" —
# notare il punto, non la parentesi, che distingue il titolo di capitolo
# dalla voce numerata dentro la sintesi). Rilevante solo per l'ultima
# sezione trovata (di solito la 6, satellitare, quando manca la 7): senza
# un prossimo "N)" a fare da confine, altrimenti continuerebbe a
# raccogliere testo fino alla fine delle pagine analizzate.
SPILLOVER_RE = re.compile(r"INGV\s*-\s*BOLLETTINO|Pagina\s+\d+\s+di\s+\d+|\b\d\.\s+[A-ZÀ-Ù]{4,}")


def trova_ultimo_bollettino() -> tuple[str, str]:
    """Trova, sulla pagina elenco INGV, id e data del bollettino
    SETTIMANALE Etna più recente. Non ci fidiamo dell'ordine con cui
    compaiono in pagina: scegliamo la data più alta tra tutti i match."""
    resp = requests.get(LISTING_PAGE, timeout=20, headers={"User-Agent": "etna-ora-bot/1.0"})
    resp.raise_for_status()

    candidati = LINK_RE.findall(resp.text)
    if not candidati:
        raise ValueError("Nessun bollettino settimanale Etna trovato (struttura pagina cambiata?)")

    candidati.sort(key=lambda c: c[1], reverse=True)
    id_, data = candidati[0]
    url = f"{LISTING_PAGE}/{id_}-bollettino-Settimanale-sul-monitoraggio-vulcanico-geochimico-e-sismico-del-vulcano-Etna-del-{data}/file"
    return url, data


def estrai_testo_prime_pagine(pdf_bytes: bytes, n: int = 2) -> str:
    """La sezione 'SINTESI STATO DI ATTIVITA'' è sempre nella prima pagina
    del bollettino (verificato su più numeri): ci limitiamo alle prime due
    pagine per non scaricare/processare inutilmente un PDF di 15-20+
    pagine quando ci serve solo l'indice iniziale."""
    testo = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:n]:
            testo.append(page.extract_text() or "")
    return "\n".join(testo)


def estrai_sezioni(testo: str) -> dict:
    normalizzato = re.sub(r"\s+", " ", testo).strip()
    matches = list(HEADER_RE.finditer(normalizzato))

    grezzo = {}
    for i, m in enumerate(matches):
        numero = m.group(1)
        inizio = m.end()
        fine = matches[i + 1].start() if i + 1 < len(matches) else len(normalizzato)
        contenuto = normalizzato[inizio:fine].strip(" .")
        if i == len(matches) - 1 and contenuto:
            # ultima sezione trovata: taglia al primo marcatore di
            # footer/nuovo capitolo, vedi commento su SPILLOVER_RE sopra.
            sm = SPILLOVER_RE.search(contenuto)
            if sm:
                contenuto = contenuto[:sm.start()].strip(" .")
        grezzo[numero] = contenuto or None

    sezioni = {}
    for numero, chiave, _nome in SEZIONI:
        sezioni[chiave] = grezzo.get(numero)

    # Estratto specifico SO2 dalla sezione geochimica (che contiene anche
    # CO2 dal suolo, CO2 in falda, rapporto isotopico He — il tab "gas" di
    # questa sessione mostra solo la frase sull'SO2, non l'intera sezione).
    so2 = None
    if sezioni["geochimica"]:
        m = SO2_RE.search(sezioni["geochimica"])
        if m:
            so2 = ("Flusso di SO2" + m.group(1)).strip(" .")
    sezioni["so2_estratto"] = so2

    return sezioni


def fetch_bollettino() -> dict:
    url, data_str = trova_ultimo_bollettino()
    resp = requests.get(url, timeout=30, headers={"User-Agent": "etna-ora-bot/1.0"})
    resp.raise_for_status()
    if b"%PDF" not in resp.content[:1024]:
        raise ValueError("La risposta non sembra un PDF valido (pagina di errore INGV?)")

    testo = estrai_testo_prime_pagine(resp.content)
    sezioni = estrai_sezioni(testo)

    if not any(v for k, v in sezioni.items() if k != "so2_estratto"):
        raise ValueError("Nessuna sezione numerata riconosciuta nel PDF (formato bollettino cambiato?)")

    return {
        "bulletin_date": data_str,
        "bulletin_url": url,
        "sections": sezioni,
    }


def write_stale_fallback(now: datetime, errore: Exception) -> None:
    """Stesso pattern di fetch_hotspot.py/fetch_aviation.py: se INGV non è
    raggiungibile o il PDF non è analizzabile, non lasciamo il file
    intatto e silenzioso — lo riscriviamo mantenendo l'ultimo bollettino
    noto ma marcato esplicitamente 'stale'."""
    precedente = {}
    if BOLLETTINO_PATH.exists():
        try:
            precedente = loads(BOLLETTINO_PATH.read_text(encoding="utf-8"))
        except Exception:
            precedente = {}

    last_success_at = precedente.get("last_success_at") or precedente.get("generated_at")

    aggiornato = {
        **precedente,
        "checked_at": now.isoformat(),
        "last_success_at": last_success_at,
        "stale": True,
        "stale_reason": f"Bollettino INGV non recuperabile ({errore})",
    }
    aggiornato.setdefault("generated_at", now.isoformat())
    aggiornato.setdefault("sections", {})

    BOLLETTINO_PATH.write_text(dumps(aggiornato, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"bollettino.json aggiornato come STALE (ultimo successo: {last_success_at}). Motivo: {errore}", file=sys.stderr)


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        bollettino = fetch_bollettino()
    except (requests.RequestException, ValueError) as exc:
        print(f"Errore nel recuperare/leggere il bollettino INGV: {exc}", file=sys.stderr)
        write_stale_fallback(now, exc)
        return 1

    bollettino["generated_at"] = now.isoformat()
    bollettino["last_success_at"] = now.isoformat()
    bollettino["stale"] = False

    BOLLETTINO_PATH.write_text(dumps(bollettino, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"bollettino.json aggiornato: bollettino del {bollettino['bulletin_date']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
