# Etna, ora

Prototipo del progetto "la cosa più bella e più snella dedicata solo all'Etna".
Mappa scenografica unica (niente dashboard multi-pagina), che mostra:

1. **Stato termico** — pallino pulsante sul cratere sommitale, colore dinamico (quiete → attività)
2. **Webcam di osservazione** — solo quelle nate per il monitoraggio vulcanologico (rete INGV-OE + osservatori dedicati), non le webcam turistiche/panoramiche
3. **Feed INGV** — finestra fissa a 25 elementi, il più recente sempre in evidenza, cassetto scorrevole per lo storico

## Come testarlo ora, gratis

Apri semplicemente `index.html` in un server locale (necessario per il `fetch()` dei JSON in `/data`):

```bash
cd etna-site
python3 -m http.server 8000
# poi apri http://localhost:8000
```

Aprirlo con doppio click (protocollo `file://`) non funziona per il fetch dei JSON — serve un server anche minimale, incluso quello gratuito di GitHub Pages/Netlify una volta pubblicato.

## Dati attualmente mock

Tutto in `/data/*.json` è statico e finto, per testare l'interfaccia. I prossimi passi tecnici (da fare con calma, un pezzo alla volta):

- `data/feed.json` → job periodico (GitHub Actions, gratuito) che scarica da INGV e mantiene la finestra a 25 elementi (FIFO)
- `data/hotspot.json` → job che interroga NASA FIRMS/MIROVA
- `data/webcam.json` → aggiornato manualmente (cambia raramente)

Nessun backend sempre acceso, nessun costo fisso: solo file statici generati periodicamente.

## Testi di attribuzione e disclaimer (riusa questi, non riformularli a caso)

**Disclaimer (già presente nel modale "i" del sito):**
> Non è un servizio ufficiale di allerta. La fonte ufficiale per l'attività vulcanica e sismica resta l'INGV Osservatorio Etneo (ct.ingv.it) e la Protezione Civile.

**Attribuzione dati (già nel footer/attribution della mappa):**
> Dati mappa: OpenTopoMap / OpenStreetMap · Dati vulcanologici: INGV Osservatorio Etneo, NASA FIRMS/MIROVA

Tienile sempre visibili (footer o pannello info), soprattutto se in futuro il sito include affiliazioni commerciali: è quello che rende il progetto credibile e distingue "informazione" da "allerta ufficiale".

## Design token (per restare coerenti quando si aggiungono pagine)

- `--basalt #14120F` sfondo
- `--basalt-panel #1F1B17` pannelli/modali
- `--ash #EDE6DB` testo primario
- `--ash-muted #9C948A` testo secondario
- `--mist #5C7A8A` stato quieto
- `--ember #E8541E` stato attivo
- `--sulfur #FFD166` allerta massima (uso minimo)
- Display: **Fraunces** · Body: **IBM Plex Sans** · Dati/mono: **IBM Plex Mono**

## Fase 2 — primo dato reale collegato: la sismicità

`scripts/fetch_terremoti.py` interroga il webservice ufficiale INGV
(`webservices.ingv.it/fdsnws/event`, licenza CC-BY 4.0) filtrato sull'area
etnea, e aggiorna `data/feed.json` mantenendo solo gli item di tipo
`sismicita` sostituiti (comunicati/tremore restano quelli mock finché non
avranno il loro script), con la finestra fissa a 25 elementi già decisa.

`.github/workflows/update-feed.yml` lo esegue automaticamente ogni 15 minuti,
gratis, e fa il commit del JSON aggiornato — **ma funziona solo una volta che
il progetto è su un vero repository GitHub** (in locale/sandbox non ha senso
farlo girare). Per attivarlo:

1. Carica questa cartella su GitHub (via web upload, come già fatto per il test)
2. Vai su **Settings → Actions → General** e verifica che i workflow siano abilitati
3. Vai sulla tab **Actions** del repo, seleziona "Aggiorna feed sismico Etna" → **Run workflow** per il primo test manuale
4. Da lì in poi girerà da solo ogni 15 minuti

Il tremore vulcanico "vero" (quello con RMS calcolato dal segnale sismico
grezzo) è tecnicamente più pesante — richiede scaricare forme d'onda e
processarle con una libreria come ObsPy — e lo affrontiamo come step
successivo, separato da questo.

## Prima di comprare dominio/hosting

- [ ] Sostituire i placeholder in `privacy.html` e `cookie.html` con dati reali (titolare, email) o generarli via Iubenda free tier
- [ ] Verificare disponibilità dominio (.it e .com)
- [ ] Scegliere hosting statico gratuito per il test pubblico (Cloudflare Pages / Netlify / GitHub Pages)
- [ ] Impostare il primo job GitHub Actions per un solo dato (partire dal tremore, poi aggiungere il resto)
