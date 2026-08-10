import time
import pickle
import requests
import threading
import pandas as pd
import numpy as np
from flask import Flask

# -------------------------------------------------------------
# 0. SERVEUR WEB FLASK (KEEP ALIVE RENDER)
# -------------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Dota 2 Predictor actif 24h/24 !", 200

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_web_server, daemon=True).start()

# -------------------------------------------------------------
# 1. CONFIGURATION TELEGRAM ET MODÈLE
# -------------------------------------------------------------
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("✅ Modèle XGBoost chargé avec succès !")
except Exception as e:
    print(f"❌ Erreur lors du chargement du modèle : {e}")
    model = None

live_last_predictions = {}


def send_telegram_alert(message):
    """Envoie une alerte formatée sur Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Erreur Telegram ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")

# -------------------------------------------------------------
# 2. ANALYSE LIVE SANS FILTRE STRICT
# -------------------------------------------------------------
def check_live_games():
    """Scan l'API OpenDota et force l'analyse de tous les matchs en cours."""
    if not model:
        return

    url = "https://api.opendota.com/api/live"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return

        live_matches = res.json()
        print(f"[Scan] {len(live_matches)} matchs détectés sur l'API.")

        for match in live_matches:
            match_id = match.get('match_id')
            if not match_id:
                continue

            # Noms par défaut si l'API OpenDota ne les fournit pas
            radiant_team = match.get('radiant_name') or f"Radiant (ID: {match.get('radiant_team_id', 'N/A')})"
            dire_team = match.get('dire_name') or f"Dire (ID: {match.get('dire_team_id', 'N/A')})"
            
            r_score = match.get('radiant_score', 0) or 0
            d_score = match.get('dire_score', 0) or 0
            duration = match.get('duration', 0) or 0

            # Prise en compte dès 30 secondes de jeu
            if duration < 30:
                continue

            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)
            duration_minutes = duration / 60.0

            # Features pour XGBoost
            features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                    columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

            # Calculation de probabilité
            prob_radiant = model.predict_proba(features)[0][1] * 100
            
            leader = radiant_team if prob_radiant >= 50 else dire_team
            confiance_live = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            last_prob = live_last_predictions.get(match_id, None)

            # Envoi : Premier scan OU évolution >= 8%
            if last_prob is None or abs(confiance_live - last_prob) >= 8.0:
                
                status_header = "⚡ *MATCH EN DIRECT DÉTECTÉ*" if last_prob is None else "🔄 *ÉVOLUTION DU MATCH*"
                
                msg = (
                    f"{status_header}\n\n"
                    f"🆔 Match ID : `{match_id}`\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n\n"
                    f"🎯 Équipe en tête : *{leader}*\n"
                    f"📊 Chance de victoire : *{confiance_live:.1f}%*\n"
                )
                
                send_telegram_alert(msg)
                live_last_predictions[match_id] = confiance_live
                print(f"[Live] Alerte envoyée pour Match {match_id} ({confiance_live:.1f}%)")

    except Exception as e:
        print(f"Erreur lors du scan Live : {e}")

# -------------------------------------------------------------
# 3. BOUCLE PRINCIPALE
# -------------------------------------------------------------
if __name__ == "__main__":
    print("Démarrage du bot en mode détection globale...")
    send_telegram_alert("⚙️ *Mise à jour activée !* Détection élargie de tous les matchs en direct.")

    while True:
        check_live_games()
        time.sleep(30)
