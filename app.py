import os
import re
import time
import pickle
import threading
import warnings
import requests
import cloudscraper
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore", category=UserWarning)

# --- SERVEUR FLASK ---
app = Flask(__name__)

# --- CONFIGURATION ---
MODEL_PATH = "xgb_dota_model.pkl"  # Ou dota_xgb.pkl selon ton nom de fichier
COUNTER_MATRIX_PATH = "counter_matrix.json"

# Chargement du modèle XGBoost et de la matrice
model = None
counter_matrix = {}

if os.path.exists(MODEL_PATH):
    try:
        import joblib
        model = joblib.load(MODEL_PATH)
        print("✅ Modèle XGBoost chargé avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors du chargement du modèle : {e}")

if os.path.exists(COUNTER_MATRIX_PATH):
    try:
        import json
        with open(COUNTER_MATRIX_PATH, "r") as f:
            counter_matrix = json.load(f)
        print("✅ Matrice de draft chargée avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors du chargement de la matrice : {e}")

def get_draft_advantage(radiant_heroes, dire_heroes):
    if len(radiant_heroes) < 5 or len(dire_heroes) < 5:
        return 0.5
    scores = []
    for r in radiant_heroes:
        for d in dire_heroes:
            key = f"{r}_{d}"
            if key in counter_matrix:
                scores.append(counter_matrix[key])
    return float(np.mean(scores)) if scores else 0.5

# --- ROUTES FLASK ---

@app.route("/")
def home():
    return "Bot Dota 2 actif sur Render !"

@app.route("/predict", methods=["POST"])
def predict():
    if model is None:
        return jsonify({"error": "Modèle non chargé sur le serveur"}), 500

    data = request.get_json(force=True)

    # Nettoyage et sécurisation des entrées
    gold_diff = float(data.get("gold_diff", 0))
    xp_diff = float(data.get("xp_diff", gold_diff * 0.85))
    minute = int(data.get("minute", 15))
    gold_momentum = float(data.get("gold_momentum", gold_diff * 0.2))
    gold_per_min = float(data.get("gold_per_min", 500 + (gold_diff / max(minute, 1))))
    
    r_heroes = data.get("radiant_heroes", [])
    d_heroes = data.get("dire_heroes", [])
    
    draft_adv = get_draft_advantage(r_heroes, d_heroes)
    gold_xp_ratio = gold_diff / (abs(xp_diff) + 1)
    networth_accel = gold_momentum / (minute + 1)

    features = pd.DataFrame([{
        'gold_diff': gold_diff,
        'xp_diff': xp_diff,
        'gold_momentum': gold_momentum,
        'gold_per_min': gold_per_min,
        'draft_advantage': draft_adv,
        'gold_xp_ratio': gold_xp_ratio,
        'networth_accel': networth_accel
    }])

    prob_radiant = float(model.predict_proba(features)[0][1] * 100)
    
    return jsonify({
        "status": "success",
        "radiant_win": round(prob_radiant, 1),
        "dire_win": round(100 - prob_radiant, 1),
        "draft_advantage": round(draft_adv * 100, 1)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
