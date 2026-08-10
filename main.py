import os
import time
import pickle
import threading
import warnings
import requests
import pandas as pd
from flask import Flask
from bs4 import BeautifulSoup
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
    Extrait uniquement les matchs marqués 'LIVE' depuis https://cyberscore.live/en/matches/
    """
    url = "https://cyberscore.live/en/matches/"
    live_matches = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Chargement de la page des matchs
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(4)
            
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        
        # Récupération de tous les liens de matchs
        links = soup.find_all("a", href=lambda h: h and "/en/match/" in h)
        
        for link in links:
            text = link.get_text(" ", strip=True)
            
            # FILTRE STRICT : Uniquement si la carte contient 'LIVE'
            if "LIVE" in text:
                # Nettoyage des espaces doubles
                clean_text = " ".join(text.split())
                if clean_text not in live_matches:
                    live_matches.append(clean_text)

    except Exception as e:
        print(f"❌ Erreur Scraping : {e}")
        
    return live_matches

def get_opendota_live_match(team1_name, team2_name):
    """Recherche la partie correspondante sur l'API OpenDota Live."""
    try:
        res = requests.get("https://api.opendota.com/api/live", timeout=10)
        if res.status_code == 200:
            games = res.json()
            t1_clean = team1_name.lower().strip()
            t2_clean = team2_name.lower().strip()

            for game in games:
                r_name = game.get('radiant_name', '').lower()
                d_name = game.get('dire_name', '').lower()

                # Vérifie si l'une des équipes correspond
                if (t1_clean and (t1_clean in r_name or t1_clean in d_name)) or \
                   (t2_clean and (t2_clean in r_name or t2_clean in d_name)):
                    return game
    except Exception as e:
        print(f"⚠️ Erreur API OpenDota : {e}")
    return None

def analyze_and_predict(raw_text):
    """Extrait les équipes du texte LIVE, interroge OpenDota et applique le modèle."""
    try:
        print(f"🔍 Traitement du match LIVE : {raw_text}")
        
        # Tentative d'extraction simplifiée des noms d'équipes
        # Exemple de texte brut : "LIVE MAP 2 BO3 0:1 Moonlight Wispers 12 - 14 PLegion Tier-4..."
        words = raw_text.split()
        
        # Envoi immédiat de l'alerte pour le match LIVE capturé
        msg_live = f"🎮 **MATCH EN DIRECT DÉTECTÉ (Cyber Score) :**\n\n📌 `{raw_text}`"
        
        # Recherche complémentaire sur OpenDota pour prédiction XGBoost
        # Exemple rapide pour tenter de matcher sur OpenDota via les mots principaux
        possible_teams = [w for w in words if len(w) > 3 and w not in ["LIVE", "MAP", "BO3", "Tier-1", "Tier-2", "Tier-3", "Tier-4"]]
        t1 = possible_teams[0] if len(possible_teams) > 0 else ""
        t2 = possible_teams[1] if len(possible_teams) > 1 else ""

        live_data = get_opendota_live_match(t1, t2)

        if live_data:
            match_id = live_data.get('match_id')
            r_score = live_data.get('radiant_score', 0)
            d_score = live_data.get('dire_score', 0)
            duration = live_data.get('duration', 0)
            radiant_name = live_data.get('radiant_name', t1)
            dire_name = live_data.get('dire_name', t2)

            duration_minutes = duration / 60.0
            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)

            if model and duration >= 30:
                features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                        columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])
                prob_radiant = model.predict_proba(features)[0][1] * 100
                leader = radiant_name if prob_radiant >= 50 else dire_name
                confiance = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

                msg_live += (
                    f"\n\n⚡ *PRÉDICTION XGBOOST*\n"
                    f"🆔 Match ID : `{match_id}`\n"
                    f"⚔️ *{radiant_name}* vs *{dire_name}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n"
                    f"🎯 Avantage : *{leader}* ({confiance:.1f}%)"
                )

        send_alert(msg_live)

    except Exception as e:
        print(f"❌ Erreur analyse match : {e}")

def run_bot():
    print("🚀 Boucle de scraping ciblée LIVE démarrée...")
    send_alert("🔴 **Filtre LIVE strict activé sur /en/matches/**\nScan en cours...")

    while True:
        try:
            live_matches = get_live_cyberscore_matches()
            print(f"📡 Scan terminé : {len(live_matches)} match(s) LIVE trouvé(s).")
            
            for match_text in live_matches:
                if match_text not in alert_cache:
                    analyze_and_predict(match_text)
                    alert_cache[match_text] = True

        except Exception as e:
            print(f"❌ Erreur dans le cycle du bot : {e}")
        
        time.sleep(120)  # Scan toutes les 2 minutes

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
