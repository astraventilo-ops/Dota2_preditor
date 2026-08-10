import time
import pickle
import requests
import threading
import pandas as pd
import numpy as np
from flask import Flask

# -------------------------------------------------------------
# 0. SERVEUR WEB FLASK (POUR LE PLAN GRATUIT RENDER)
# -------------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Dota 2 LIVE actif 24h/24 !", 200

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

# Stocke la dernière probabilité envoyée {match_id: proba} pour éviter les spams
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")

# -------------------------------------------------------------
# 2. SUIVI EXCLUSIF EN LIVE
# -------------------------------------------------------------
def check_live_games():
    """Suit uniquement les matchs en cours et calcule la probabilité XGBoost."""
    if not model:
        return

    url = "https://api.opendota.com/api/live"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return

        live_matches = res.json()

        for match in live_matches:
            league_id = match.get('league_id', 0)
            
            # Filtrage strict : Uniquement les matchs de ligues officielles
            if not league_id or league_id == 0:
                continue

            match_id = match.get('match_id')
            radiant_team = match.get('radiant_name') or 'Radiant'
            dire_team = match.get('dire_name') or 'Dire'
            
            r_score = match.get('radiant_score', 0) or 0
            d_score = match.get('dire_score', 0) or 0
            duration = match.get('duration', 0) or 0
            
            # Attendre au moins 3 minutes de jeu (180s) pour éviter les fausses données de draft
            if duration < 180:
                continue

            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)
            duration_minutes = duration / 60.0

            # Préparation des features pour XGBoost
            features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                    columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

            # Calcul du pronostic
            prob_radiant = model.predict_proba(features)[0][1] * 100
            
            leader = radiant_team if prob_radiant >= 50 else dire_team
            confiance_live = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            last_prob = live_last_predictions.get(match_id, None)

            # Règle d'envoi : 1er message au coup d'envoi OR variation de plus de 15% de probabilité
            if last_prob is None or abs(confiance_live - last_prob) >= 15.0:
                
                header = "⚡ *DÉMARRAGE MATCH LIVE*" if last_prob is None else "🔄 *REVIREMENT EN LIVE*"
                
                msg = (
                    f"{header}\n\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Kills : {r_score} - {d_score}\n\n"
                    f"🔥 Équipe en tête : *{leader}*\n"
                    f"📊 Confiance du modèle : *{confiance_live:.1f}%*\n"
                )
                
                send_telegram_alert(msg)
                live_last_predictions[match_id] = confiance_live
                print(f"[Live] Alerte envoyée pour le match {match_id} ({confiance_live:.1f}%)")

    except Exception as e:
        print(f"Erreur lors du check Live : {e}")

# -------------------------------------------------------------
# 3. BOUCLE PRINCIPALE
# -------------------------------------------------------------
if __name__ == "__main__":
    send_telegram_alert("🚀 *Mode Live Uniquement Activé !* Le bot ne suit plus que les matchs en direct.")
    print("Démarrage du bot en mode 100% Live...")

    while True:
        check_live_games()
        # Scan des API toutes les 60 secondes
        time.sleep(60)
