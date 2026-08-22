from fastapi import FastAPI
from playwright.async_api import async_playwright
import json

app = FastAPI()

@app.get("/")
def home():
    return {"status": "online", "service": "Dota 2 Scraper"}

@app.get("/match/{match_slug}")
async def get_match_data(match_slug: str):
    url = f"https://cyberscore.live/en/matches/{match_slug}/"
    
    async with async_playwright() as p:
        # Lancement avec arguments d'isolation pour éviter les erreurs mémoire Render
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu'
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        page = await context.new_page()
        
        # Capture des réponses API en tâche de fond
        api_data = []
        async def on_response(response):
            if "api" in response.url or "json" in response.url or "graphql" in response.url:
                try:
                    data = await response.json()
                    api_data.append({"url": response.url, "payload": data})
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            # Attente de la structure du DOM
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000) # Laisse à React 4s pour afficher les tours/scores
            
            # Récupération du HTML final nettoyé
            rendered_html = await page.content()
            await browser.close()
            
            return {
                "status": "success",
                "match_slug": match_slug,
                "api_responses_captured": len(api_data),
                "api_payloads": api_data,
                "html_rendered": rendered_html
            }

        except Exception as e:
            await browser.close()
            return {"status": "error", "detail": str(e)}
