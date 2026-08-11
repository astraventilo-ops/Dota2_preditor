import os
import warnings
import numpy as np
from flask import Flask, request, jsonify

warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)

MODEL_PATH = "xgb_dota_model.pkl"
COUNTER_MATRIX_PATH = "counter_matrix.json"

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

@app.route("/")
def home():
    return "Bot Dota 2 actif sur Render !"

@app.route("/predict", methods=["POST"])
def predict():
    if model is None:
        return jsonify({"error": "Modèle non chargé sur le serveur"}), 500

    try:
        data = request.get_json(force=True) or {}

        # 1. Extraction des valeurs
        gold_diff = float(data.get("gold_diff", 0))
        minute = max(int(data.get("minute", 15)), 1)
        xp_diff = float(data.get("xp_diff", gold_diff * 0.85))
        gold_momentum = float(data.get("gold_momentum", gold_diff * 0.2))
        gold_per_min = float(data.get("gold_per_min", 500 + (gold_diff / minute)))
        
        r_heroes = data.get("radiant_heroes", [])
        d_heroes = data.get("dire_heroes", [])
        draft_adv = get_draft_advantage(r_heroes, d_heroes)
        
        gold_xp_ratio = gold_diff / (abs(xp_diff) + 1.0)
        networth_accel = gold_momentum / (minute + 1.0)

        # 2. Construction d'un tableau NumPy 2D dans l'ordre exact de l'entraînement
        features_array = np.array([[
            gold_diff,
            xp_diff,
            gold_momentum,
            gold_per_min,
            draft_adv,
            gold_xp_ratio,
            networth_accel
        ]], dtype=np.float32)

        # 3. Prédiction de la probabilité
        proba = model.predict_proba(features_array)[0]
        
        # Sur XGBoost, proba[1] est généralement la classe 1 (Victoire Radiant)
        prob_radiant = float(proba[1] * 100.0)

        return jsonify({
            "status": "success",
            "radiant_win": round(prob_radiant, 1),
            "dire_win": round(100.0 - prob_radiant, 1),
            "draft_advantage": round(draft_adv * 100.0, 1)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
