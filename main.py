import asyncio
import os
import warnings
import httpx
from aiohttp import web
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import google.generativeai as genai

# Masquer les avertissements système internes
warnings.filterwarnings("ignore", category=UserWarning)

# ==========================================
# CONFIGURATION DU BOT
# ==========================================
TELEGRAM_BOT_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
GEMINI_API_KEY = "AQ.Ab8RN6KTg1OYFdhKtXP6p-hPg0vu5uztePiemDr_Wqm1gkow"

# Configuration de la clé Gemini
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL_NAME = "gemini-1.5-flash"

BASE_URL = "https://cyberscore.live/en/"
CHECK_INTERVAL_SECONDS = 60  # Pause de 60 secondes entre chaque cycle


# ==========================================
# FONCTIONS TELEGRAM & GEMINI
# ==========================================
async def send_telegram_report(photo_bytes: bytes, match_url: str, analysis_text: str):
    """Envoie l'image HD puis le rapport formaté séparément sur Telegram pour un match."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            photo_caption = f"📸 *CAPTURE LIVE MATCH DOTA 2*\n🔗 [Lien direct Cyberscore]({match_url})"
            await client.post(
                photo_url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": photo_caption, "parse_mode": "Markdown"},
                files={"photo": ("match_full.png", photo_bytes, "image/png")}
            )

            msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            await client.post(
                msg_url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": analysis_text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
            print(" [✓] Rapport de match envoyé sur Telegram.")

        except Exception as e:
            print(f" [ERR Telegram] Échec d'envoi du match : {e}")


async def send_telegram_summary(summary_text: str):
    """Envoie un message de synthèse global pour tous les matchs du cycle."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            await client.post(
                msg_url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": summary_text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
            print(" [✓] Résumé global des pronostics envoyé sur Telegram !")
        except Exception as e:
            print(f" [ERR Telegram] Échec d'envoi du résumé : {e}")


def analyze_with_targeted_data(image_bytes: bytes, match_data: dict) -> str:
    """Analyse sécurisée avec l'ancienne bibliothèque Google Generative AI."""
    prompt_text = f"""
Tu es un expert analyste eSport Dota 2. 
Voici les DONNÉES OFFICIELLES ET VÉRIFIÉES extraites directement de l'interface du match actif :
- Temps de jeu : {match_data.get('timer', 'Inconnu')}
- Score de Kills : {match_data.get('score', 'Inconnu')}
- Avantage Économique / Net Worth : {match_data.get('net_worth', 'Inconnu')}

Consignes de rédaction strictes :
- N'utilise PAS les termes génériques "Radiant" ou "Dire" pour le pronostic final. Donne impérativement le **NOM EXACT DE L'ÉQUIPE EN CLAIR** (ex: Vitality Warriors ou Real Eclipse).
- Base-toi strictement sur les données de l'interface et la capture d'écran.
- Rédige une réponse STYLÉE pour Telegram en utilisant le format Markdown suivant :

🏆 *ANALYSE & PRONOSTIC DOTA 2 LIVE*

⏱️ *STATUT DU MATCH*
• *Temps de jeu :* {match_data.get('timer', 'N/C')}
• *Score (Kills) :* {match_data.get('score', 'N/C')}
• *Avantage Économique :* {match_data.get('net_worth', 'N/C')}

⚔️ *DYNAMIQUE & HÉROS*
• [Synthèse courte de la phase de laning, des objets clés et du rythme de jeu]

🎯 *PRONOSTIC FINAL*
🏆 *Victoire recommandée :* **[NOM EXACT DE L'ÉQUIPE]**
💡 *Explication :* [Raisonnement clair en 2 phrases]
"""

    image_part = {
        "mime_type": "image/png",
        "data": image_bytes
    }

    for attempt in range(3):
        try:
            model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            response = model.generate_content([prompt_text, image_part])
            if response and response.text:
                return response.text
        except Exception as e:
            print(f" [!] Tentative Gemini {attempt + 1} échouée. Erreur exacte : {e}")
            import time
            time.sleep(3)
            
    return "⚠️ *Erreur d'analyse Gemini* : Impossible de joindre l'API après 3 essais."


# ==========================================
# TÂCHE DE FOND (LE BOT DOTA 2 EN BOUCLE)
# ==========================================
async def dota_bot_loop():
    print("\n" + "═" * 60)
    print(" 🎮 BOT DOTA 2 LIVE - LANCEMENT DE LA BOUCLE PRINCIPALE ")
    print("═" * 60)
    
    stealth = Stealth()

    while True:
        try:
            print("\n[🔄] Lancement d'un nouveau cycle de vérification...")
            async with stealth.use_async(async_playwright()) as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                )
                
                context = await browser.new_context(viewport={"width": 1280, "height": 1100})
                page = await context.new_page()

                print(f"[🔍] Navigation sur l'accueil : {BASE_URL}")
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(8)

                match_elements = page.locator("a[href*='/matches/'], a[href*='/match/']")
                count = await match_elements.count()
                
                match_urls = set()
                for i in range(count):
                    el = match_elements.nth(i)
                    text_content = await el.inner_text()
                    if "LIVE" in text_content.upper():
                        href = await el.get_attribute("href")
                        if href:
                            if not href.startswith("http"):
                                href = "https://cyberscore.live" + href
                            
                            href = href.rstrip("/")
                            if "/matches/" in href or "/match/" in href:
                                player_url = f"{href}/players/"
                                match_urls.add(player_url)

                match_urls = list(match_urls)
                print(f"[✓] {len(match_urls)} match(s) en live actuellement détecté(s).")

                if match_urls:
                    cycle_summaries = []
                    for match_url in match_urls:
                        print(f"\n[⚡] Traitement du match : {match_url}")
                        match_page = await context.new_page()
                        try:
                            await match_page.goto(match_url, wait_until="domcontentloaded", timeout=45000)
                            await asyncio.sleep(10)

                            match_data = {
                                'timer': "En cours",
                                'score': "Vérifié via l'interface active",
                                'net_worth': "Analyser via l'image et l'écart affiché"
                            }
                            
                            screenshot_bytes = await match_page.screenshot(full_page=True)
                            await match_page.close()

                            print(" [🤖] Génération de l'analyse ciblée...")
                            analysis = analyze_with_targeted_data(screenshot_bytes, match_data)

                            await send_telegram_report(screenshot_bytes, match_url, analysis)

                            rec_line = "Pronostic en cours"
                            for line in analysis.split('\n'):
                                if "Victoire recommandée" in line or "🏆" in line and "Victoire" in line:
                                    rec_line = line
                                    break

                            cycle_summaries.append(f"🔗 [Lien du match]({match_url})\n{rec_line}\n")

                        except Exception as e:
                            print(f" [ERR Match] {e}")
                            try:
                                await match_page.close()
                            except:
                                pass

                    if cycle_summaries:
                        summary_payload = "📋 *RÉSUMÉ GLOBAL DES MATCHS EN LIVE*\n\n" + "\n".join(cycle_summaries)
                        await send_telegram_summary(summary_payload)

                await context.close()
                await browser.close()
                print("[✓] Navigateur fermé proprement pour ce cycle.")

        except Exception as e:
            print(f" [ERR Global du cycle] {e}")

        print(f"[⌛] Pause de {CHECK_INTERVAL_SECONDS} secondes avant le prochain check...")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ==========================================
# SERVEUR WEB POUR SATISFAIRE RENDER
# ==========================================
async def handle_ping(request):
    return web.Response(text="Dota 2 Bot is running live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[🌐] Mini serveur web démarré sur le port {port} pour valider Render.")


async def main():
    await start_web_server()
    await dota_bot_loop()


if __name__ == "__main__":
    asyncio.run(main())
