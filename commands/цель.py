import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from score_utils import load_score, save_score

async def run(ctx):
    data = load_score()
    await ctx.send(f"🎯 Цель выбить {data['goal']} ключей! Прогресс: {data['score']}/{data['goal']}")