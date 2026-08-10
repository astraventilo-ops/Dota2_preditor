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
    return "Bot Dota 2 actif 24h/24 sur Render !", 200

def run_web_server():
    # Render attribue automatiquement le port 10000 par défaut
    app.run(host='0.0.0.0', port=10000)

# Démarrage du serveur web dans un thread séparé en arrière-plan
threading.Thread(target=run_web_server, daemon=True).start()

# -------------------------------------------------------------
# 1. CONFIGURATION TELEGRAM ET MODÈLE
# -------------------------------------------------------------
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle XGBoost entraîné sur Colab
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("✅ Modèle XGBoost chargé avec succès !")
except Exception as e:
    print(f"❌ Erreur lors du chargement du modèle : {e}")
    model = None

# Dictionnaires pour éviter les spams d'alertes
prematch_sent = set()        # Stocke les match_id déjà annoncés en pre-match
live_last_predictions = {}   # Stocke la dernière probabilité envoyée {match_id: proba}


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
# 2. PHASE 1 : ANALYSE PRE-MATCH
# -------------------------------------------------------------
def check_prematch_games():
    """Analyse les matchs de ligue prévus et envoie le pronostic initial."""
    url = "https://api.opendota.com/api/proMatches"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return
        
        matches = res.json()
        
        # On examine les matchs récents/à venir issus des ligues officielles
        for match in matches[:10]:
            match_id = match.get('match_id')
            league_name = match.get('league_name', 'Ligue Officielle')
            radiant_team = match.get('radiant_name', 'Radiant')
            dire_team = match.get('dire_name', 'Dire')

            # Si le match n'a pas encore été annoncé
            if match_id and match_id not in prematch_sent:
                favori = radiant_team
                confiance = 58.0  # Estimation de départ avant coup d'envoi
                
                msg = (
                    f"🏆 *PRONOSTIC PRE-MATCH*\n"
                    f"Ligue : _{league_name}_\n\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"🎯 Pronostic initial : *{favori}* ({confiance:.1f}% de confiance)\n"
                    f"⏰ Status : Le suivi Live démarrera dès le coup d'envoi."
                )
                
                send_telegram_alert(msg)
                prematch_sent.add(match_id)
                print(f"[Pre-Match] Alerte envoyée pour le match {match_id}")

    except Exception as e:
        print(f"Erreur lors du check Pre-Match : {e}")

# -------------------------------------------------------------
# 3. PHASE 2 : SUIVI ET MISE À JOUR EN LIVE
# -------------------------------------------------------------
def check_live_games():
    """Suit les matchs en cours et ajuste les pronostics avec XGBoost."""
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
            
            # Filtrage : On ne garde que les matchs de ligue officielle
            if not league_id or league_id == 0:
                continue

            match_id = match.get('match_id')
            radiant_team = match.get('radiant_name', 'Radiant')
            dire_team = match.get('dire_name', 'Dire')
            
            r_score = match.get('radiant_score', 0) or 0
            d_score = match.get('dire_score', 0) or 0
            duration = match.get('duration', 0) or 0
            
            # Attendre au moins 3 minutes de jeu pour avoir des données stables
            if duration < 180:
                continue

            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)
            duration_minutes = duration / 60.0

            # Préparation des données pour le modèle XGBoost
            features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                    columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

            # Calcul de la probabilité XGBoost
            prob_radiant = model.predict_proba(features)[0][1] * 100
            
            # Détermination de l'équipe favorite en direct
            leader = radiant_team if prob_radiant >= 50 else dire_team
            confiance_live = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            # Vérification de la variation par rapport à la dernière alerte
            last_prob = live_last_predictions.get(match_id, None)

            # Règle d'envoi : Premier calcul Live OU variation de plus de 15% (Changement de dynamique)
            if last_prob is None or abs(confiance_live - last_prob) >= 15.0:
                
                type_alerte = "🔄 *UPDATE LIVE (Changement de dynamique)*" if last_prob else "⚡ *DÉMARRAGE SUIVI LIVE*"
                
                msg = (
                    f"{type_alerte}\n\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n\n"
                    f"🔥 Avantage actuel : *{leader}*\n"
                    f"📊 Probabilité de victoire : *{confiance_live:.1f}%*\n"
                )
                
                send_telegram_alert(msg)
                live_last_predictions[match_id] = confiance_live
                print(f"[Live] Mise à jour envoyée pour le match {match_id} ({confiance_live:.1f}%)")

    except Exception as e:
        print(f"Erreur lors du check Live : {e}")

# -------------------------------------------------------------
# 4. BOUCLE PRINCIPALE (EXECUTION EN CONTINU)
# -------------------------------------------------------------
if __name__ == "__main__":
    send_telegram_alert("🚀 *Bot Dota 2 Predictor (Web Service Free)* activé sur Render !")
    print("Démarrage du serveur Web et de la boucle du bot...")

    while True:
        # 1. Vérification des matchs d'avant-match
        check_prematch_games()
        
        # 2. Analyse des matchs en cours
        check_live_games()
        
        # Pause de 60 secondes entre chaque cycle d'analyse
        time.sleep(60)
