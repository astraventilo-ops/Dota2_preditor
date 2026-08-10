import time
import pickle
import requests
import threading
import pandas as pd
import numpy as np
from flask import Flask

# -------------------------------------------------------------
# 0. SERVEUR WEB FLASK (KEEP ALIVE RENDER - PLAN GRATUIT)
# -------------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Dota 2 Predictor actif 24h/24 !", 200

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# Démarrage du serveur web dans un thread séparé
threading.Thread(target=run_web_server, daemon=True).start()

# -------------------------------------------------------------
# 1. CONFIGURATION TELEGRAM ET MODÈLE
# -------------------------------------------------------------
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle XGBoost
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("✅ Modèle XGBoost chargé avec succès !")
except Exception as e:
    print(f"❌ Erreur lors du chargement du modèle : {e}")
    model = None

# Dictionnaire de mémoire {match_id: derniere_probabilite}
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
            print(f"Erreur d'envoi Telegram ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")

# -------------------------------------------------------------
# 2. ANALYSE ET DÉTECTION LIVE LARGE
# -------------------------------------------------------------
def check_live_games():
    """Analyse tous les matchs en direct renvoyés par l'API OpenDota."""
    if not model:
        return

    url = "https://api.opendota.com/api/live"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return

        live_matches = res.json()

        for match in live_matches:
            match_id = match.get('match_id')
            radiant_team = match.get('radiant_name')
            dire_team = match.get('dire_name')

            # Ignorer uniquement si aucune équipe n'est identifiée
            if not radiant_team and not dire_team:
                continue

            radiant_team = radiant_team or "Radiant"
            dire_team = dire_team or "Dire"
            
            r_score = match.get('radiant_score', 0) or 0
            d_score = match.get('dire_score', 0) or 0
            duration = match.get('duration', 0) or 0

            # Prise en compte dès 1 minute de jeu (60s)
            if duration < 60:
                continue

            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)
            duration_minutes = duration / 60.0

            # Calcul des variables (features) pour XGBoost
            features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                    columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

            # Prédiction
            prob_radiant = model.predict_proba(features)[0][1] * 100
            
            leader = radiant_team if prob_radiant >= 50 else dire_team
            confiance_live = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            last_prob = live_last_predictions.get(match_id, None)

            # Envoi : Premier scan du match OU variation >= 10%
            if last_prob is None or abs(confiance_live - last_prob) >= 10.0:
                
                status_header = "⚡ *ALERTE MATCH EN DIRECT*" if last_prob is None else "🔄 *EVOLUTION DES CHANCES*"
                
                msg = (
                    f"{status_header}\n\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n\n"
                    f"🎯 Équipe en tête : *{leader}*\n"
                    f"📊 Probabilité estimée : *{confiance_live:.1f}%*\n"
                )
                
                send_telegram_alert(msg)
                live_last_predictions[match_id] = confiance_live
                print(f"[Live] Alerte envoyée pour {radiant_team} vs {dire_team} ({confiance_live:.1f}%)")

    except Exception as e:
        print(f"Erreur lors du scan Live : {e}")

# -------------------------------------------------------------
# 3. BOUCLE PRINCIPALE
# -------------------------------------------------------------
if __name__ == "__main__":
    print("Démarrage du bot avec le nouveau Token Telegram...")
    # Notification initiale au démarrage
    send_telegram_alert("🚀 *Bot Predictor Connecté !* Analyse des matchs en direct en cours...")

    while True:
        check_live_games()
        # Pause de 45 secondes entre chaque scan
        time.sleep(45)
