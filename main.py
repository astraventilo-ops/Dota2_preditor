import os
import asyncio
import httpx
from fastapi import FastAPI, BackgroundTasks
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from google import genai

app = FastAPI()

# Tokens d'environnement (à configurer sur Render)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Client Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

async def send_telegram(photo_bytes: bytes, caption: str):
    """Envoie la capture et l'analyse sur ton Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    async with httpx.AsyncClient() as client:
        await client.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("match.png", photo_bytes, "image/png")}
        )

async def process_match_pipeline(url: str):
    """Pipeline autonome : Playwright -> Gemini Vision -> Telegram."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1100},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Clic sur l'onglet PLAYERS
            players_btn = page.locator("text=PLAYERS")
            if await players_btn.is_visible():
                await players_btn.click()
                await asyncio.sleep(1.5)
            
            screenshot = await page.screenshot(full_page=False)
            await browser.close()
            
            # Analyse Gemini Vision
            prompt = (
                "Analyse cette capture de Dota 2 (score, Net Worth, KDA, structures sur la minimap, "
                "stats des joueurs). Donne un pronostic clair en 4-5 lignes : "
                "Qui a l'avantage (Radiant/Dire) et pourquoi ?"
            )
            
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    genai.types.Part.from_bytes(data=screenshot, mime_type='image/png'),
                    prompt
                ]
            )
            
            analysis = response.text if response.text else "Analyse indisponible."
            await send_telegram(screenshot, f"🎯 *PRONOSTIC LIVE DOTA 2*\n\n{analysis}")
            
        except Exception as e:
            await browser.close()
            print(f"[ERR] Échec du pipeline : {e}")

@app.get("/")
def home():
    return {"status": "Bot Dota 2 actif sur Render !"}

@app.get("/analyze")
def trigger_analysis(url: str, background_tasks: BackgroundTasks):
    """Route pour lancer une analyse en arrière-plan."""
    background_tasks.add_task(process_match_pipeline, url)
    return {"message": "Analyse lancée en arrière-plan ! Le résultat arrive sur Telegram."}
