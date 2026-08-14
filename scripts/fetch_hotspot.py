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

---------------------------------------------------------------------------
SESSIONE 2026-08: fix di affidabilità
---------------------------------------------------------------------------
Il problema segnalato ("il job fallisce spesso, il sito mostra un dato non
veritiero") aveva due cause distinte, non una sola:

1. NASA sta migrando tutti i siti Earth Science su Earthdata durante il
   2026, e FIRMS ha già avuto finestre di manutenzione programmata durante
   le quali il dominio primario non risponde. NASA stessa pubblica un
   mirror di riserva per questi casi: firms2.modaps.eosdis.nasa.gov.
   Prima non veniva mai usato — ora lo script prova prima il dominio
   primario, poi il mirror, prima di arrendersi.

2. Anche a monte del punto 1, quando ENTRAMBI i tentativi fallivano lo
   script terminava con exit 1 SENZA toccare hotspot.json. Il workflow
   GitHub Actions, a quel punto, saltava anche lo step di commit (uno step
   fallito blocca quelli successivi di default) — quindi il file restava
   fermo all'ultimo dato buono, ma SENZA alcun indicatore che fosse vecchio.
   Il sito mostrava con sicurezza uno stato che poteva risalire a ore o
   giorni prima. Ora, in caso di fallimento totale, lo script scrive
   comunque un JSON aggiornato con "stale": true e "last_success_at",
   mantenendo l'ultimo stato noto ma dichiarandolo esplicitamente non
   fresco — e il workflow (vedi update-hotspot.yml) fa comunque il commit
   anche quando questo script termina con errore, cosa che prima non
   succedeva.

Non toccare il fix IPv4 sotto: risolve un problema reale e distinto (alcuni
runner GitHub Actions instradano male l'IPv6).
"""

import csv
import io
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from json import dumps, loads

import requests
import urllib3.util.connection as urllib3_cn

# ---------------------------------------------------------------------------
# Fix di rete: alcuni runner GitHub Actions non instradano correttamente
# l'IPv6, e host come firms.modaps.eosdis.nasa.gov rispondono anche con un
# indirizzo IPv6 — il tentativo di connessione va in "Network is unreachable"
# prima ancora di raggiungere NASA. Forzando la risoluzione DNS solo su IPv4
# evitiamo il problema alla radice.
# ---------------------------------------------------------------------------
def _forza_ipv4():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = _forza_ipv4

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# Bounding box usata per la CHIAMATA a FIRMS e per i punti mostrati in
# mappa: allargata rispetto alla versione precedente per includere anche
# l'alta Valle del Bove, dove possono aprirsi nuove bocche attive a quote
# più basse dei crateri sommitali (richiesta utente 2026-08, sessione 2).
# west, south, east, north
AREA = "14.90,37.68,15.15,37.82"

# Bounding box STRETTA intorno ai crateri sommitali, usata SOLO per decidere
# lo stato (quiete/moderata/alta): tenerla separata dalla AREA più larga
# evita che un incendio boschivo sui fianchi bassi del vulcano (dentro la
# AREA larga ma fuori da quest'area) faccia scattare un falso stato "alta".
# west, south, east, north — identica alla vecchia AREA, invariata.
NARROW_BOUNDS = (14.95, 37.70, 15.05, 37.80)

# Quanti punti al massimo salviamo in hotspot.json per il rendering in
# mappa (ordinati per FRP decrescente): tiene il file piccolo e veloce da
# scaricare anche in giornate con centinaia di rilevazioni.
MAX_POINTS_SALVATI = 80

SOURCE = "VIIRS_SNPP_NRT"   # sensore VIIRS, dati quasi in tempo reale
DAY_RANGE = 1                # solo le ultime 24 ore, ci basta per lo stato attuale

# Domini FIRMS, in ordine di tentativo. Il secondo è il mirror ufficiale
# NASA usato durante le manutenzioni programmate del dominio primario.
FIRMS_HOSTS = [
    "firms.modaps.eosdis.nasa.gov",
    "firms2.modaps.eosdis.nasa.gov",
]

# Soglie per decidere lo stato mostrato sul sito. A differenza di quanto si
# potrebbe pensare, la sola PRESENZA di hotspot rilevati vicino ai crateri
# sommitali è già un segnale significativo: in condizioni di vera quiete,
# VIIRS in genere non rileva nulla in quest'area. Non serve un FRP enorme
# perché conti come attività: un FRP basso ma con hotspot multipli è già
# coerente con degassamento intenso o attività stromboliana offuscata da
# cenere (il satellite vede "attraverso" solo in parte in questi casi).
SOGLIA_ALTA_FRP = 15      # FRP massimo (MW) sopra cui l'attività è considerata forte
SOGLIA_ALTA_COUNT = 6     # numero di hotspot sopra cui l'attività è considerata forte

HOTSPOT_PATH = Path(__file__).resolve().parent.parent / "data" / "hotspot.json"


def fetch_hotspots_from_host(host: str, map_key: str, max_tentativi: int = 2) -> list[dict]:
    """Prova un singolo host FIRMS, con un piccolo retry locale per
    assorbire intoppi di rete transitori (non un fallimento del servizio)."""
    url = f"https://{host}/api/area/csv/{map_key}/{SOURCE}/{AREA}/{DAY_RANGE}"

    ultimo_errore = None
    for tentativo in range(1, max_tentativi + 1):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()

            # Un errore di chiave non valida spesso torna comunque HTTP 200 ma con
            # un corpo di testo che non è un CSV valido: lo intercettiamo a parte.
            text = resp.text.strip()
            if not text or "latitude" not in text.splitlines()[0]:
                raise ValueError(f"Risposta FIRMS inattesa da {host} (chiave non valida?): {text[:200]!r}")

            reader = csv.DictReader(io.StringIO(text))
            return list(reader)

        except (requests.RequestException, ValueError) as exc:
            ultimo_errore = exc
            if tentativo < max_tentativi:
                attesa = 5 * tentativo
                print(f"[{host}] tentativo {tentativo}/{max_tentativi} fallito ({exc}), riprovo tra {attesa}s...", file=sys.stderr)
                time.sleep(attesa)

    raise ultimo_errore


def fetch_hotspots(map_key: str) -> list[dict]:
    """Prova tutti gli host FIRMS configurati in ordine (primario, poi
    mirror). Solleva l'ultimo errore solo se TUTTI gli host falliscono."""
    ultimo_errore = None
    for i, host in enumerate(FIRMS_HOSTS):
        try:
            return fetch_hotspots_from_host(host, map_key)
        except (requests.RequestException, ValueError) as exc:
            ultimo_errore = exc
            rimasti = len(FIRMS_HOSTS) - i - 1
            if rimasti:
                print(f"Host {host} non raggiungibile ({exc}), provo il mirror successivo...", file=sys.stderr)

    raise ultimo_errore


def _dentro_narrow_bounds(row: dict) -> bool:
    """True se il punto ricade nella bounding box stretta (crateri
    sommitali), usata solo per la classificazione dello stato."""
    try:
        lat = float(row.get("latitude", 0) or 0)
        lng = float(row.get("longitude", 0) or 0)
    except ValueError:
        return False
    west, south, east, north = NARROW_BOUNDS
    return west <= lng <= east and south <= lat <= north


def _punto_da_row(row: dict) -> dict:
    """Converte una riga CSV FIRMS in un punto compatto per hotspot.json.
    Campi CSV rilevanti (VIIRS NRT): latitude, longitude, frp, confidence,
    acq_date, acq_time, daynight."""
    try:
        frp = round(float(row.get("frp", 0) or 0), 1)
    except ValueError:
        frp = 0.0
    return {
        "lat": round(float(row["latitude"]), 5),
        "lng": round(float(row["longitude"]), 5),
        "frp": frp,
        "confidence": row.get("confidence", ""),
        "acq_date": row.get("acq_date", ""),
        "acq_time": row.get("acq_time", ""),
    }


def build_status(rows: list[dict], now: datetime) -> dict:
    # Solo i punti nella bbox stretta (crateri sommitali) contano per lo
    # stato — vedi commento su NARROW_BOUNDS sopra.
    rows_stato = [r for r in rows if _dentro_narrow_bounds(r)]

    # Tutti i punti nella bbox larga (crateri + Valle del Bove) vengono
    # invece salvati per essere disegnati in mappa, non solo usati per lo
    # stato aggregato — ordinati per FRP decrescente e tagliati a
    # MAX_POINTS_SALVATI per tenere il file leggero.
    punti = sorted((_punto_da_row(r) for r in rows), key=lambda p: p["frp"], reverse=True)
    punti = punti[:MAX_POINTS_SALVATI]

    if not rows_stato:
        return {
            "generated_at": now.isoformat(),
            "source": "NASA FIRMS (VIIRS_SNPP_NRT) — https://firms.modaps.eosdis.nasa.gov",
            "status": "quiete",
            "notes": "Nessuna anomalia termica rilevata dal satellite nelle ultime 24 ore.",
            "last_significant_event": None,
            "hotspot_count_24h": 0,
            "points": punti,
            "stale": False,
            "last_success_at": now.isoformat(),
        }

    max_frp = max(float(r.get("frp", 0) or 0) for r in rows_stato)
    count = len(rows_stato)

    if max_frp >= SOGLIA_ALTA_FRP or count >= SOGLIA_ALTA_COUNT:
        status = "alta"
        notes = f"Anomalia termica significativa rilevata dal satellite ({count} hotspot, FRP massimo {max_frp:.1f} MW)."
    else:
        # qualunque hotspot rilevato vicino ai crateri sommitali è già un
        # segnale di attività: in quiete reale VIIRS non rileva quasi nulla qui
        status = "moderata"
        notes = f"Attività termica rilevata dal satellite ({count} hotspot, FRP massimo {max_frp:.1f} MW)."

    return {
        "generated_at": now.isoformat(),
        "source": "NASA FIRMS (VIIRS_SNPP_NRT) — https://firms.modaps.eosdis.nasa.gov",
        "status": status,
        "notes": notes,
        "last_significant_event": now.isoformat() if status != "quiete" else None,
        "hotspot_count_24h": count,
        "points": punti,
        "stale": False,
        "last_success_at": now.isoformat(),
    }


def write_stale_fallback(now: datetime, errore: Exception) -> None:
    """Chiamato quando TUTTI gli host FIRMS falliscono. Non inventiamo un
    nuovo stato: manteniamo l'ultimo stato noto letto dal file esistente,
    ma lo marchiamo esplicitamente come non fresco, con il timestamp
    dell'ultimo successo reale (se lo troviamo) e il motivo del fallimento
    odierno. Questo è il cuore del fix: prima, in questo scenario, il file
    non veniva proprio toccato e il sito mostrava un dato vecchio spacciato
    per attuale."""
    precedente = {}
    if HOTSPOT_PATH.exists():
        try:
            precedente = loads(HOTSPOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            precedente = {}

    last_success_at = precedente.get("last_success_at") or precedente.get("generated_at")

    aggiornato = {
        **precedente,
        "checked_at": now.isoformat(),
        "last_success_at": last_success_at,
        "stale": True,
        "stale_reason": f"NASA FIRMS non raggiungibile su nessun host disponibile ({errore})",
    }
    # non sovrascriviamo "generated_at": deve restare quello dell'ultimo
    # dato realmente ottenuto da FIRMS, non il momento di questo tentativo.
    aggiornato.setdefault("generated_at", now.isoformat())
    aggiornato.setdefault("status", "quiete")
    aggiornato.setdefault("notes", "Nessun dato disponibile.")

    HOTSPOT_PATH.write_text(dumps(aggiornato, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"hotspot.json aggiornato come STALE (ultimo successo: {last_success_at}). Motivo: {errore}", file=sys.stderr)


def main() -> int:
    map_key = os.environ.get("FIRMS_MAP_KEY")
    now = datetime.now(timezone.utc)

    if not map_key:
        print("Variabile d'ambiente FIRMS_MAP_KEY mancante.", file=sys.stderr)
        write_stale_fallback(now, RuntimeError("FIRMS_MAP_KEY non configurata"))
        return 1

    try:
        rows = fetch_hotspots(map_key)
    except (requests.RequestException, ValueError) as exc:
        print(f"Errore nel contattare NASA FIRMS (primario + mirror): {exc}", file=sys.stderr)
        write_stale_fallback(now, exc)
        return 1

    status = build_status(rows, now)
    HOTSPOT_PATH.write_text(dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"hotspot.json aggiornato: stato '{status['status']}', {len(rows)} rilevazioni nelle ultime 24h.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
