from fastapi import FastAPI
from playwright.async_api import async_playwright
import json

app = FastAPI()

@app.get("/match/{match_slug}")
async def get_match_data(match_slug: str):
    url = f"https://cyberscore.live/en/matches/{match_slug}/"
    
    async with async_playwright() as p:
        # Lancement de Chromium Headless avec gestion Cloudflare
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Interception des requêtes API/WebSocket exécutées par le JS de Cyberscore
        json_responses = []
        
        async def handle_response(response):
            if "api" in response.url or "json" in response.url:
                try:
                    data = await response.json()
                    json_responses.append({"url": response.url, "data": data})
                except Exception:
                    pass

        page.on("response", handle_response)

        # Chargement complet de la page (exécution du JS React)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Récupération de l'état du DOM rendu
        content = await page.content()
        await browser.close()
        
        return {
            "status": "success",
            "captured_api_calls": json_responses,
            "html_rendered_length": len(content)
        }
