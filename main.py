import os
import re
import time
import pickle
import threading
import warnings
import requests
import pandas as pd
from flask import Flask
from bs4 import BeautifulSoup

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

alert_cache = set()

def send_alert(message):
    """Envoie un message formaté sur Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
        if res.status_code == 200:
            print("✉️ Alerte Telegram envoyée avec succès !")
        else:
            print(f"⚠️ Telegram HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"❌ Erreur envoi Telegram : {e}")

def clean_and_parse_match(match_text):
    """Analyse et nettoie le texte brut extrait d'une carte Cyber Score."""
    
    # 1. Extraction Map et Format
    map_match = re.search(r'(MAP\s*\d+)', match_text)
    bo_match = re.search(r'(BO\s*\d+)', match_text)
    
    map_str = map_match.group(1) if map_match else "MAP 1"
    bo_str = bo_match.group(1) if bo_match else "BO3"
    
    # 2. Extraction du Score
    score_match = re.search(r'(\d+\s*-\s*\d+)', match_text)
    score_str = score_match.group(1) if score_match else "0 - 0"
    
    # 3. Extraction de la Ligue / Tournoi
    league_str = "Ligue Inconnue"
    tier_split = re.split(r'T\s*ier\s*[-–]\s*\d+', match_text, flags=re.IGNORECASE)
    
    if len(tier_split) > 1:
        league_raw = tier_split[1].strip()
        league_raw = re.sub(r'^(Quick view|Add to favorites)\s*', '', league_raw, flags=re.IGNORECASE)
        league_str = league_raw
    else:
        league_match = re.search(r'([A-Za-z0-9\s]+(?:League|Masters|Cup|Trophy|Tournament)[A-Za-z0-9\s/]+)', match_text)
        if league_match:
            league_str = league_match.group(1).strip()

    # 4. Nettoyage du bloc équipes
    clean = match_text
    noise_patterns = [
        r'LIVE', r'MAP\s*\d+', r'BO\s*\d+', r'Quick view', r'Add to favorites',
        r'Draft', r'T\s*ier\s*[-–]\s*\d+', r'\+?\d+(\.\d+)?k?', r'\d+:\d+', r'\d+\s*-\s*\d+'
    ]
    
    for pattern in noise_patterns:
        clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
        
    if league_str != "Ligue Inconnue":
        clean = clean.replace(league_str, "")

    clean = re.sub(r'\b\d+\.\d+\b', '', clean)

    words = clean.split()
    unique_words = []
    for w in words:
        if len(w) > 1 and (not unique_words or unique_words[-1] != w):
            unique_words.append(w)
            
    teams_raw = " ".join(unique_words)

    return {
        "map": f"{map_str} ({bo_str})",
        "score": score_str,
        "teams_raw": teams_raw,
        "league": league_str
    }

def get_live_cyberscore_matches():
    """Scrape Cyber Score avec des headers contournant le blocage Cloudflare."""
    url = "https://cyberscore.live/en/matches/"
    
    # En-têtes complets navigateur desktop
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Referer": "https://cyberscore.live/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    parsed_matches = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"🌐 Statut HTTP CyberScore : {response.status_code}")
        
        if response.status_code != 200:
            print("⚠️ Réponse non valide de CyberScore.")
            return parsed_matches

        soup = BeautifulSoup(response.text, "html.parser")
        live_badges = [elem for elem in soup.find_all(string=True) if "LIVE" in elem]
        print(f"🔍 Badges 'LIVE' repérés dans le HTML : {len(live_badges)}")
        
        extracted_raw = []

        for badge in live_badges:
            current = badge.parent
            card = None
            for _ in range(6):
                if current and current.name in ["a", "div", "article", "li"]:
                    text_length = len(current.get_text(" ", strip=True))
                    if 40 <= text_length <= 300:
                        card = current
                        break
                if current:
                    current = current.parent

            if card:
                full_text = " ".join(card.get_text(" ", strip=True).split())
                if full_text not in extracted_raw:
                    extracted_raw.append(full_text)

        for raw_text in extracted_raw:
            match_data = clean_and_parse_match(raw_text)
            # Clé unique basée sur équipes + map pour éviter de spammer mais réémettre si changement
            match_data["match_key"] = f"{match_data['teams_raw']}_{match_data['map']}"
            parsed_matches.append(match_data)

    except Exception as e:
        print(f"❌ Erreur Scraping : {e}")
        
    return parsed_matches

def get_opendota_live_match(teams_raw):
    """Tente de trouver le match correspondant sur l'API OpenDota Live."""
    try:
        res = requests.get("https://api.opendota.com/api/live", timeout=10)
        if res.status_code == 200:
            games = res.json()
            words = [w.lower() for w in teams_raw.split() if len(w) > 2]

            for game in games:
                r_name = game.get('radiant_name', '').lower()
                d_name = game.get('dire_name', '').lower()

                for word in words:
                    if word in r_name or word in d_name:
                        return game
    except Exception as e:
        print(f"⚠️ Erreur API OpenDota : {e}")
    return None

def analyze_and_predict(match_data):
    """Construit et envoie la notification Telegram."""
    try:
        teams = match_data["teams_raw"]
        league = match_data["league"]
        map_info = match_data["map"]
        score = match_data["score"]

        msg = (
            f"🔴 *MATCH EN DIRECT DÉTECTÉ*\n\n"
            f"🏆 Ligue : *{league}*\n"
            f"🗺️ Carte : `{map_info}` | Score : `{score}`\n"
            f"👥 Équipes : *{teams}*\n"
        )

        live_data = get_opendota_live_match(teams)

        if live_data:
            match_id = live_data.get('match_id')
            r_score = live_data.get('radiant_score', 0)
            d_score = live_data.get('dire_score', 0)
            duration = live_data.get('duration', 0)
            radiant_name = live_data.get('radiant_name', 'Radiant')
            dire_name = live_data.get('dire_name', 'Dire')

            duration_minutes = duration / 60.0
            kill_diff = r_score - d_score
            kill_ratio = (r_score + 1) / (d_score + 1)

            if model and duration >= 30:
                features = pd.DataFrame([[r_score, d_score, kill_diff, kill_ratio, duration, duration_minutes]], 
                                        columns=['radiant_score', 'dire_score', 'kill_diff', 'kill_ratio', 'duration', 'duration_minutes'])
                prob_radiant = model.predict_proba(features)[0][1] * 100
                leader = radiant_name if prob_radiant >= 50 else dire_name
                confiance = prob_radiant if prob_radiant >= 50 else (100 - prob_radiant)

                msg += (
                    f"\n⚡ *PRÉDICTION XGBOOST*\n"
                    f"🆔 Match ID : `{match_id}`\n"
                    f"⚔️ *{radiant_name}* vs *{dire_name}*\n"
                    f"⏱️ Temps : {int(duration_minutes)} min\n"
                    f"🎯 Avantage : *{leader}* ({confiance:.1f}%)\n"
                )

        send_alert(msg)

    except Exception as e:
        print(f"❌ Erreur analyse match : {e}")

def run_bot():
    print("🚀 Boucle de scraping Render démarrée...")
    send_alert("⚙️ **Bot Dota 2 mis à jour et opérationnel sur Render !**")

    while True:
        try:
            live_matches = get_live_cyberscore_matches()
            print(f"📡 Scan terminé : {len(live_matches)} match(s) LIVE extrait(s).")
            
            new_alerts = 0
            for match in live_matches:
                key = match["match_key"]
                if key not in alert_cache:
                    analyze_and_predict(match)
                    alert_cache.add(key)
                    new_alerts += 1
            
            print(f"📊 {new_alerts} nouvelle(s) alerte(s) envoyée(s).")

        except Exception as e:
            print(f"❌ Erreur dans le cycle du bot : {e}")
        
        time.sleep(120)  # Scan toutes les 2 minutes

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
