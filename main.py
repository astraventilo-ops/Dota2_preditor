from fastapi import FastAPI
from playwright.async_api import async_playwright

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok", "message": "Scraper Dota 2 opérationnel"}

@app.get("/match/{match_slug}")
async def get_match(match_slug: str):
    url = f"https://cyberscore.live/en/matches/{match_slug}/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Attente du chargement complet du DOM React
        await page.goto(url, wait_until="networkidle", timeout=45000)
        content = await page.content()
        await browser.close()
        
        return {"status": "success", "html_length": len(content)}
