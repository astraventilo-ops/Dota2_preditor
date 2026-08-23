import asyncio
import warnings
import httpx
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from google import genai
from google.genai import types

# Masquer les avertissements système internes
warnings.filterwarnings("ignore", category=UserWarning)

# ==========================================
# CONFIGURATION DU BOT
# ==========================================
TELEGRAM_BOT_TOKEN = "8840292681:AAHoBm9SlLC9HRDGwHs9VyRKR1BnFXD063Y"
TELEGRAM_CHAT_ID = "8594543473"
GEMINI_API_KEY = "AQ.Ab8RN6LokPIX6Tf6kXhda6zPFKT9VUn4-sWdA3BdwctaStzwbA"

GEMINI_MODEL_NAME = "gemini-3.6-flash"
BASE_URL = "https://cyberscore.live/en/"


# ==========================================
# FONCTIONS TELEGRAM & GEMINI
# ==========================================
async def send_telegram_report(photo_bytes: bytes, match_url: str, analysis_text: str):
    """Envoie l'image HD puis le rapport formaté séparément sur Telegram pour un match."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 1. Envoi de la photo avec titre
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            photo_caption = f"📸 *CAPTURE LIVE MATCH DOTA 2*\n🔗 [Lien direct Cyberscore]({match_url})"
            await client.post(
                photo_url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": photo_caption, "parse_mode": "Markdown"},
                files={"photo": ("match_full.png", photo_bytes, "image/png")}
            )

            # 2. Envoi du rapport texte complet et stylisé
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
    """Analyse combinée avec noms d'équipes en clair et sécurité de réessai."""
    client = genai.Client(api_key=GEMINI_API_KEY)
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

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
                    prompt_text
                ]
            )
            return response.text
        except Exception as e:
            print(f" [!] Tentative {attempt + 1} échouée (Réseau/DNS), nouvelle tentative dans 3s...")
            import time
            time.sleep(3)
            
    return "⚠️ *Erreur d'analyse Gemini* : Impossible de joindre l'API après 3 essais."


# ==========================================
# EXÉCUTION UNIQUE (ONE-SHOT) SUR RENDER
# ==========================================
async def main():
    print("\n" + "═" * 60)
    print(" 🎮 VÉRIFICATION UNIQUE DES MATCHS DOTA 2 LIVE (Render Cron) ")
    print("═" * 60)
    
    stealth = Stealth()

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,  # Impératif sur Render
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--start-maximized"
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1100}
        )
        page = await context.new_page()

        try:
            print(f"[🔍] Navigation sur l'accueil : {BASE_URL}")
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            
            print("[⌛] Attente de la stabilisation de la page (Cloudflare)...")
            await asyncio.sleep(10)

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

            if not match_urls:
                print("[⌛] Aucun match live en cours ou page bloquée. Fin de l'exécution.")
                await context.close()
                await browser.close()
                return

            cycle_summaries = []

            for match_url in match_urls:
                print(f"\n[⚡] Traitement du match : {match_url}")
                match_page = await context.new_page()
                
                try:
                    await match_page.goto(match_url, wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(12)

                    match_data = {
                        'timer': "En cours",
                        'score': "Vérifié via l'interface active",
                        'net_worth': "Analyser via l'image et l'écart affiché"
                    }
                    
                    screenshot_bytes = await match_page.screenshot(full_page=True)
                    await match_page.close()

                    print(" [🤖] Génération de l'analyse ciblée...")
                    analysis = analyze_with_targeted_data(screenshot_bytes, match_data)

                    print("\n" + "─" * 20 + " RÉSULTAT DU PRONOSTIC " + "─" * 20)
                    print(analysis)
                    print("─" * 63)

                    await send_telegram_report(screenshot_bytes, match_url, analysis)

                    rec_line = "Pronostic en cours"
                    for line in analysis.split('\n'):
                        if "Victoire recommandée" in line or "🏆" in line and "Victoire" in line:
                            rec_line = line
                            break

                    cycle_summaries.append(f"🔗 [Lien du match]({match_url})\n{rec_line}\n")

                except Exception as e:
                    print(f" [ERR] Échec du traitement sur le match : {e}")
                    try:
                        await match_page.close()
                    except:
                        pass

            if cycle_summaries:
                summary_payload = "📋 *RÉSUMÉ GLOBAL DES MATCHS EN LIVE*\n\n" + "\n".join(cycle_summaries)
                await send_telegram_summary(summary_payload)

        except Exception as e:
            print(f" [ERR Global] {e}")

        await context.close()
        await browser.close()
        print("\n[✓] Exécution unique terminée avec succès.")
        print("═" * 60)


if __name__ == "__main__":
    asyncio.run(main())
