from score_utils import load_score, save_score
import os

CHANNEL = os.getenv("CHANNEL")

async def run(ctx):
    if ctx.author.name.lower() != CHANNEL.lower():
        return

    parts = ctx.message.content.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await ctx.send("Используй: !цель- <число>")
        return

    value = int(parts[1])
    data = load_score()
    current = data["score"]
    goal = data["goal"]

    new_value = max(current - value, 0)  # не уходим ниже нуля
    data["current"] = new_value
    save_score(data)

    await ctx.send(f"Счёт обновлён: {data['current']}/{goal}")