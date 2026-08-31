import os
import time
import schedule
import requests
from PIL import Image
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# --- Configuration directe ---
TELEGRAM_BOT_TOKEN = "8840292681:AAHoBm9S1LC9HRDGWhS9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
GOOGLE_API_KEY = "AQ.Ab8RN6KTg1OYFdhKtXP6p-hPg0vu5uztePiemDr_Wqm1gkow" # Note: Assure-toi que c'est une clé Google GenAI valide (commençant normalement par AIza...)

# Initialiser l'IA Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-lite')

def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo_file:
        files = {'photo': photo_file}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
        response = requests.post(url, data=data, files=files)
        return response.json()

def analyse_et_alerte_match(match_url):
    screenshot_path = 'screenshot.png'
    
    # 1. Capturer le screenshot du match avec Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(match_url, timeout=60000)
        time.sleep(3) # Laisser le temps au contenu dynamique de charger
        page.screenshot(path=screenshot_path, full_page=True)
        browser.close()

    # 2. Préparer le prompt d'analyse inspiré de ton style
    img = Image.open(screenshot_path)
    
    prompt = """
    Tu es un expert en analyse de matchs Dota 2 en direct.
    Analyse l'image fournie (capture d'écran d'une page de match live sur cyberscore.live).
    
    Rédige ton analyse en suivant strictement cette structure et ces emojis :
    
    🏆 ANALYSE & PRONOSTIC DOTA 2 LIVE
    ⏱️ STATUT DU MATCH
    - Match : [Nom Radiant] vs [Nom Dire]
    - Temps de jeu : [MM:SS] (Map [N])
    - Score actuel : [Kills R]-[Kills D] ([Avantage kills])

    ⚔️ DYNAMIQUE DU MATCH & MINI-MAP
    - Net Worth / Or : [Analyse de l'écart d'or et de la courbe]
    - Mini-map & Objectifs : [Analyse de la position et de la map]

    🎯 PRONOSTIC FINAL
    🏆 Victoire recommandée (Map [N]) : [Nom de l'équipe]
    💡 Explication : [Explication concise basée sur l'économie et le timing]
    
    Règles : Si le match est en début de partie (moins de 15 minutes), indique clairement dans l'explication qu'on attend que la tranche critique des 15-20 minutes soit atteinte. Sois direct, précis et réponds en français.
    """

    # 3. Appel à l'API Gemini
    response = model.generate_content([prompt, img])
    analyse_texte = response.text

    # 4. Envoi sur Telegram
    send_telegram_photo(screenshot_path, analyse_texte)

    # Nettoyage
    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)

def get_live_matches():
    # Scraping de la page d'accueil des matchs pour récupérer les liens en cours
    match_urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://cyberscore.live/en/matches", timeout=60000)
        time.sleep(3)
        
        # Récupérer les liens de matchs (à adapter selon la structure exacte du site)
        links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
        for link in links:
            if "/match/" in link and link not in match_urls:
                match_urls.append(link)
                
        browser.close()
    return match_urls[:3] # Limiter aux 3 premiers pour les tests

def run_bot_job():
    print("Vérification des matchs en cours...")
    try:
        matches = get_live_matches()
        for url in matches:
            print(f"Analyse du match : {url}")
            analyse_et_alerte_match(url)
            time.sleep(5) # Pause entre chaque match
    except Exception as e:
        print(f"Erreur dans la boucle : {e}")

# Planifier l'exécution (toutes les 10 minutes)
schedule.every(10).minutes.do(run_bot_job)

if __name__ == "__main__":
    print("Bot démarré et en attente...")
    # Premier lancement immédiat pour tester
    run_bot_job()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
