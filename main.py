import os
import asyncio
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from google import genai

app = FastAPI(title="Dota 2 Cyberscore Predictor Bot")

# Tokens et cles integres (avec fallback automatique)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8594543473")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Lbtp9FNIqojFrUyI9ODlK9SQOEocMlDqe6ibgRETN6wA")

async def send_telegram(photo_bytes: bytes, caption: str):
    """Envoie la capture d'ecran et l'analyse sur Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERR] Tokens Telegram manquants !")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption[:1024],  # Limite Telegram
                "parse_mode": "Markdown"
            },
            files={"photo": ("match.png", photo_bytes, "image/png")}
        )
        if response.status_code != 200:
            print(f"[ERR Telegram] {response.status_code}: {response.text}")

async def process_match_pipeline(url: str):
    """Pipeline autonome : Playwright -> Gemini 2.5 Flash -> Telegram."""
    print(f"[*] Traitement lance pour : {url}")
    
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
            # Navigation vers la page de match Cyberscore
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(3)
            
            # Clic automatique sur l'onglet PLAYERS
            players_btn = page.locator("text=PLAYERS")
            if await players_btn.is_visible():
                await players_btn.click()
                await asyncio.sleep(2)
            
            # Capture d'ecran
            screenshot = await page.screenshot(full_page=False)
            await browser.close()
            print("[✓] Capture reussie !")
            
            # Initialisation du client Gemini
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            
            prompt = (
                "Tu es un expert analyste eSport Dota 2. Analyse cette capture d'écran de Cyberscore live :\n"
                "1. Donne le score actuel (Kills), le temps de jeu et la différence de Net Worth (valeur nette).\n"
                "2. Évalue l'état des bâtiments (tours/racks) sur la minimap.\n"
                "3. Analyse rapidement la dynamique des héros/joueurs (KDA, niveau).\n"
                "4. Donne un PRONOSTIC CLAIR : Quelle équipe a le plus fort avantage (Radiant ou Dire) "
                "et explique pourquoi en 3 phrases concises."
            )
            
            # Requete Gemini Vision
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    genai.types.Part.from_bytes(data=screenshot, mime_type='image/png'),
                    prompt
                ]
            )
            
            analysis = response.text if response.text else "Aucune analyse generee."
            
            # Message Telegram
            telegram_msg = f"🎯 *PRONOSTIC LIVE DOTA 2*\n\n{analysis}"
            await send_telegram(screenshot, telegram_msg)
            print("[✓] Pronostic et image envoyes sur Telegram !")
            
        except Exception as e:
            await browser.close()
            err_msg = f"⚠️ *Erreur lors du traitement* :\n`{str(e)}`"
            print(f"[ERR Pipeline] {e}")
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": err_msg, "parse_mode": "Markdown"}
                    )

@app.get("/")
def home():
    return {"status": "Bot Dota 2 actif sur Render !", "version": "1.0.0"}

@app.get("/analyze")
def trigger_analysis(url: str, background_tasks: BackgroundTasks):
    """Route pour declencher une analyse de match."""
    if not url or "cyberscore.live" not in url:
        raise HTTPException(status_code=400, detail="URL invalide. Fournis un lien cyberscore.live/en/match/...")
    
    background_tasks.add_task(process_match_pipeline, url)
    return {
        "status": "Analyse lancée",
        "url": url,
        "message": "Le résultat et la capture d'écran vont arriver sur Telegram."
    }
