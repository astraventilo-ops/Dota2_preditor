import time
import requests
import pandas as pd
import pickle
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
MODEL_PATH = "dota_xgb.pkl"

# Chargement du modèle
with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

# Cache pour éviter de spammer Telegram pour le même match
alert_cache = {}

def get_live_cyberscore_matches():
    """Scrape Cyber Score pour trouver les matchs actifs."""
    url = "https://cyberscore.live/en/match/"
    matches = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        time.sleep(3) # Temps pour charger le JS
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    # Note: Adapter la classe 'match-card' selon le HTML réel de la page
    for match in soup.find_all("div", class_="match-card"):
        try:
            teams = match.find_all("span", class_="team-name")
            if len(teams) >= 2:
                matches.append((teams[0].text.strip(), teams[1].text.strip()))
        except: continue
    return matches

def get_opendota_live_data(team1, team2):
    """Cherche dans l'API OpenDota si un match correspond aux équipes trouvées."""
    try:
        r = requests.get("https://api.opendota.com/api/live", timeout=10)
        if r.status_code == 200:
            games = r.json()
            for game in games:
                radiant = game.get('radiant_name', '')
                dire = game.get('dire_name', '')
                # Correspondance simple par nom
                if (team1 in radiant or team1 in dire) and (team2 in radiant or team2 in dire):
                    return game # Retourne toutes les stats du match
        return None
    except: return None

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

# --- BOUCLE PRINCIPALE ---
print("Bot démarré...")
while True:
    try:
        live_teams = get_live_cyberscore_matches()
        for t1, t2 in live_teams:
            match_data = get_opendota_live_data(t1, t2)
            
            if match_data:
                m_id = match_data['match_id']
                # Ici : extraire les stats (radiant_score, dire_score, etc.)
                # features = préparer_features(match_data)
                # proba = model.predict_proba(features)
                
                # Exemple d'envoi d'alerte si nouveau match
                if m_id not in alert_cache:
                    send_alert(f"🚀 Match détecté : {t1} vs {t2} (ID: {m_id})")
                    alert_cache[m_id] = True
        
        time.sleep(60) # Scan toutes les minutes
    except Exception as e:
        print(f"Erreur : {e}")
        time.sleep(60)
