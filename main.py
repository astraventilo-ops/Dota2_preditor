import os
import asyncio
import base64
import httpx

# Configuration du chemin pour Playwright Chromium sur Render
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.abspath(".local-browsers")

from fastapi import FastAPI, BackgroundTasks, HTTPException
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

app = FastAPI(title="Dota 2 Cyberscore Predictor Bot")

# Chargement des variables d'environnement
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8594543473")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LKA92INHOad-gQJs2JCU2HBNB34_ijL-WCM20aQf8JZA")


async def send_telegram(photo_bytes: bytes, caption: str):
    """Envoie la capture d'écran et le pronostic sur Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERR] Tokens Telegram manquants !")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption[:1024],
                "parse_mode": "Markdown"
            },
            files={"photo": ("match.png", photo_bytes, "image/png")}
        )
        if response.status_code != 200:
            print(f"[ERR Telegram] {response.status_code}: {response.text}")


async def analyze_image_with_gemini(image_bytes: bytes) -> str:
    """Appel direct REST à l'API Gemini compatible avec les clés AQ.Ab..."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # Encodage de l'image en base64
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    prompt_text = (
        "Tu es un expert analyste eSport Dota 2. Analyse cette capture d'écran de Cyberscore live :\n"
        "1. Donne le score actuel (Kills), le temps de jeu et la différence de Net Worth (valeur nette).\n"
        "2. Évalue l'état des bâtiments (tours/racks) sur la minimap.\n"
        "3. Analyse rapidement la dynamique des héros/joueurs (KDA, niveau).\n"
        "4. Donne un PRONOSTIC CLAIR : Quelle équipe a le plus fort avantage (Radiant ou Dire) "
        "et explique pourquoi en 3 phrases concises."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            print(f"[ERR Gemini REST] {response.status_code}: {response.text}")
            raise Exception(f"Erreur API Gemini ({response.status_code}) : {response.text}")

        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexErrors):
            return "Impossible d'extraire la réponse de l'analyse Gemini."


async def process_match_pipeline(url: str):
    """Pipeline complet : Playwright -> Gemini REST API -> Telegram."""
    print(f"[*] Traitement lancé pour : {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1100},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(3)
            
            players_btn = page.locator("text=PLAYERS")
            if await players_btn.is_visible():
                await players_btn.click()
                await asyncio.sleep(2)
            
            screenshot = await page.screenshot(full_page=False)
            await browser.close()
            print("[✓] Capture réussie !")
            
            # Analyse de l'image via REST
            analysis = await analyze_image_with_gemini(screenshot)
            
            telegram_msg = f"🎯 *PRONOSTIC LIVE DOTA 2*\n\n{analysis}"
            await send_telegram(screenshot, telegram_msg)
            print("[✓] Pronostic et image envoyés sur Telegram !")
            
        except Exception as e:
            await browser.close()
            err_msg = f"⚠️ *Erreur lors du traitement* :\n`{str(e)}`"
            print(f"[ERR Pipeline] {e}")
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_CHAT_ID}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": err_msg, "parse_mode": "Markdown"}
                    )


@app.get("/")
def home():
    return {"status": "Bot Dota 2 actif sur Render !", "version": "1.1.0"}


@app.get("/analyze")
def trigger_analysis(url: str, background_tasks: BackgroundTasks):
    if not url or "cyberscore.live" not in url:
        raise HTTPException(status_code=400, detail="URL invalide. Fournis un lien cyberscore.live/en/match/...")
    
    background_tasks.add_task(process_match_pipeline, url)
    return {
        "status": "Analyse lancée",
        "url": url,
        "message": "Le résultat et la capture d'écran vont arriver sur Telegram."
    }
