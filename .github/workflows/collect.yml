name: Update repo lists

on:
  schedule:
    - cron: '0 10 * * *'   # каждый день в 10:00 UTC
  workflow_dispatch:        # можно запустить вручную

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: true
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Run search script
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MODELS_ROUTER: ${{ secrets.MODELS_ROUTER }}
        run: python scripts/github_search.py

      - name: Commit and push changes
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "Автообновление списков репозиториев"
          file_pattern: "README.md links/*.md data/**/*.json"
