import json
import os

SCORE_FILE = "score.json"

def load_score():
    if not os.path.exists(SCORE_FILE):
        data = {"score": 0, "goal": 100}
        save_score(data)  # создаём файл при первом запуске
        return data
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_score(data):
    with open(SCORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)