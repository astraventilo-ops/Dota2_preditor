#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Mise à jour de pip et installation des packages Python
python -m pip install --upgrade pip
pip install -r requirements.txt

# 2. Installation de Chromium uniquement (sans privilèges root/sudo)
python -m playwright install chromium
