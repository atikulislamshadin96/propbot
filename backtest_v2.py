name: weekly-backtest

on:
  schedule:
    - cron: '0 3 * * 0'   # Weekly Sunday 3 AM UTC
  workflow_dispatch:        # Manual run

concurrency:
  group: backtest
  cancel-in-progress: true

jobs:
  backtest:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run 90-day backtest with funding/OI data
        run: python backtest_v2.py --days 90 --with-foi

      - name: Run purged validation
        run: python purged_validation.py --days 90
        continue-on-error: true

      - name: Generate daily report
        run: python daily_report_v2.py
        continue-on-error: true

      - name: Commit results
        run: |
          git config user.name "propbot[bot]"
          git config user.email "propbot@users.noreply.github.com"
          git add -A reports data
          git diff --cached --quiet || git commit -m "backtest $(date -u +%FT%TZ)"
          git push || echo "push failed (non-fatal)"
