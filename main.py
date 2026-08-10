import os
import time
import pickle
import threading
import warnings
import requests
from flask import Flask
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Ignore le warning de version XGBoost
warnings.filterwarnings("ignore", category=UserWarning)

# --- 1. CONFIGURATION DU SERVEUR FLASK (Pour la gratuité Render) ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Dota 2 actif sur Render (Plan Gratuit) !"

@app.route("/healthz")
def health_check():
    return "OK", 200

# --- 2. CONFIGURATION BOT & SCRAPING ---
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle
model = None
if os.path.exists(MODEL_PATH):
    try:
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        print("✅ Modèle chargé avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors du chargement du modèle : {e}")
else:
    print(f"⚠️ Fichier {MODEL_PATH} introuvable.")

def get_live_cyberscore_matches():
    url = "https://cyberscore.live/en/match/"
    matches = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            soup = BeautifulSoup(page.content(), "html.parser")
            browser.close()

        for match in soup.find_all("div", class_="match-card"):
            try:
                teams = match.find_all("span", class_="team-name")
                if len(teams) >= 2:
                    matches.append((teams[0].text.strip(), teams[1].text.strip()))
            except:
                continue
    except Exception as e:
        print(f"❌ Erreur Scraping Playwright : {e}")
    return matches

def run_bot():
    print("🚀 Boucle de scraping démarrée...")
    while True:
        try:
            live_teams = get_live_cyberscore_matches()
            print(f"📡 Scan terminé : {len(live_teams)} matchs trouvés.")
            for t1, t2 in live_teams:
                print(f"🔍 Match en direct : {t1} vs {t2}")
        except Exception as e:
            print(f"❌ Erreur cycle bot : {e}")
        
        # Scan toutes les 5 minutes
        time.sleep(300)

# --- 3. DÉMARRAGE DU PROGRAMME ---
if __name__ == "__main__":
    # Lancement du bot dans un thread séparé
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Démarrage du serveur Flask sur le port fourni par Render (ou 10000 par défaut)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
