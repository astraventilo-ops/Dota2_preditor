import time
import requests
import pickle
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- CONFIGURATION (Remplace par tes vraies valeurs) ---
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle (assure-toi que le fichier .pkl est bien dans ton repo GitHub)
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("✅ Modèle chargé avec succès.")
except Exception as e:
    print(f"❌ Erreur chargement modèle : {e}")
    model = None

alert_cache = {}

def get_live_cyberscore_matches():
    url = "https://cyberscore.live/en/match/"
    matches = []
    with sync_playwright() as p:
        # headless=True est obligatoire pour Render
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(5) 
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    # Adaptation des classes CSS selon le site
    for match in soup.find_all("div", class_="match-card"):
        try:
            teams = match.find_all("span", class_="team-name")
            if len(teams) >= 2:
                matches.append((teams[0].text.strip(), teams[1].text.strip()))
        except: continue
    return matches

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

print("🚀 Bot démarré en mode Cloud (Render)...")

while True:
    try:
        live_teams = get_live_cyberscore_matches()
        print(f"📡 Scan terminé : {len(live_teams)} matchs trouvés.")
        
        for t1, t2 in live_teams:
            # Ici tu peux ajouter la logique OpenDota si nécessaire
            # Pour l'instant, on teste la détection
            print(f"🔍 Détection : {t1} vs {t2}")
        
        time.sleep(300) # Scan toutes les 5 minutes pour économiser les ressources Render
    except Exception as e:
        print(f"❌ Erreur cycle : {e}")
        time.sleep(60)
