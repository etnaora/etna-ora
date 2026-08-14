# Etna, ora — Note complete di progetto

Questo file è il "cervello" del progetto: architettura, decisioni prese, logiche
implementate, insidie già risolte, e cosa manca ancora. Se riprendi il lavoro
(con me o con chiunque altro, umano o AI), leggi questo file per intero prima
di modificare qualcosa — evita di rifare errori già corretti.

Ultimo aggiornamento contenuti: sessione in cui sono stati risolti i fallimenti
di rete IPv6 su GitHub Actions e rimossa la vista 3D.

---

## 1. Cos'è il progetto

Sito statico gratuito di monitoraggio in tempo reale del vulcano Etna.
Filosofia guida, decisa fin dall'inizio e mai cambiata: **"la cosa più bella e
più snella dedicata solo all'Etna"** — non un cruscotto tecnico stile
strumentazione (quello lo fa già bene un concorrente, EtnaMonitor.it), ma una
mappa scenografica essenziale, emozionale più che "da controllo missione".

Vincoli permanenti del progetto:
- **Zero costi fissi**: solo servizi con piano gratuito (GitHub Pages, GitHub
  Actions su repo pubblico, API gratuite di INGV/NASA)
- **Nessun backend sempre acceso**: tutta la logica "server-side" gira come
  job periodici GitHub Actions che scrivono file JSON statici
- **No scopo di lucro nella fase attuale**, ma pensato per essere scalabile in
  futuro (dominio proprio, affiliazioni turistiche, canale Telegram)

---

## 2. Dove vive il progetto

- **Organization GitHub**: `etnaora` (creata apposta, namespace separato
  dall'account personale dell'utente, stesso login)
- **Repository**: `github.com/etnaora/etna-ora` (pubblico — deve restare
  pubblico, altrimenti GitHub Actions e Pages non sono più gratuiti illimitati)
- **Sito pubblicato**: `https://etnaora.github.io/etna-ora/` (GitHub Pages,
  branch `main`, root)
- **Dominio proprio**: non ancora acquistato. Quando succede, vanno aggiornati
  a mano tutti i riferimenti elencati nella sezione 9.

---

## 3. Struttura dei file

```
etna-ora/
├── index.html                          # l'intero sito (HTML+CSS+JS in un file)
├── privacy.html                        # pagina privacy (editata a mano dall'utente)
├── cookie.html                         # pagina cookie (editata a mano dall'utente)
├── robots.txt                          # SEO
├── sitemap.xml                         # SEO
├── README.md                           # doc tecnico "storico" (vedi nota sotto)
├── PROGETTO_NOTE.md                    # QUESTO FILE
├── data/
│   ├── feed.json                       # sismicità + comunicati INGV (finestra 25 elementi)
│   ├── hotspot.json                    # stato termico satellitare (quiete/moderata/alta)
│   └── webcam.json                     # elenco statico delle 6 webcam ufficiali
├── scripts/
│   ├── fetch_terremoti.py              # popola gli item "sismicita" in feed.json
│   ├── fetch_comunicati.py             # popola gli item "comunicato" in feed.json
│   └── fetch_hotspot.py                # popola hotspot.json
└── .github/workflows/
    ├── update-feed.yml                 # esegue fetch_terremoti.py ogni 15 min
    ├── update-comunicati.yml           # esegue fetch_comunicati.py ogni 15 min (sfasato +5)
    └── update-hotspot.yml              # esegue fetch_hotspot.py ogni 30 min
```

**Nota sul README.md**: esiste da prima di questo file ed è stato aggiornato
via via, ma è meno organico di questo documento (cresciuto "a incrementi").
Questo `PROGETTO_NOTE.md` è la fonte di verità più completa e aggiornata; il
README può essere considerato un sotto-insieme/duplicato parziale.

**Assenti di proposito**: nessun `package.json`, nessun bundler, nessun
framework frontend. `index.html` carica Leaflet via CDN (`unpkg.com`) e non
ha altre dipendenze runtime lato client.

---

## 4. index.html — architettura del sito

Un solo file, self-contained. Struttura interna:

1. **`<head>`**: meta tag SEO completi (title, description, keywords, Open
   Graph, Twitter Card, canonical, JSON-LD schema.org `WebSite`), font Google
   (Fraunces per i titoli, IBM Plex Sans per il corpo, IBM Plex Mono per
   dati/numeri/orari), CSS Leaflet da CDN.
2. **Design tokens** (CSS custom properties in `:root`):
   - `--basalt #14120F` sfondo principale
   - `--basalt-panel #1F1B17` / `--basalt-panel-2 #26211C` pannelli/modali
   - `--ash #EDE6DB` testo primario, `--ash-muted #9C948A` testo secondario
   - `--mist #5C7A8A` = stato "quiete", `--ember #E8541E` = stato "attività",
     `--sulfur #FFD166` = stato "allerta" (usato anche per il pallino del
     pulsante "ricaduta cenere")
   - `--accent` è **dinamico**: viene riassegnato via JS in base allo stato
     hotspot (vedi punto 6), e pilota sia il colore del pallino di stato che
     quello del marker pulsante sul cratere
3. **`<body>`**: mappa Leaflet full-bleed (`#map`), topbar con wordmark +
   pillola di stato centrata + bottone info, cassetto feed in basso, bottone
   "ricaduta cenere" fluttuante, 4 modali (webcam, info, ricaduta cenere).
4. **`<script>`** (un solo blocco finale): inizializzazione mappa Leaflet,
   fetch dei 3 JSON con **cache-busting esplicito** (`?v=timestamp` +
   `{cache:'no-store'}` — necessario, vedi insidia in sezione 8), rendering
   webcam/feed/stato, logica modali, logica "ricaduta cenere".

### Elementi chiave del DOM (id) da conoscere se si modifica il codice
- `#map` — contenitore Leaflet
- `#statusDot` / `#statusLabel` — pillola di stato in alto (testo generato via `renderStatus()`, i18n-aware)
- `#feed` / `#feedList` / `#feedHeadline` — cassetto feed
- `#camModal` / `#camTitle` / `#camMeta` / `#camFrame` / `#camFallbackLink`
- `#infoModal` — spiegazione + link privacy/cookie
- `#ashModal` / `#ashSlots` / `#ashImage` / `#ashImageError` — ricaduta cenere
- `#topicDock` — dock di 5 pulsanti circolari collassabili (vedi §12), sostituisce il vecchio `.ash-btn`
- `#gasModal` / `#aeroportoModal` / `#scientificoModal` / `#satelliteModal` — i 4 nuovi tab, scheletro (vedi §12)
- `#langBtnIt` / `#langBtnEn` — toggle lingua in topbar, accanto al bottone info

---

## 5. Le tre pipeline dati automatiche (schema comune)

Tutte e tre seguono lo stesso pattern:
**script Python → GitHub Actions schedulato → commit automatico del bot
`etna-bot` → GitHub Pages si ripubblica da solo**.

### 5.1 Sismicità (`fetch_terremoti.py` + `update-feed.yml`)
- Fonte: webservice ufficiale INGV FDSN event
  (`webservices.ingv.it/fdsnws/event/1/query`, licenza CC-BY 4.0)
- Bounding box: lat 37.55–37.95, lon 14.75–15.25 (edificio etneo + zone
  sismogenetiche limitrofe)
- Filtro: `minmagnitude=1.0`, `LOOKBACK_DAYS=14`
- Logica di merge: rilegge `feed.json`, **rimuove solo gli item con
  `type=="sismicita"`**, li ricostruisce da zero con i dati freschi, li
  rimescola con gli item degli altri tipi (comunicato/tremore/bollettino) già
  presenti, ordina per `timestamp` decrescente, taglia a `MAX_ITEMS=25`
- **Insidia già risolta**: il campo `time` del geojson INGV arriva come
  **stringa ISO**, non timestamp numerico come da spec FDSN generica —
  c'è una funzione `parse_ingv_time()` che gestisce entrambi i casi
- Cron: `*/15 * * * *` (ogni 15 minuti)

### 5.2 Comunicati INGV (`fetch_comunicati.py` + `update-comunicati.yml`)
- Fonte: **non è un'API strutturata** — scraping HTML leggero della pagina
  pubblica `ct.ingv.it/sezioniesterne/Comunicati/ComunicatiVulcanici.php?I=0`
  (tabella con link a PDF)
- Filtro: solo link con `ETNA` nell'href (scarta Stromboli)
- Estrazione: cerca un pattern data `YYYY-MM-DD HH:MM:SS` nel testo del
  blocco contenente il link, poi ripulisce la descrizione rimuovendo la data
  e il testo visibile del link (es. "Download PDF") — **senza questa pulizia
  il titolo finisce con "download pdf" appiccicato in coda**
- URL del PDF: costruito con `urllib.parse.urljoin()`, **mai concatenazione
  manuale** — l'href della pagina è un percorso relativo (`../../Dati/...`),
  concatenarlo a mano produce URL rotti (bug già commesso e corretto)
- Logica di merge: stessa identica logica della sismicità, ma sul
  `type=="comunicato"`
- Se non trova nulla, **non sovrascrive il feed con un vuoto** (probabile
  cambio di formato della pagina, meglio lasciare i dati vecchi che perderli)
- Cron: `5-59/15 * * * *` — **sfasato di 5 minuti** rispetto a
  `update-feed.yml` apposta, perché entrambi scrivono su `feed.json` e un
  'push' concorrente nello stesso istante potrebbe fallire

### 5.3 Hotspot termico satellitare (`fetch_hotspot.py` + `update-hotspot.yml`)
- Fonte primaria: NASA FIRMS (VIIRS_SNPP_NRT), endpoint area CSV
  `firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}`
- **Fix 2026-08 — mirror di riserva**: se il dominio primario non risponde,
  lo script riprova automaticamente su `firms2.modaps.eosdis.nasa.gov`, il
  mirror ufficiale NASA usato durante le manutenzioni programmate (NASA sta
  migrando i siti Earth Science su Earthdata durante tutto il 2026, con
  finestre di manutenzione note). Prima non veniva mai usato.
- Richiede una **API key gratuita** salvata come secret GitHub
  `FIRMS_MAP_KEY` (organization secret, repository access = etna-ora)
- Bounding box strettissima intorno ai crateri sommitali: `14.95,37.70,15.05,37.80`
- **Logica di classificazione (calibrata su un caso reale di eruzione in
  corso, non teorica)**:
  - 0 hotspot rilevati → `quiete`
  - ≥1 hotspot ma sotto soglia → `moderata` (**anche un solo hotspot con FRP
    basso conta come attività**: in condizioni di vera quiete VIIRS non
    rileva quasi nulla in quest'area, quindi la sola presenza è già
    significativa — non serve un FRP alto)
  - `FRP massimo ≥ 15 MW` OPPURE `numero hotspot ≥ 6` → `alta`
- Questo stato pilota **sia** la pillola "status attuale" in alto sul sito
  **sia** il colore (`--accent`) del marker pulsante sul cratere
- Cron: `*/30 * * * *`
- **Fix 2026-08 — stato "stale" onesto invece del silenzio**: se ANCHE il
  mirror fallisce, lo script non lascia `hotspot.json` intonso: scrive
  comunque il file, mantenendo l'ultimo stato noto ma aggiungendo
  `"stale": true`, `"stale_reason"` e `"last_success_at"`. Il frontend
  (`renderStatus()` in `index.html`) mostra in quel caso un suffisso
  esplicito accanto allo stato ("· dato non aggiornato" / "· data not up to
  date"), invece di far sembrare fresco un dato vecchio.
  **Prima**, in questo scenario, lo script terminava con `exit 1` senza
  toccare il file, e il workflow saltava anche lo step di commit — quindi
  il sito mostrava con sicurezza uno stato potenzialmente vecchio di ore o
  giorni, senza alcun indicatore. Era questo il bug segnalato ("il job
  fallisce, il sito mostra un dato non veritiero"), non (solo) il problema
  di rete IPv6.
- Il job GitHub Actions **fallisce comunque visibilmente** (notifica email)
  quando il fetch non riesce — utile per sapere se serve intervenire (es.
  chiave FIRMS scaduta) — ma questo non impedisce più la pubblicazione dello
  stato onesto sul sito, perché lo step di commit ora ha `if: always()`.

### 5.4 Fix di rete comune a tutti e tre gli script (importante!)
Tutti e tre gli script hanno, in testa, questo blocco:
```python
import socket
import urllib3.util.connection as urllib3_cn
def _forza_ipv4():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = _forza_ipv4
```
**Perché esiste**: alcuni runner GitHub Actions non instradano correttamente
l'IPv6. Host come `firms.modaps.eosdis.nasa.gov` rispondono anche con un
indirizzo IPv6, e la richiesta falliva con `Errno 101 Network is unreachable`
— **prima ancora di raggiungere il server**, quindi non è un problema NASA/INGV.
Questo causava sia fallimenti frequenti (email di notifica continue) sia,
concretamente, un **falso stato "quiete" durante un'eruzione realmente in
corso** (perché lo script falliva prima di scrivere `hotspot.json`, che
restava bloccato all'ultimo dato buono). **Non rimuovere questo blocco.**

`fetch_hotspot.py` prova fino a 2 tentativi per host (attesa 5s tra un
tentativo e l'altro), poi passa all'host successivo nell'elenco
`FIRMS_HOSTS` (primario → mirror), prima di arrendersi e scrivere lo stato
"stale" descritto sopra.

---

## 6. webcam.json — dati statici (nessuno script)

6 webcam reali della rete INGV-OE, aggiornate a mano (non cambiano spesso):
`ecv` (crateri sommitali), `emct` (cratere SE), `ent` (Piano Provenzana,
nord), `env` (Rifugio Sapienza, sud), `epvh` (Milo, est), `emov` (Montagnola,
2600m, la più vicina ai crateri).

Ogni voce ha `stream_url` che punta a
`ct.ingv.it/sezioniesterne/webcam/Webcam.php?Vulcano={CODICE}` — questa
pagina INGV **non fa refresh automatico lato loro**, ma restituisce sempre
l'ultima immagine disponibile a ogni caricamento: per questo il sito la
incorpora in un `<iframe>` dentro il modale, ricreato ogni volta che si apre
(non serve nessun job di aggiornamento).

**Webcam INGV note ma NON incluse** per mancanza di una fonte affidabile
sulla loro posizione esatta: `Emot`, `Emv`. Se in futuro si trova una fonte
verificata (non un blog, una pagina ufficiale con nome+coordinate), si
possono aggiungere con lo stesso schema.

**Fallback se l'iframe non carica**: sotto l'immagine c'è sempre un link
"apri in una nuova scheda" — in caso INGV introduca protezioni anti-iframe
in futuro (X-Frame-Options), quel link resta la via di riserva.

---

## 7. Funzionalità "ricaduta cenere" (nessuno script, zero backend)

Aggiunta più recente. Mostra la mappa previsionale INGV di dispersione/
ricaduta dei tefra (prodotti piroclastici), **generata sempre ogni giorno**
da INGV come simulazione standard (scenario eruttivo ipotetico applicato ai
venti reali) — **non è specifica di un'eruzione in corso**, va presentata
con quella cornice (c'è già un disclaimer nel modale).

- URL immagine, prevedibile e documentato:
  `https://www.ct.ingv.it/Dati/ASH/ASH_{AAAAMMGG}_{HHMM}.jpg`
- 8 fasce orarie fisse UTC: `0000,0300,0600,0900,1200,1500,1800,2100`
- Tutto calcolato **client-side in JavaScript** (funzioni `ashDateStr()`,
  `currentAshSlot()`, `ashImageUrl()` in `index.html`) — nessuno script
  Python, nessun workflow, nessun costo aggiuntivo. È il pezzo più "snello"
  di tutto il sito.
- L'utente può cambiare fascia oraria dal selettore nel modale; di default
  si apre sulla fascia più recente rispetto a "adesso" (UTC)
- Se l'immagine non carica, mostra un messaggio di errore invece di un
  riquadro vuoto muto (gestito con `onerror` sull'`<img>`)

---

## 8. Insidie già affrontate (per non ripeterle)

1. **Cache del browser + cache CDN di GitHub Pages**: i fetch dei JSON in
   `index.html` hanno cache-busting esplicito (`?v=timestamp`,
   `{cache:'no-store'}`). Anche così, dopo un commit può volerci un minuto
   perché "pages build and deployment" (workflow automatico di GitHub, non
   nostro) ripubblichi — se il sito "non cambia mai", controllare prima
   quello, non il codice.
2. **`.github` non caricata dal drag&drop del browser**: GitHub a volte
   ignora le cartelle che iniziano con il punto durante l'upload trascinato.
   Va creata a mano da interfaccia web se manca ("Add file → Create new file"
   scrivendo il percorso completo `.github/workflows/nome.yml`).
3. **Workflow "verde" non significa "ha fatto qualcosa"**: un job può avere
   successo (nessun errore) ma non trovare nulla di nuovo da scrivere — va
   sempre controllato anche il file `data/*.json` raw, non solo il colore del
   pallino su Actions.
4. **Errore di rete IPv6 su GitHub Actions**: vedi sezione 5.4. Causa reale
   di gran parte dei fallimenti intermittenti osservati.
5. **URL relativi INGV**: sempre `urljoin()`, mai concatenazione manuale di
   stringhe (vedi 5.2).
6. **Formato data INGV incoerente**: FDSN a volte stringa ISO, non sempre
   epoch numerico (vedi 5.1, `parse_ingv_time()`).
7. **Vista 3D rimossa**: è stata costruita con Three.js (cono wireframe
   stilizzato, toggle 2D/3D, marker orientati per bussola+quota), ma **non
   ha convinto esteticamente l'utente dopo più iterazioni** (illuminazione
   incoerente, webcam nascoste dietro la mesh solida) ed è stata **rimossa
   completamente e deliberatamente**. Se in futuro si volesse riprovare,
   ripartire da zero concettualmente piuttosto che recuperare quel codice —
   non era il problema tecnico, era la direzione estetica a non funzionare.

---

## 9. Cose da NON dimenticare quando si compra il dominio proprio

Riferimenti oggi puntati a `https://etnaora.github.io/etna-ora/`, da
aggiornare ovunque quando si passa a un dominio proprio (es. `etna-ora.it`):
- `index.html`: tag `<link rel="canonical">`, tutti i tag Open Graph
  (`og:url`), Twitter Card, il JSON-LD schema.org (`"url"`)
- `robots.txt`: riga `Sitemap:`
- `sitemap.xml`: tutti i `<loc>`
- Eventuali link hardcoded rimasti in giro (cercare "etnaora.github.io" nel
  progetto prima di considerarlo fatto)
- Registrare il nuovo dominio su **Google Search Console**

---

## 10. Cosa manca / possibili sviluppi futuri (non fatti, solo annotati)

- **Bollettino settimanale multidisciplinare**: nel feed è ancora un item
  finto/statico (`f-0004` originario) — nessuno script lo aggiorna. Bassa
  priorità (si aggiorna una volta a settimana), ma è l'ultimo pezzo "mock"
  rimasto nel feed.
- **Tremore vulcanico "vero"**: quello attuale (`type=tremore`, item
  `f-0001`) è ancora **statico/finto**, mai collegato a un dato reale.
  Richiederebbe scaricare le forme d'onda sismiche grezze e calcolarne
  l'RMS (es. con la libreria ObsPy) — tecnicamente il pezzo più complesso
  di tutti quelli discussi, deliberatamente rimandato.
- **Le due webcam INGV non mappate** (Emot, Emv) — vedi sezione 6.
- **App mobile**: discusso ma non avviato. Percorso consigliato se si
  riprende: PWA gratuita prima di tutto (manifest.json + service worker),
  poi eventualmente Google Play via Trusted Web Activity (~25$ una tantum),
  App Store solo se il progetto cresce abbastanza da giustificare Capacitor
  + Mac + Apple Developer Program (99$/anno) — Apple non accetta un sito
  "travestito" da app senza funzionalità native vere.
- **Dominio proprio + SEO attiva** (Search Console, contenuti più ricchi nel
  tempo) — impostato tecnicamente (sezione 9) ma non ancora attivato.
- **Canale Telegram**: discusso come estensione naturale (lo stesso script
  che rileva "cosa è cambiato" per il feed potrebbe mandare un messaggio a
  un bot Telegram gratuito), mai implementato.
- **Terza telecamera/ubicazioni verificate**: se si trova una fonte
  ufficiale (non un blog) con l'elenco nome↔codice↔coordinate di tutte le
  webcam della rete INGV-OE, vale la pena completare `webcam.json`.

---

## 11. Riferimenti rapidi

- Repo: `github.com/etnaora/etna-ora`
- Sito: `https://etnaora.github.io/etna-ora/`
- INGV Osservatorio Etneo: `ct.ingv.it`
- Comunicati (scraping): `ct.ingv.it/sezioniesterne/Comunicati/ComunicatiVulcanici.php?I=0`
- Webcam ufficiali: `ct.ingv.it/sezioniesterne/webcam/Webcam.php?Vulcano={CODICE}`
- Ricaduta cenere: `ct.ingv.it/Dati/ASH/ASH_{AAAAMMGG}_{HHMM}.jpg`
- Terremoti (FDSN): `webservices.ingv.it/fdsnws/event/1/query`
- Hotspot satellitari: `firms.modaps.eosdis.nasa.gov/api/area/csv/` (mirror:
  `firms2.modaps.eosdis.nasa.gov`, vedi §12)
- Bollettini VAAC Toulouse (Etna): `vaac.meteo.fr/volcanoes/etna/`
- Bollettini settimanali multidisciplinari INGV:
  `ct.ingv.it/index.php/monitoraggio-e-sorveglianza/prodotti-del-monitoraggio/bollettini-settimanali-multidisciplinari`
- SACS (SO₂/cenere satellitare, ESA/BIRA-IASB): `sacs.aeronomie.be`
- Competitor di riferimento (per differenziazione, non per copiare):
  `etnamonitor.it`

---

## 12. Sessione 2026-08 — fix affidabilità hotspot + scheletro 4 nuovi tab + i18n IT/EN

Sessione avviata da tre richieste: (1) risolvere i fallimenti ricorrenti del
job hotspot, (2) aggiungere 4 nuovi tab sul modello di "ricaduta cenere"
(gas, aeroporto, dati scientifici, satelliti), (3) sito bilingue IT/EN.
D'accordo con l'utente, in questa sessione sono stati completati **solo** il
punto (1) e lo **scheletro** dei punti (2)-(3) — non le pipeline dati live
dei 4 nuovi tab, rimandate a sessioni successive.

### 12.1 Fix hotspot — vedi già sezioni 5.3/5.4 sopra, aggiornate
Riassunto: mirror FIRMS di riserva + stato `"stale": true` scritto e
pubblicato onestamente invece di far sparire il problema in silenzio.
**Da fare quando si riprende**: osservare per un paio di settimane se lo
`stale` compare mai nei log/nel sito — se sì, capire se è il mirror a non
bastare (es. entrambi i domini NASA down insieme, raro ma possibile) e in
quel caso valutare una fonte satellite alternativa come **secondo livello
di verifica indipendente** (non come sostituto): MIROVA (mirovaweb.it) è
stato scartato perché non ha un'API pubblica documentata — è un sito pensato
per consultazione umana, non per essere interrogato da uno script.

### 12.2 Nuovo dock di icone circolari collassabili (`#topicDock`)
Sostituisce il vecchio pulsante singolo "ricaduta cenere" (`.ash-btn`, ora
rimosso). 5 pulsanti circolari (44px), impilati verticalmente in basso a
sinistra, sopra al cassetto feed. CSS puro, nessuna libreria: al passaggio
del mouse (`:hover`/`:focus-visible`) il pulsante si espande in larghezza
(`transition: width`) rivelando l'etichetta testuale già prima del click,
esattamente come richiesto. Ogni pulsante ha un pittogramma SVG inline
minimale (stroke `currentColor`, nessun emoji per coerenza visiva con la
palette basalto) e un pallino colorato d'accento nell'angolo, che sparisce
quando il pulsante è espanso. Per aggiungere un sesto tab in futuro: copiare
un blocco `<button class="topic-btn">` in `#topicDock`, scegliere un colore
per `--topic-accent` inline, disegnare l'SVG (viewBox 0 24 24, stroke 1.6),
e aggiungere le chiavi i18n `topic.<nome>` in entrambe le lingue.

### 12.3 Sistema i18n IT/EN
Nessuna libreria: dizionario piatto `I18N = {it:{...}, en:{...}}` in cima
allo script, funzione `t(chiave)` per leggerlo, funzione `setLang(lang)` che:
applica `textContent` a tutti gli elementi `[data-i18n]`, `innerHTML` a
quelli `[data-i18n-html]` (i pochi blocchi con `<strong>`/`<br>`/`<a>`
interni, es. il corpo del modale info), aggiorna `document.documentElement
.lang`, aggiorna lo stato attivo dei due bottoni `#langBtnIt`/`#langBtnEn`,
e **ri-renderizza i blocchi generati via JS** (stato, feed, meta webcam)
riusando l'ultimo dato ricevuto (`window.lastHotspot`, `window.lastFeedItems`,
`window.lastCam`) — senza bisogno di rifare il fetch. La lingua scelta è
salvata in `localStorage['etnaora_lang']` e riletta a ogni caricamento;
default `it`. Per tradurre una nuova stringa statica: aggiungere
`data-i18n="chiave"` (o `data-i18n-html` se contiene markup) all'elemento
nell'HTML, e la stessa chiave in **entrambi** i blocchi `it`/`en` del
dizionario — c'è uno script di verifica rapido (vedi sotto) per controllare
che le chiavi combacino sempre tra le due lingue.

```bash
# verifica che ogni chiave data-i18n usata nell'HTML esista in IT ed EN,
# e che IT ed EN abbiano esattamente lo stesso insieme di chiavi
python3 << 'EOF'
import re
html = open('index.html', encoding='utf-8').read()
keys_used = set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', html))
it_block = re.search(r"it:\s*\{(.*?)\n    \},\n    en:", html, re.S).group(1)
en_block = re.search(r"en:\s*\{(.*?)\n    \},\n  \};", html, re.S).group(1)
it_keys = set(re.findall(r"'([\w.]+)':", it_block))
en_keys = set(re.findall(r"'([\w.]+)':", en_block))
assert not (keys_used - it_keys), f"mancano in IT: {keys_used - it_keys}"
assert not (keys_used - en_keys), f"mancano in EN: {keys_used - en_keys}"
assert not (it_keys ^ en_keys), f"IT/EN disallineati: {it_keys ^ en_keys}"
print("OK")
EOF
```

**Cose NON tradotte in questa sessione (scelta deliberata, basso impatto)**:
meta tag SEO (`<title>`, `og:*`, JSON-LD — restano IT anche con sito in EN,
impatta solo le anteprime social/i motori di ricerca, non l'esperienza in
pagina), `privacy.html`/`cookie.html` (restano solo IT, il link dal modale
info punta sempre lì in entrambe le lingue), nomi propri delle webcam
(vengono da `webcam.json`, dato non tradotto).

### 12.4 I 4 nuovi tab: cosa è reale oggi, cosa manca
Ogni modale ha **contenuto reale scritto a mano** (non segnaposto vuoto):
un badge onesto "in sviluppo", una spiegazione di cosa mostreranno quando
saranno collegati, e link diretti alle fonti ufficiali già verificate in
questa sessione. Nessuna pipeline Python/workflow ancora creata per loro.

| Tab | Fonte scelta per la pipeline futura | Perché | Frequenza reale |
|---|---|---|---|
| Gas (SO₂) | Bollettino settimanale INGV (rete FLAME) + link SACS | Nessun feed SO₂ giornaliero pubblico affidabile trovato | Settimanale (certificato) |
| Aeroporto | VAAC Toulouse (bollettini VAA testuali, ente ICAO) | `aeroporto.catania.it` è una SPA Next.js non scrapabile senza browser headless (costo non compatibile con l'architettura zero-backend) — confermato con l'utente che VAAC va bene come proxy | Ogni 3-6h durante un episodio attivo |
| Dati scientifici | Bollettino settimanale INGV | Tremore RMS "vero" richiede ObsPy + forme d'onda grezze, confermato come pezzo più complesso, rimandato (vedi anche §10) | Settimanale (certificato) |
| Satelliti | Stesso pattern URL diretta di "ricaduta cenere", NASA Worldview + FIRMS | Zero backend, coerente con l'architettura esistente | Da definire in dettaglio nella prossima sessione |

**Prossimi passi consigliati, in ordine**:
1. `scripts/fetch_aviation.py` + `update-aviation.yml` — il più a valore
   immediato (utile ai turisti, dato quasi in tempo reale, fonte già
   individuata e testata in questa sessione: `vaac.meteo.fr/volcanoes/etna/`)
2. `scripts/fetch_gas.py` + `update-gas.yml` — riusa lo stesso pattern di
   `fetch_comunicati.py` (scraping bollettino INGV), aggiungendo
   l'estrazione del dato FLAME dal PDF/pagina settimanale
3. Tab scientifico — stessa pipeline di (2), campo diverso dello stesso
   bollettino (deformazione/tremore invece di gas): si può fare insieme
   costruendo un unico script che estrae più campi dal bollettino settimanale
4. Tab satellitare — costruire gli URL diretti NASA Worldview/FIRMS per
   Etna con parametri fissi (bounding box, layer), sul modello di
   `ashImageUrl()` in `index.html`

### 12.5 Correzioni dopo il primo test in produzione (stesso giorno)

**Push rifiutato tra workflow concorrenti (bug reale, osservato in
produzione)**: `update-comunicati.yml` è fallito con
`! [rejected] main -> main (fetch first)` perché nel frattempo un altro
workflow (probabilmente `update-feed.yml`, che scrive sullo stesso
`data/feed.json`) aveva già pushato. Lo sfasamento dei cron (già presente,
vedi §5) riduce la probabilità ma non la azzera, perché GitHub Actions può
ritardare l'avvio di un run di qualche minuto sotto carico. **Fix**: tutti e
tre i workflow (`update-comunicati.yml`, `update-feed.yml`,
`update-hotspot.yml`) ora hanno uno step di commit con **retry**: se il
push viene rifiutato, fanno `git pull --rebase origin main` e riprovano,
fino a 5 volte con una breve pausa casuale (3-13s) tra un tentativo e
l'altro. Se dopo 5 tentativi fallisce ancora, il job fallisce visibilmente
(email di notifica) invece di perdere l'aggiornamento in silenzio.

**Contenuto dei 4 nuovi tab oscurato su richiesta esplicita**: i modali
`gasModal`/`aeroportoModal`/`scientificoModal`/`satelliteModal`, che nella
prima versione mostravano già una spiegazione + link alle fonti ufficiali,
ora mostrano solo titolo + badge "🛠 coming soon", **senza alcun
riferimento a fonti o dettagli**, finché ogni funzionalità non sarà
sviluppata e testata. Le fonti individuate in §12.4 restano valide come
piano per l'implementazione futura, semplicemente non sono più esposte
nell'interfaccia nel frattempo. Chiavi i18n `gas.*`/`aeroporto.*`/
`scientifico.*`/`satellite.*` (title/body/link) rimosse dal dizionario e
sostituite da un'unica chiave condivisa `comingSoon.badge`.

**Riordino e rinomina pulsanti del dock**: ordine dall'alto verso il basso
ora `ricaduta cenere → gas in atmosfera → dati scientifici al suolo → foto
satellitari → aeroporto Catania`. Nota tecnica per chi tocca `#topicDock`:
il container usa `flex-direction: column-reverse`, quindi **l'ordine dei
`<button>` nel sorgente HTML è l'ordine visivo dal basso verso l'alto**
(il primo `<button>` nel codice appare più in basso). L'etichetta del tab
scientifico è stata rinominata da "Dati scientifici" a **"Dati scientifici
al suolo"** (`topic.scientifico` in entrambe le lingue) — il titolo del
modale (ora comunque nascosto dietro "coming soon") non è stato aggiornato
di conseguenza, da allineare quando si svilupperà quel tab.

---

## 13. Sessione 2026-08 (2) — leggibilità, mappa, bug modali, geografia

Cinque richieste, tutte completate in questa sessione.

### 13.1 Tagline poco leggibile
`.tagline` (sottotitolo "monitoraggio in tempo reale del vulcano" accanto
al wordmark) usava `--ash-muted` a piena densità direttamente sopra la
mappa (nessun pannello sotto), risultando quasi invisibile su certe zone
chiare dei tile. Ora: `color:var(--ash)` con `opacity:0.88`,
`font-weight:500`, `font-size` 11px→12.5px (10px→11px su mobile), più
`text-shadow` (aggiunta anche a `.wordmark h1` per coerenza) per leggibilità
su sfondo variabile. Resta più piccola del titolo come richiesto.

### 13.2 Vista iniziale mappa più ampia
`zoom` iniziale 12→10, `minZoom` 10→9 (stesso `center`). Zoom di dettaglio
al click su una webcam (`flyToPoint`, default `zoom=14`) invariato.

### 13.3 Bug: modali non scrollabili, tasto chiudi irraggiungibile
**Causa**: `.modal-backdrop` centrava il contenuto con
`align-items:center; justify-content:center` ma non aveva `overflow-y`,
quindi se il modale era più alto del viewport (frequente su mobile, es.
tab "ricaduta cenere" con selettore fasce orarie + immagine), la parte
superiore/il tasto chiudi finivano fuori schermo senza alcun modo di
scrollare — unica via d'uscita, ricaricare la pagina. **Fix**: rimossi
`align-items`/`justify-content` dal backdrop, aggiunto `overflow-y:auto` +
padding verticale sul backdrop, e `margin:auto` sul `.modal` stesso (pattern
flex+margin:auto, evita il "flexbug" di clipping che si ha centrando con
`align-items` quando il contenuto supera l'altezza del contenitore). **Vale
per tutti i modali esistenti E futuri** che usano `.modal-backdrop`/`.modal`
— non serve rifare questa fix per i prossimi tab (gas, aeroportuale,
scientifico, satellitare) quando verranno sviluppati.

### 13.4 Webcam mal posizionate
- **`ecv`** ("Crateri Sommitali"): il campo `position` dice "stazione
  arrivo funivia — 2505 m" ma le coordinate erano quelle dei crateri
  sommitali stessi (~3300 m) — **identiche, non a caso, a quelle del
  cerchio termico**, causa diretta anche del punto 13.5. Spostata alla
  stima geografica della stazione di arrivo della funivia/area Montagnola
  (~2500 m), coerente col proprio campo `position`.
- **`ent`** ("Piano Provenzana" nel campo `name`, ma "Osservatorio
  Vulcanologico, 2900 m" nel campo `position`): le coordinate corrispondevano
  a nessuno dei due luoghi reali. Ricerca web ha confermato le coordinate
  ufficiose dell'Osservatorio di Pizzi Deneri (2818 m, versante nord,
  ~2 km dai crateri sommitali): **37.7695, 15.0164** — ora usate. **Attenzione,
  incongruenza NON risolta**: il `name` del campo dice ancora "Piano
  Provenzana", che è in realtà tutt'altro luogo (stazione sciistica a
  ~1800 m, diversi km più in basso e più a nord rispetto a Pizzi Deneri).
  Le coordinate ora puntano a Pizzi Deneri (coerenti col `position`
  "Osservatorio Vulcanologico, 2900 m"), ma se la webcam è fisicamente a
  Piano Provenzana andrebbe corretto il `name`, non le coordinate — da
  verificare con l'utente quale dei due è corretto.
- **`env`** (Rifugio Sapienza): coordinate raffinate su valore noto e
  documentato (37.7000, 14.9958).
- **`epvh`** (Milo, versante est) ed **`emov`** (Montagnola): **non
  toccate**, nessuna fonte sufficientemente affidabile trovata per
  affinarle oltre la stima già presente. Se si trova una fonte ufficiale
  INGV con le coordinate esatte dell'intera rete webcam (vedi anche § 6,
  "terza telecamera/ubicazioni verificate"), è il momento buono per
  sistemare anche queste due.
- **Nota generale**: nessuna di queste coordinate è "da rilievo ufficiale"
  — sono stime ragionate da fonti geografiche pubbliche (guide
  escursionistiche, siti di enti locali), adeguate alla filosofia
  "scenografica non strumentale" del progetto (vedi § 1), non a un uso
  scientifico/di precisione.

### 13.5 Cerchio termico al posto del pallino crateri
Il marker che si accendeva del colore di stato (`--accent`, pilotato da
`hotspot.status`) era un pallino da 16px posizionato **esattamente sulle
stesse coordinate della webcam `ecv`** (vedi 13.4) — da qui la confusione
segnalata ("sembra che si accenda una webcam"). Sostituito con un
`L.circle` (non più un `L.marker` con div-icon): cerchio geografico reale
(raggio in metri, si ridimensiona correttamente con lo zoom), centrato
leggermente a est-sudest dei crateri sommitali per includere anche l'alta
Valle del Bove (dove possono aprirsi nuove bocche a quote più basse),
raggio 3600 m. Colore/opacità di riempimento pilotati da JS (stesso
`--accent`), pulsazione via CSS (`fill-opacity`/`stroke-opacity` animate:
funziona senza `!important` perché le regole CSS con selettore di classe
hanno priorità sugli attributi di presentazione SVG che Leaflet imposta di
default). Centro e raggio sono costanti in cima allo script
(`HOTSPOT_ZONE_CENTER`, `HOTSPOT_ZONE_RADIUS_M`) per essere facili da
ritoccare.

**Idea "vera" scartata per ora (non tecnicamente impossibile, solo
rimandata)**: geolocalizzare i singoli punti hotspot NASA FIRMS invece del
cerchio approssimativo. È fattibile: `fetch_hotspot.py` già scarica il CSV
FIRMS con lat/lon per ogni hotspot, basterebbe scrivere l'elenco (non solo
lo stato aggregato) in `hotspot.json` e disegnare un marker per punto in
`index.html`. Non fatto in questa sessione per restare nello scope delle
5 richieste; buon prossimo passo se si vuole più precisione.
