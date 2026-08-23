# Utilise l'image officielle Playwright pour Python
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Définit le répertoire de travail
WORKDIR /app

# Copie et installe les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le code source de ton bot
COPY . .

# Commande exécutée pour lancer ton main.py
CMD ["python", "main.py"]
