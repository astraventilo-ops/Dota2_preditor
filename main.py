import os
import time
import pickle
import threading
import warnings
import requests
import pandas as pd
from flask import Flask
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore", category=UserWarning)

# --- SERVEUR FLASK (Health Check Render) ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Dota 2 actif sur Render !"

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle XGBoost
model = None
if os.path.exists(MODEL_PATH):
    try:
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        print("✅ Modèle XGBoost chargé avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors du chargement du modèle : {e}")

alert_cache = {}

def send_alert(message):
    """Envoie un message formaté sur Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"❌ Erreur envoi Telegram : {e}")

def get_live_cyberscore_matches():
    """
    Méthode 2 : Interception dynamique du DOM avec Playwright.
    Localise les badges 'LIVE' et extrait le texte de la carte parent.
    """
    url = "https://cyberscore.live/en/match/"
    extracted_matches = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Charger la page et attendre que le JS s'exécute complètement
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            
            # Cibler les éléments contenant 'LIVE'
            live_elements = page.locator("text=LIVE").all()
            
            for elem in live_elements:
                try:
                    # Remonter au bloc parent de la carte de match
                    card = elem.locator("xpath=ancestor::a[1]")
                    if card.count() == 0:
                        card = elem.locator("xpath=ancestor::div[contains(@class, 'match') or contains(@class, 'card')][1]")
                    
                    if card.count() > 0:
                        card_text = card.inner_text().strip()
                        lines = [line.strip() for line in card_text.split("\n") if line.strip()]
                        
                        # Combiner les lignes pour créer une signature unique du match
                        clean_entry = " | ".join(lines)
                        if clean_entry and clean_entry not in extracted_matches:
                            extracted_matches.append(clean_entry)
                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"❌ Erreur Playwright Méthode 2 : {e}")
        
    return extracted_matches

def get_opendota_live_match(team1_name, team2_name):
    """Recherche le match correspondant sur l'API OpenDota Live."""
    try:
        res = requests.get("https://api.opendota.com/api/live", timeout=10)
        if res.status_code == 200:
            games = res.json()
            t1_clean = team1_name.lower().strip()
            t2_clean = team2_name.lower().strip()

            for game in games:
                r_name = game.get('radiant_name', '').lower()
                d_name = game.get('dire_name', '').lower()

                if (t1_clean in r_name or t1_clean in d_name) or (t2_clean in r_name or t2_clean in d_name):
                    return game
    except Exception as e:
        print(f"⚠️ Erreur API OpenDota : {e}")
    return None

def analyze_and_predict(match_raw_text):
    """Analyse le contenu extrait, interroge OpenDota et exécute la prédiction."""
    try:
        # Découpage du texte récupéré pour identifier les noms d'équipes
        lines = match_raw_text.split(" | ")
        team1 = lines[1] if len(lines) > 1 else "Équipe 1"
        team2 = lines[-1] if len(lines) > 2 else "Équipe 2"

        live_data = get_opendota_live_match(team1, team2)

        if not live_data:
            # Notification directe du match Cyber Score si absent d'OpenDota
            msg = (
                f"🎮 **Match LIVE détecté sur Cyber Score !**\n\n"
                f"📋 `{match_raw_text}`"
            )
            send_alert(msg)
            return

        match_id = live_data.get('match_id')
        r_score = live_data.get('radiant_score', 0)
        d_score = live_data.get('dire_score', 0)
        duration = live_data.get('duration', 0)
        
        radiant_name = live_data.get('radiant_name', team1)
        dire_name = live_data.get('dire_name', team2)

        if duration < 30:
            return

        # Calcul des features pour XGBoost
        kill_diff = r_score - d_score
        kill_ratio = (r_score + 1) / (d_score + 1)
        duration_minutes = duration / 60.0

        features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

        if model:
            prob_radiant = model.predict_proba(features)[0][1] * 100
            leader = radiant_name if prob_radiant >= 50 else dire_name
            confiance = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            msg = (
                f"⚡ *PRÉDICTION MATCH EN DIRECT*\n\n"
                f"🆔 Match ID : `{match_id}`\n"
                f"⚔️ *{radiant_name}* vs *{dire_name}*\n"
                f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n\n"
                f"🎯 Avantage : *{leader}*\n"
                f"📊 Probabilité : *{confiance:.1f}%*\n"
            )
            send_alert(msg)
        else:
            send_alert(f"🎮 **Match en direct :** `{radiant_name}` vs `{dire_name}`\nScore: {r_score} - {d_score}")

    except Exception as e:
        print(f"❌ Erreur analyse match : {e}")

def run_bot():
    print("🚀 Boucle de scraping (Méthode 2) démarrée...")
    send_alert("⚙️ **Passage à la Méthode 2 (Sélecteurs Playwright Négociés) !**\nScan actif...")

    while True:
        try:
            live_matches = get_live_cyberscore_matches()
            print(f"📡 Scan terminé : {len(live_matches)} cartes LIVE extraites.")
            
            for match_text in live_matches:
                if match_text not in alert_cache:
                    analyze_and_predict(match_text)
                    alert_cache[match_text] = True

        except Exception as e:
            print(f"❌ Erreur dans le cycle du bot : {e}")
        
        time.sleep(180)  # Vérification toutes les 3 minutes

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
