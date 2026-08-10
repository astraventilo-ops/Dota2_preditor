import time
import pickle
import requests
import pandas as pd
from flask import Flask
import threading

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
STEAM_API_KEY = "VOTRE_CLE_STEAM_API"  # À obtenir gratuitement sur steamcommunity.com/dev/apikey
MODEL_PATH = "dota_xgb.pkl"

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("✅ Modèle XGBoost chargé !")
except Exception as e:
    print(f"❌ Erreur modèle : {e}")
    model = None

live_last_predictions = {}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur Telegram : {e}")

# -------------------------------------------------------------
# RÉCUPÉRATION DIRECTE DE VALVE (STEAM API)
# -------------------------------------------------------------
def check_valve_live_games():
    if not model:
        return

    # Endpoint officiel de Valve pour TOUS les matchs de ligue en direct
    url = f"https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/?key={STEAM_API_KEY}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return
            
        data = res.json().get('result', {}).get('games', [])
        print(f"[Scan Valve] {len(data)} matchs pro en direct détectés.")

        for game in data:
            match_id = game.get('match_id')
            scoreboard = game.get('scoreboard')
            
            if not match_id or not scoreboard:
                continue

            # Informations équipes
            radiant_team = game.get('radiant_team', {}).get('team_name', 'Radiant')
            dire_team = game.get('dire_team', {}).get('team_name', 'Dire')

            r_score = scoreboard.get('radiant', {}).get('score', 0)
            d_score = scoreboard.get('dire', {}).get('score', 0)
            duration = scoreboard.get('duration', 0)

            if duration < 30:
                continue

            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)
            duration_minutes = duration / 60.0

            features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                    columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])

            prob_radiant = model.predict_proba(features)[0][1] * 100
            leader = radiant_team if prob_radiant >= 50 else dire_team
            confiance_live = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

            last_prob = live_last_predictions.get(match_id)

            if last_prob is None or abs(confiance_live - last_prob) >= 8.0:
                msg = (
                    f"⚡ *MATCH EN DIRECT (VALVE)*\n\n"
                    f"🆔 Match ID : `{match_id}`\n"
                    f"⚔️ *{radiant_team}* vs *{dire_team}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min | Score : {r_score} - {d_score}\n\n"
                    f"🎯 Avantage : *{leader}*\n"
                    f"📊 Probabilité : *{confiance_live:.1f}%*\n"
                )
                send_telegram_alert(msg)
                live_last_predictions[match_id] = confiance_live

    except Exception as e:
        print(f"Erreur scan Valve : {e}")
