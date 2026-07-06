name: Aggiorna hotspot termico Etna

on:
  schedule:
    # Ogni 30 minuti: i passaggi satellitari VIIRS non sono comunque più
    # frequenti di qualche ora, ma un controllo più ravvicinato non costa
    # nulla su repository pubblico e ci fa vedere prima un nuovo dato.
    - cron: "*/30 * * * *"
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  update-hotspot:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Imposta Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Installa dipendenze
        run: pip install requests

      - name: Aggiorna data/hotspot.json
        env:
          FIRMS_MAP_KEY: ${{ secrets.FIRMS_MAP_KEY }}
        run: python3 scripts/fetch_hotspot.py

      - name: Commit se ci sono cambiamenti
        run: |
          git config user.name "etna-bot"
          git config user.email "actions@users.noreply.github.com"
          git add data/hotspot.json
          git diff --cached --quiet || git commit -m "Aggiorna hotspot termico [automatico]"
          git push
