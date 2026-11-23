name: Peter Opportunity Radar - Hourly Cloud Scan

on:
  schedule:
    - cron: '15 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scan-and-notify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run hourly opportunity radar
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
          PWA_BASE_URL: ${{ secrets.PWA_BASE_URL }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python engine/hourly_runner.py

      - name: Commit and push updated feed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/live_feed.json data/gmail_queue.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "chore(radar): hourly opportunity scan update" && git push)
