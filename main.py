import os
import time
import pickle
import threading
import warnings
import requests
from flask import Flask
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Dota 2 actif sur Render !"

TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

alert_cache = {}

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"❌ Erreur envoi Telegram : {e}")

def get_live_cyberscore_matches():
    url = "https://cyberscore.live/en/match/"
    matches = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(4)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        
        # Recherche globale de tous les liens vers les matchs (/en/match/xxxx)
        match_links = soup.find_all("a", href=lambda href: href and "/en/match/" in href)
        
        for link in match_links:
            text = link.get_text(separator=" ", strip=True)
            if text and "vs" in text.lower():
                matches.append(text)

    except Exception as e:
        print(f"❌ Erreur Scraping Playwright : {e}")
    return matches

def run_bot():
    print("🚀 Boucle de scraping démarrée...")
    # Notification de confirmation au démarrage du serveur
    send_alert("🟢 **Bot démarré avec succès sur Render !**\nLe scan des matchs Cyber Score est actif.")

    while True:
        try:
            live_matches = get_live_cyberscore_matches()
            print(f"📡 Scan terminé : {len(live_matches)} matchs détectés.")
            
            for m in live_matches:
                print(f"🔍 Match trouvé : {m}")
                if m not in alert_cache:
                    send_alert(f"🎮 **Match Cyber Score détecté :**\n{m}")
                    alert_cache[m] = True

        except Exception as e:
            print(f"❌ Erreur cycle bot : {e}")
        
        time.sleep(180) # Scan toutes les 3 minutes

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
