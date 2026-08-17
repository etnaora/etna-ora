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

---

## 14. Sessione 2026-08 (3) — punti FIRMS reali al posto del cerchio

Implementata l'opzione "ideale" annotata a fine § 13.5: la mappa ora mostra
i **veri punti di rilevazione satellitare NASA FIRMS**, non solo un'area
indicativa. Il cerchio ampio di § 13.5 **non è stato rimosso**: resta come
fallback automatico quando non ci sono punti da mostrare (dato mock,
giornata di vera quiete satellitare, o pipeline non ancora aggiornata).

### 14.1 `fetch_hotspot.py` — due bounding box distinte
- **`AREA`** (usata per la chiamata a FIRMS): allargata da
  `14.95,37.70,15.05,37.80` a **`14.90,37.68,15.15,37.82`**, per includere
  anche l'alta Valle del Bove nel raggio di osservazione, non solo i
  crateri sommitali.
- **`NARROW_BOUNDS`**: nuova costante, identica alla vecchia `AREA` stretta
  di prima. Usata **solo** per filtrare quali punti contano ai fini dello
  stato (quiete/moderata/alta) — la logica delle soglie (§ 5.3) è
  **invariata**, cambia solo l'input: prima tutti i punti nella bbox
  stretta, ora la stessa identica bbox stretta ma isolata da quella più
  larga usata per il fetch. **Perché la separazione è necessaria**: un
  incendio boschivo sui fianchi bassi del vulcano (dentro la `AREA` larga,
  fuori dalla `NARROW_BOUNDS`) non deve poter far scattare un falso stato
  "alta" — VIIRS non distingue anomalie termiche vulcaniche da quelle di
  un incendio, la distinzione la facciamo noi via posizione.
- **`hotspot.json` ha ora un campo `"points"`**: elenco (max 80,
  `MAX_POINTS_SALVATI`, ordinato per FRP decrescente) di
  `{lat, lng, frp, confidence, acq_date, acq_time}` per **tutti** i punti
  nella bbox larga (quindi include anche eventuali bocche in Valle del
  Bove, anche se non hanno influenza sullo stato aggregato).
- **Non richiede una nuova API key o un nuovo endpoint**: stesso servizio
  FIRMS area-CSV già in uso, semplicemente si legge e si salva anche
  `latitude`/`longitude`/`frp`/`confidence`/`acq_date`/`acq_time` di ogni
  riga invece di scartarle dopo aver calcolato solo l'aggregato.

### 14.2 `index.html` — rendering punti + fallback
`placeCraterMarker(hotspot)` ora:
- se `hotspot.points` non è vuoto → disegna un `L.circleMarker` per punto
  (classe CSS `hotspot-point`, pulsazione più rapida/marcata di prima),
  raggio in pixel scalato (contenuto, min 5 / max 15px) sul FRP via
  `pointRadiusPx()`, popup con FRP/affidabilità/orario di rilevazione
  (nuove chiavi i18n `hotspot.popup.*` e `hotspot.confidence.*`, IT/EN);
- altrimenti → ricade sul cerchio `L.circle` di § 13.5 (classe CSS
  `hotspot-zone`, invariata), con lo stesso centro/raggio di prima
  (`HOTSPOT_ZONE_CENTER`, `HOTSPOT_ZONE_RADIUS_M`).
- I layer disegnati (punti o cerchio) sono ora tracciati in un array
  `hotspotLayers` e ripuliti insieme (`clearHotspotLayers()`) ad ogni
  refresh, invece di una singola variabile `hotspotZone` — necessario per
  poter avere N marker invece di uno solo.
- Richiamata anche da `setLang()` (non solo dal caricamento dati iniziale),
  così il testo del popup segue la lingua selezionata anche senza
  ricaricare i dati.

### 14.3 Cosa NON è cambiato
- Le soglie di stato (`SOGLIA_ALTA_FRP=15`, `SOGLIA_ALTA_COUNT=6`) e la
  loro logica: invariate, vedi § 5.3.
- Il fix IPv4, il mirror FIRMS, la gestione `stale`: invariati, vedi § 5.3/5.4.
- `data/hotspot.json` mock locale: aggiornato allo schema nuovo
  (`hotspot_count_24h`, `points: []`, `stale`, `last_success_at`) per
  restare testabile in locale senza chiave FIRMS — con `points` vuoto
  mostra correttamente il cerchio di fallback.

### 14.4 Prossimo passo naturale, se si vuole ancora più fedeltà
Il colore di ogni punto oggi è unico (`--accent`, lo stesso della pillola
di stato). Si potrebbe differenziare il colore/l'intensità del singolo
punto in base al proprio FRP individuale (non solo alla soglia aggregata),
per distinguere a colpo d'occhio un'anomalia debole da una forte anche
quando lo stato generale è "moderata". Non fatto in questa sessione,
annotato come possibile rifinitura.

---

## 15. Sessione 2026-08 (4) — zoom automatico, stati unificati, bug orario UTC

Tre correzioni, **solo su `index.html`** (nessuna modifica a `fetch_hotspot.py`
o ai JSON in questa sessione).

### 15.1 Zoom-out automatico alla chiusura del modale webcam
Il bottone "Chiudi" di `#camModal` ora richiama anche `flyToInitialView()`,
non solo la chiusura del modale. Nuove costanti in cima allo script:
`MAP_INITIAL_CENTER`/`MAP_INITIAL_ZOOM` (stessi valori passati a `L.map()`,
centralizzati per non doverli duplicare). Riguarda solo la webcam: gli
altri modali (cenere, gas, ecc.) non spostano la mappa all'apertura, quindi
non serve applicare lo stesso fly-back alla chiusura.

### 15.2 Stati "moderata" e "alta" uniti in un unico stato mostrato
**Perché**: due livelli distinti (attività/allerta) sopra la quiete
rischiavano di confondere più che informare — la soglia tra i due non è
mai stata comunicata chiaramente in interfaccia. **Cosa è cambiato, e cosa
no**: `fetch_hotspot.py` continua a scrivere `"status"` a 3 valori
(`quiete`/`moderata`/`alta`, soglie invariate, § 5.3/14.1) — **non
toccato**, per non perdere granularità del dato grezzo se servirà in
futuro. Il **frontend** (`index.html`, `renderStatus()`) ora mostra solo
due stati:
- `quiete` → colore `--mist` (invariato)
- `moderata` **o** `alta` → un solo stato mostrato, **"attività vulcanica
  in corso"** (`status.attiva`, IT/EN), colore **`--alert:#C2410C`**
  (arancione scuro, vicino al rosso — nuova variabile CSS, non riusa
  `--ember` che resta per altri usi decorativi: icona satellite, tag
  tremore, hover webcam).

Le vecchie chiavi i18n `status.moderata`/`status.alta` sono state rimosse
(sostituite da `status.attiva`) in entrambe le lingue.

### 15.3 "Ultimo aggiornamento" sempre visibile accanto allo stato
Sotto la pillola di stato è comparsa una riga più piccola,
`ultimo aggiornamento: gg/mm/aaaa, hh:mm UTC` (`status.updated`,
IT/EN — markup: nuovo contenitore `.status-wrap` che avvolge
`.status-pill` esistente + il nuovo `.status-updated`). Usa
**`hotspot.last_success_at`** (fallback su `generated_at` se assente),
**non** `generated_at` da solo: `last_success_at` è il timestamp
dell'ultimo fetch **riuscito**, che `write_stale_fallback()` non
sovrascrive mai in caso di errore (§ 14 non toccato, il campo esisteva
già). Risultato: la data/ora mostrata è onesta indipendentemente dal buon
esito o meno dell'ultimo job — se il job fallisce, il suffisso
"· dato non aggiornato" (già esistente, § 5.4) compare accanto allo stato
E la data resta congelata all'ultimo successo reale, invece di scrivere
"generated_at" del run fallito (che avrebbe fatto sembrare il dato più
fresco di quanto sia).

### 15.4 Bug: "37 UTC" nei popup dei punti hotspot
**Causa**: il campo `acq_time` di FIRMS è in formato `HHMM` **senza zeri
iniziali** (es. `"37"` = 00:37, non le "ore 37"; `"5"` = 00:05;
`"1205"` = 12:05) — veniva concatenato così com'era, crudo, nel popup.
**Fix**: prima di mostrarlo, il valore viene portato a 4 cifre
(`padStart(4,'0')`) e poi formattato `hh:mm` (`raw.slice(0,2) + ':' +
raw.slice(2,4)`). Il dato salvato in `hotspot.json` da `fetch_hotspot.py`
resta grezzo (invariato) — la formattazione avviene solo in fase di
visualizzazione in `index.html`.

### 15.5 Cosa NON è cambiato / non toccato in questa sessione
- `scripts/fetch_hotspot.py`: nessuna modifica.
- `data/hotspot.json`, `data/webcam.json`: nessuna modifica.
- Soglie `SOGLIA_ALTA_FRP`/`SOGLIA_ALTA_COUNT`: invariate.
- **Nota sulla "quiete" durante l'eruzione in corso (ago. 2026)**: durante
  questa sessione risultava `status: quiete` con zero hotspot rilevati pur
  in presenza di un'eruzione reale confermata da INGV (colate laviche,
  emissione di cenere, aeroporto di Catania chiuso). Verificato che **non
  è un bug della pipeline**: anche un sito indipendente che legge la
  stessa fonte (NASA FIRMS VIIRS) riportava 0 hotspot nello stesso
  momento, quasi certamente per la spessa coltre di cenere/nubi che
  ostacola la rilevazione termica satellitare durante un'eruzione
  esplosiva — un limite noto del rilevamento da satellite, non risolvibile
  lato nostro codice. Da qui la scelta fatta in § 15.2/15.3: se il dato
  satellitare non basta a dare un quadro affidabile, meglio essere
  minimali ma onesti (due soli stati, data di ultimo aggiornamento sempre
  in vista) piuttosto che dare un falso senso di precisione a tre livelli.

---

## 16. Sessione 2026-08 (5) — primo tab con dati reali: avviso aeronautico VAAC

Primo dei 4 tab "coming soon" a diventare reale, seguendo l'ordine
consigliato in § 12.5 punto 1 ("il più a valore immediato"). **Nuovi file**
(nessun file esistente di pipeline toccato): `scripts/fetch_aviation.py`,
`.github/workflows/update-aviation.yml`, `data/aviation.json` (mock locale).
Modificato solo `index.html` (modale `#aeroportoModal` + JS + i18n).

### 16.1 Fonte e formato
VAAC Toulouse pubblica per ogni avviso un file di testo semplice a formato
fisso (non serve fare scraping HTML fragile del contenuto): dalla pagina
`https://vaac.meteo.fr/volcanoes/etna/` si trova la cartella dell'avviso
più recente (slug tipo `211060_20260815072511`, codice volcano ICAO
dell'Etna + timestamp), e la stessa cartella contiene sempre un file
`<slug>_vaa.txt` con il testo canonico. Lo script:
1. scarica la pagina indice e trova **tutti** gli slug che contengono il
   codice `211060` (Etna, per scartare eventuali avvisi di altri vulcani
   che compaiono nella stessa pagina/lista limitrofa);
2. sceglie quello con il timestamp più alto (non si fida dell'ordine con
   cui compaiono nella pagina, potrebbe cambiare);
3. scarica direttamente il `.txt` corrispondente e ne estrae i campi via
   regex riga-per-riga (`DTG`, `ADVISORY NR`, `AVIATION COLOUR CODE`,
   `ERUPTION DETAILS`, `RMK`, `NXT ADVISORY`).

**Verificato con dati reali** (non solo con un mock inventato): durante
questa sessione l'Etna era in eruzione reale con codice colore RED, poi
sceso ad ORANGE lo stesso giorno con "ERUPTION ENDED, ASH CLOUD ONGOING" —
entrambi i formati testuali sono stati testati contro il parser e
funzionano correttamente, inclusa la deduzione `eruption_ongoing`
(`true`/`false`/`null` se il testo non è chiaro).

### 16.2 Schema `data/aviation.json`
```json
{
  "advisory_id": "ETNA.87",
  "advisory_url": "https://vaac.meteo.fr/advisory/2026/.../.../",
  "dtg": "2026-08-15T07:25:00+00:00",
  "advisory_nr": "2026/87",
  "aviation_colour_code": "orange",
  "eruption_details_raw": "testo originale VAAC, invariato",
  "eruption_ongoing": false,
  "remark_raw": "testo originale VAAC, invariato",
  "next_advisory_raw": "testo originale VAAC, invariato",
  "raw_text": "l'intero avviso .txt, per riferimento/debug",
  "generated_at": "...", "last_success_at": "...", "stale": false
}
```
`aviation_colour_code` è sempre uno tra `red`/`orange`/`yellow`/`green`/
`unknown` (normalizzato minuscolo; `unknown` anche se VAAC pubblicasse un
valore imprevisto — non blocchiamo tutto per un campo fuori standard).
I campi `_raw` sono **testo originale non tradotto** (l'avviso VAAC è
sempre in inglese, per definizione — è uno standard ICAO internazionale):
mostrato così com'è in pagina, non tradotto in IT, scelta deliberata per
non rischiare di alterare il significato di un avviso di sicurezza aerea.

### 16.3 Fallback stale — stesso pattern di `fetch_hotspot.py`
Se VAAC non è raggiungibile, `write_stale_fallback()` mantiene l'ultimo
avviso noto ma scrive `"stale": true` (stessa logica, stesso motivo,
niente di nuovo rispetto a § 5.4/14 — vedi lì per la spiegazione estesa).
Il workflow `update-aviation.yml` fa il commit "if: always()" per lo
stesso identico motivo di `update-hotspot.yml`.

### 16.4 `index.html` — modale aeroporto ora reale
Il badge "🛠 coming soon" è sparito solo da `#aeroportoModal` (gli altri
3 — gas, dati scientifici, satelliti — restano "coming soon", non
toccati). Contenuto mostrato: pallino colorato + codice colore aviazione
(rosso/arancione/giallo/verde, con una riga esplicativa di cosa
significa ciascuno — non tutti sanno cosa vuol dire "codice arancione"),
stato eruzione (in corso/conclusa/non specificato), nota testuale VAAC se
presente, id avviso + **stesso `formatUpdatedAt()`/`status.updated`
riusati da § 15.3** per la data di ultimo aggiornamento (coerenza tra i
due tab, stesso linguaggio "ultimo aggiornamento" + eventuale
"· dato non aggiornato" se stale). `renderAviation()` viene richiamata sia
al caricamento dati sia da `setLang()` (come gli altri blocchi dinamici),
e tollera `aviation.json` mancante/non ancora pubblicato mostrando
`aviation.noData` invece di rompersi — il `fetch` di `aviation.json` nel
`Promise.all` ha un `.catch(()=>null)` dedicato apposta per questo, per
non far fallire anche webcam/hotspot/feed se questo singolo file non
esiste ancora la prima volta che il workflow non è ancora girato.

### 16.5 Prossimi passi (roadmap aggiornata)
Con l'aviazione fatta, i prossimi in ordine (§ 12.5 originale, invariato):
1. ~~Tab aeroporto~~ ✅ fatto in questa sessione
2. `scripts/fetch_gas.py` + `update-gas.yml` — riusa il pattern di
   `fetch_comunicati.py` (scraping bollettino INGV settimanale), estrae il
   dato FLAME
3. Tab scientifico — stessa pipeline di (2), campo diverso dello stesso
   bollettino
4. Tab satellitare — URL diretti NASA Worldview/FIRMS, sul modello di
   `ashImageUrl()`

---

## 17. Sessione 2026-08 (6) — tab gas: bollettino settimanale INGV

Secondo tab della roadmap. **Nuovi file**: `scripts/fetch_bollettino.py`,
`.github/workflows/update-bollettino.yml`, `data/bollettino.json` (mock
locale). Modificato solo `index.html` (modale `#gasModal` + JS + i18n).

### 17.1 Perché un solo script per gas E dati scientifici
Il bollettino settimanale INGV è **un unico PDF** con una sezione iniziale
numerata ("1. SINTESI STATO DI ATTIVITA'") che contiene, punto per punto,
esattamente i campi utili sia al tab gas sia al futuro tab scientifico:
1) osservazioni vulcanologiche, 2) sismologia, 3) infrasuono,
4) deformazioni del suolo, 5) geochimica (SO2/CO2/He), 6) osservazioni
satellitari, 7) altre osservazioni (non sempre presente). Non avrebbe
senso scaricare due volte lo stesso PDF con due script diversi: **un solo
script estrae tutte le sezioni**, il tab gas (questa sessione) ne usa solo
una (geochimica/SO2), il tab scientifico (prossima sessione) userà le
altre — già pronte in `data/bollettino.json` da subito, **senza dover
toccare di nuovo la pipeline** quando si costruirà quel tab.

### 17.2 Come funziona `fetch_bollettino.py`
1. Scarica la pagina elenco `.../bollettini-settimanali-multidisciplinari`
   (Joomla DOCman: elenca insieme Etna/Stromboli/Vulcano, settimanali E
   mensili, tutti mischiati per data);
2. filtra via regex **solo** i link che contengono
   `bollettino-Settimanale-...-del-vulcano-Etna-del-{data}` (esclude
   Stromboli, Vulcano, e i bollettini *mensili* dell'Etna — pattern
   testato con un mock che replica la struttura reale osservata su
   `ct.ingv.it`, vedi commit);
3. sceglie la data più alta tra i match trovati (non si fida dell'ordine
   di visualizzazione della pagina);
4. scarica il PDF (verifica la firma `%PDF` prima di procedere, per non
   tentare di leggere una pagina di errore come fosse un PDF valido);
5. estrae il testo **solo delle prime 2 pagine** con `pdfplumber` — la
   sintesi numerata è sempre in pagina 1 su tutti i bollettini controllati,
   non serve processare le 15-22 pagine del documento completo;
6. isola le 7 sezioni con una singola regex a più alternative
   (`HEADER_RE`), gestendo sia il caso normale (confine = inizio della
   sezione successiva) sia l'ultima sezione trovata quando la 7 manca (che
   altrimenti "trabocca" nel testo di pagina 2/piè di pagina — tagliata al
   primo marcatore di piè di pagina o nuovo capitolo, `SPILLOVER_RE`);
7. dalla sezione geochimica (che contiene anche CO2 suolo/falda e rapporto
   isotopico He, non solo SO2) isola con una regex dedicata (`SO2_RE`)
   **solo** la frase sull'SO2, salvata a parte come `so2_estratto` — è
   quella che il tab gas mostra, senza il resto della sezione geochimica
   che è più densa di quanto serva a questo tab.

**Testato con 6 varianti di testo reale** raccolte da bollettini INGV
pubblicati tra febbraio e agosto 2026 (formulazioni della sezione SO2
diverse tra loro: "su un livello medio", "su un livello medio ed in
incremento", con/senza punteggiatura tra una sotto-voce e l'altra) — non
solo un mock inventato a tavolino.

### 17.3 Schema `data/bollettino.json`
```json
{
  "bulletin_date": "2026-08-11",
  "bulletin_url": "https://www.ct.ingv.it/.../file",
  "sections": {
    "vulcanologiche": "...", "sismologia": "...", "infrasuono": "...",
    "deformazioni": "...", "geochimica": "...", "satellitare": "...",
    "altre_osservazioni": null,
    "so2_estratto": "Flusso di SO2 su un livello alto"
  },
  "generated_at": "...", "last_success_at": "...", "stale": false
}
```
Ogni campo di `sections` può essere `null` se quella settimana la voce non
è stata riconosciuta (formato leggermente diverso, sezione assente) — il
resto del bollettino resta comunque utilizzabile, non tutto o niente.

### 17.4 `index.html` — modale gas
Il badge "🛠 coming soon" è sparito solo da `#gasModal` (dati scientifici e
satelliti restano "coming soon"). Contenuto: frase SO2 estratta, settimana
di riferimento del bollettino, **stessi `formatUpdatedAt()`/
`status.updated`/`escapeHtml()` già introdotti per aviazione** (§ 16.4 —
riuso diretto, nessun codice duplicato), link al bollettino completo su
`ct.ingv.it` (href impostato dinamicamente da `renderGas()` sull'URL
specifico dell'ultimo bollettino trovato, non un link fisso alla pagina
indice). `bollettino.json` nel `Promise.all` ha lo stesso `.catch(()=>null)`
di `aviation.json`, per lo stesso motivo (non deve poter rompere
webcam/hotspot/feed se manca).

### 17.5 Cosa NON è cambiato
- `fetch_hotspot.py`, `fetch_aviation.py`, `fetch_comunicati.py`,
  `fetch_terremoti.py`: nessuna modifica.
- Fallback stale: stesso pattern identico a hotspot/aviation (§ 5.4/16.3).

### 17.6 Prossimi passi (roadmap aggiornata)
1. ~~Tab aeroporto~~ ✅
2. ~~Tab gas~~ ✅ fatto in questa sessione
3. **Tab dati scientifici — dato già pronto**, `data/bollettino.json` ha
   già `sections.sismologia`/`.infrasuono`/`.deformazioni`/`.satellitare`
   popolati dallo stesso script di questa sessione: serve "solo" scrivere
   il modale HTML/JS (`renderScientifico()`, sullo stesso modello di
   `renderGas()`), **non serve toccare `fetch_bollettino.py`**.
4. Tab satellitare — URL diretti NASA Worldview/FIRMS, sul modello di
   `ashImageUrl()`

---

## 18. Sessione 2026-08 (7) — tab dati scientifici: nessuna nuova pipeline

Terzo tab della roadmap. **Nessun file di pipeline toccato** — esattamente
come previsto in § 17.6: `data/bollettino.json` conteneva già tutto il
necessario da quando è stato scritto `fetch_bollettino.py` nella sessione
precedente. Modificato solo `index.html` (modale `#scientificoModal` +
`renderScientifico()` + i18n).

### 18.1 Cosa mostra il tab
Quattro sezioni dal bollettino settimanale INGV, ciascuna con etichetta +
testo: **sismologia**, **infrasuono**, **deformazioni del suolo**,
**osservazioni satellitari** (l'area termica in area sommitale osservata
da satellite — complementare, non sovrapposta, ai punti FIRMS già mostrati
in mappa: quella è quasi in tempo reale, questa è la lettura settimanale
aggregata di INGV). La sezione "geochimica" non compare qui: è già
mostrata (nella sua parte SO2) nel tab gas, § 17 — non la duplichiamo.
"Altre osservazioni" (7) non è incluso nel tab: è la sezione meno
strutturata/più raramente presente del bollettino (spesso su temi molto
specifici, es. analisi granulometrica della cenere), lasciata fuori per
tenere il tab leggibile — resta comunque nei dati (`sections.altre_osservazioni`)
se in futuro si vuole aggiungerla.

### 18.2 `renderScientifico(bollettino)`
Stesso identico bollettino già scaricato per il tab gas (nessuna chiamata
di rete aggiuntiva, nessun nuovo file JSON): la funzione filtra le 4
sezioni non vuote (`campi.filter(...)`) e mostra solo quelle
effettivamente presenti quella settimana — se ad esempio "infrasuono"
risultasse `null` (sezione non riconosciuta nel PDF quella settimana, vedi
§ 17.3), il tab la ometterebbe silenziosamente invece di mostrare un campo
vuoto o un errore. Se **tutte e 4** risultano assenti, mostra
`scientific.noData` invece di un modale vuoto. Riusa senza modifiche
`formatUpdatedAt()`, `escapeHtml()`, `status.updated`/`status.staleSuffix`,
e la chiave i18n `gas.bulletinWeek` (stesso testo "Dal bollettino della
settimana del", non serve duplicarla con un nome diverso). Richiamata sia
nel caricamento dati iniziale sia da `setLang()`, come tutti gli altri
blocchi dinamici.

### 18.3 Prossimi passi (roadmap aggiornata)
1. ~~Tab aeroporto~~ ✅
2. ~~Tab gas~~ ✅
3. ~~Tab dati scientifici~~ ✅ fatto in questa sessione
4. **Tab satellitare** — ultimo della lista. A differenza dei tre
   precedenti non richiede scraping: si può costruire con URL diretti a
   immagini satellitari pubbliche (NASA Worldview, GIBS) parametrizzati
   per data/area/livello di zoom sull'Etna, sul modello già in uso in
   `ashImageUrl()` per le mappe di ricaduta cenere (stessa idea, fonte
   diversa) — probabile che non serva nessun nuovo script Python né
   nessun nuovo workflow GitHub Actions, solo `index.html`.

---

## 19. Sessione 2026-08 (8) — tab satellitare: roadmap completata

Quarto e ultimo tab della roadmap originale (§ 12.5). **Nessun nuovo file
Python, nessun nuovo workflow**, esattamente come previsto in § 18.3: a
differenza di aviazione/gas/scientifico, non serve scraping — l'immagine
si costruisce con un URL diretto, verificato contro la documentazione
ufficiale NASA GIBS (non inventato). Modificato solo `index.html`
(modale `#satelliteModal` + JS + i18n + bottone dock).

### 19.1 Fonte: NASA GIBS Snapshot API
`https://wvs.earthdata.nasa.gov/api/v1/snapshot` — stesso servizio dietro
NASA Worldview, pensato apposta per generare "ritagli" statici di immagini
satellitari via URL parametrizzato (data, bounding box, livello,
dimensioni), documentato pubblicamente su `nasa-gibs.github.io/gibs-api-docs`.
Nessuna chiave API richiesta, nessun limite di utilizzo pubblicato per
questo tipo di richieste sporadiche.

**Attenzione all'ordine del bounding box**: l'API GIBS vuole
`south,west,north,east` (verificato sull'esempio ufficiale della
documentazione), **diverso** dall'ordine `west,south,east,north` usato
altrove in questo stesso file per Leaflet/FIRMS (§ 13.4/14.1) — commentato
esplicitamente nel codice per non fare confusione in futuro.

Layer usati:
- `VIIRS_SNPP_CorrectedReflectance_TrueColor` — immagine vero colore,
  risoluzione ~375 m (stesso sensore VIIRS già usato per i punti hotspot,
  § 14 — coerenza di fonte in tutto il sito)
- `VIIRS_SNPP_Thermal_Anomalies_375m_All` — overlay opzionale (checkbox,
  disattivo di default) che sovrappone le anomalie termiche rilevate dallo
  stesso sensore, per un confronto visivo diretto "cosa vede la mappa vs
  cosa vede la foto satellitare quello stesso giorno"
- `Coastlines` — sempre incluso, per orientarsi (costa siciliana)

### 19.2 UX: perché si parte da "ieri" e non da "oggi"
Il passaggio del satellite sull'Italia avviene a metà giornata UTC e GIBS
pubblica con qualche ora di ritardo: aprire il tab e mostrare subito
l'immagine di "oggi" avrebbe una probabilità concreta di restituire
un'immagine vuota/non ancora pronta al primo tentativo, specialmente se
qualcuno consulta il sito la mattina (ora italiana). Il selettore giorni
parte quindi da **ieri** (quasi sempre disponibile) con altri 3 giorni
precedenti selezionabili — stesso pattern a bottoni di `ashSlots` (§ 12.2),
riusato con le stesse classi CSS (`.ash-slots`, `.ash-slot`,
`.ash-image-wrap`) invece di duplicarle con un nome diverso.

### 19.3 Gestione immagine mancante
Stesso pattern di `#ashImage` (§ 12.2): `onerror`/`onload` sull'`<img>`
mostrano/nascondono un messaggio esplicito (`satellite.imgError`) invece
di lasciare un'icona di immagine rotta — importante qui più che altrove,
dato che "nessuna immagine per oggi" è un esito **atteso e frequente**
(nuvole, satellite non passato, dato non ancora pubblicato), non un errore
di rete da segnalare come guasto.

### 19.4 Roadmap — completata
Con questo tab si chiude la lista di 4 elencata in § 12.5:
aeroporto ✅ (§ 16) → gas ✅ (§ 17) → dati scientifici ✅ (§ 18) →
satellitare ✅ (questa sessione). Prossimi sviluppi non hanno più un
ordine "consigliato" prestabilito: da definire in base a cosa interessa
di più in questo momento (es. il suite "check-sicurezza"/registro
subappaltatori per il lavoro, o rifiniture del sito già esistente).

---

## 20. Sessione 2026-08 (9) — estetica topbar/dock + contenuti dei 4 tab

Richieste in due gruppi: estetica (2 punti) e contenuti (4 punti). **Nessun
nuovo workflow GitHub Actions**, un solo campo nuovo in una pipeline
esistente (§ 20.5). Modificati `index.html`, `scripts/fetch_terremoti.py`,
`data/feed.json` (mock).

### 20.1 Sottotitolo di stato troppo trasparente
`.status-updated` (riga "ultimo aggiornamento: …" sotto la pillola di
stato) usava `--ash-muted` + `font-mono` a 10.5px — troppo tenue rispetto
alla `.tagline` accanto al wordmark. Uniformata: stesso `font-body`,
`color:var(--ash)` con `opacity:0.88`, `font-weight:500`, `font-size`
12.5px→11px su mobile (prima 9.5px) — identica a `.tagline`.

### 20.2 Pulsanti del dock: larghezza fissa → calcolata sul testo
Il dock (§ 12.2) usava un'unica `--topic-expand-w:210px` per tutti e 5 i
pulsanti: margine nero vistoso sulle etichette corte ("Ricaduta cenere"),
testo tagliato/illeggibile su quella lunga ("Dati scientifici al suolo").
**Fix**: nuova funzione `fitTopicDockButtons()` (JS, non CSS puro — vedi
sotto perché) che misura `label.scrollWidth` di ogni `.topic-label` e
imposta `--topic-expand-w` per-pulsante = icona (44px) + testo reale +
padding + margine di sicurezza. Richiamata al load, da `setLang()` (IT/EN
hanno lunghezze diverse per la stessa etichetta) e da `document.fonts.ready`
(ricalcolo di sicurezza se il primo giro capita prima che IBM Plex Mono sia
caricato). **Perché non solo CSS**: animare `width` verso `auto`/
`fit-content` non ha supporto cross-browser affidabile per una transizione
fluida; misurare via JS e passare un px esplicito a una CSS custom property
resta la via robusta, coerente con "niente librerie" del progetto.

### 20.3 Tab gas — immagini satellitari SO2
Nuova sezione nel modale gas, sotto la sintesi testuale esistente: mappa
satellitare NASA (layer GIBS `OMPS_NOAA20_SO2_Planetary_Boundary_Layer`,
verificato su gibs.earthdata.nasa.gov — sensore OMPS su NOAA-20, strato
limite planetario, dove si concentra la SO2 vulcanica), stesso pattern
"snapshot diretto per data" già in uso per il tab satellitare (§ 19),
selettore giorno (ieri + 3 precedenti, stesse classi `.ash-slot`
riusate). Bounding box **più larga** della sola Etna (`35.00,10.00,
40.00,18.00`, Sicilia + Mediterraneo centrale) perché una nube di SO2 si
disperde ben oltre il vulcano. Disclaimer esplicito: l'assenza di colore è
il caso più comune (non un errore). Aggiunto anche link a **SACS**
(sacs.aeronomie.be, ESA/BIRA-IASB) — fonte già individuata come
riferimento in § 12.4 ma non ancora esposta in UI, ora linkata come mappa
di approfondimento completa. Nuova funzione `openGasModal()` (sostituisce
il generico `openModalById('gasModal')` sul pulsante del dock) per
inizializzare il selettore giorni prima di aprire il modale, sullo stesso
modello di `openSatelliteModal()`.

### 20.4 Tab dati scientifici — grafico sismicità recente
Nuovo grafico SVG (bar chart, disegnato a mano in JS, nessuna libreria) con
la magnitudo degli eventi sismici più recenti. **Fonte**: non il bollettino
settimanale (le 4 sezioni testuali esistenti restano invariate), ma
`window.lastFeedItems` — lo stesso feed sismico già scaricato per il
cassetto in basso, quindi **nessuna nuova chiamata di rete**. Dichiarato
esplicitamente in UI che questo grafico è quasi in tempo reale, più fresco
delle sezioni testuali sopra (stesso principio di trasparenza già applicato
altrove, es. punti FIRMS vs osservazioni satellitari settimanali, § 18.1).
`renderSeismicChart()` richiamata da `renderFeed()` (quindi automaticamente
anche da `setLang()`, che già richiama `renderFeed()`). Barre colorate per
soglia di magnitudo (`--mist` <2.0, `--sulfur` 2.0–3.0, `--alert` ≥3.0,
stessa palette già in uso altrove nel sito). Se nessun evento ha il campo
`magnitude`, mostra `scientific.chartNoData` invece di un grafico vuoto.

### 20.5 Nuovo campo `magnitude` in `fetch_terremoti.py`
Il grafico di § 20.4 richiede una magnitudo numerica isolata: prima viveva
solo dentro la stringa `title` ("Evento sismico Ml 2.1"), non utilizzabile
per un grafico senza fare parsing fragile della stringa. **Fix minimo**:
aggiunto il campo `"magnitude": round(mag, 1)` (o `null` se INGV non lo
fornisce per quell'evento) agli item `type=sismicita` scritti da
`fetch_terremoti.py` — nessun altro campo toccato, nessuna modifica alla
logica di merge/filtro esistente (§ 5.1, invariata). `data/feed.json` mock
aggiornato con il campo su tutti gli item sismicita esistenti, più due
nuovi eventi mock (`f-0005` Ml 1.4, `f-0006` Ml 2.8) solo per rendere il
grafico leggibile in locale con più di una barra — **dati mock dichiarati
come tali** nel campo `source` del file, non dati reali inventati.

### 20.6 Tab satellitare — Sentinel-2
Aggiunta una sezione sotto il contenuto esistente (VIIRS 375m + toggle
anomalie termiche, invariati): link diretto al **Copernicus Browser**
ufficiale ESA (`browser.dataspace.copernicus.eu`), centrato sull'Etna via
URL con parametri `zoom`/`lat`/`lng`/`themeId` (schema verificato sulla
documentazione ufficiale Copernicus Data Space). **Perché un link e non un
embed diretto come per VIIRS**: a differenza di NASA GIBS (Snapshot API
pubblica, senza chiave, usata per VIIRS/SO2), Sentinel-2 via Copernicus
Data Space richiede una istanza/configurazione WMS con un account per un
embed diretto — niente di equivalente alla semplicità "URL pubblico senza
chiave" del resto del sito. Un link diretto e verificato è stata la scelta
più onesta, coerente con lo stile del sito (mai inventare/promettere un
dato che non si può davvero garantire). Risoluzione dichiarata in UI: 10m
contro i ~375m di VIIRS.

### 20.7 Tab aeroporto — link ufficiale
Aggiunto link diretto a `aeroporto.catania.it/tracking-voli` (pagina
ufficiale "Tracking voli", con partenze/arrivi in tempo reale), sopra il
link VAAC Toulouse già esistente. **Nota**: § 12.4 aveva scartato
`aeroporto.catania.it` come *fonte dati* per la pipeline (SPA Next.js non
scrapabile senza browser headless) — questo resta vero e non è stato
toccato: qui si tratta solo di un **link cliccabile** verso il sito
ufficiale per chi vuole il dettaglio volo-per-volo, non di una nuova fonte
per `fetch_aviation.py`.

### 20.8 Cosa NON è cambiato
- `fetch_hotspot.py`, `fetch_aviation.py`, `fetch_comunicati.py`,
  `fetch_bollettino.py`: nessuna modifica.
- Le 4 sezioni testuali del tab scientifico e il tab gas testuale: logica
  invariata, solo contenuto aggiuntivo sotto.
- Nessun nuovo secret, nessuna nuova chiave API: sia GIBS SO2 sia GIBS
  VIIRS sono la stessa Snapshot API pubblica senza autenticazione già in
  uso da § 19.
