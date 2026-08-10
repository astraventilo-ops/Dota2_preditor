#!/usr/bin/env bash
# exit on error
set -o errexit

# Installation des dépendances
pip install -r requirements.txt

# Installation des navigateurs pour Playwright
playwright install chromium
playwright install-deps chromium
