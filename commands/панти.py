import random

async def run(ctx):
    items = [
        {"t": " воздух", "c": 38},
        {"t": " трусики di_ke_in", "c": 30},
        {"t": " трусики Сыра", "c": 15},
        {"t": " трусики nevord", "c": 13},
        {"t": " трусики nikoline_da", "c": 10},
        {"t": " трусики tuxuy15", "c": 6},
        {"t": " трусики snegurka666", "c": 0.3},
        {"t": " трусики молодого человека стримерши", "c": 0.07},
    ]

    total_weight = sum(x["c"] for x in items)
    r = random.uniform(0, total_weight)

    cumulative = 0
    chosen = None
    for x in items:
        cumulative += x["c"]
        if r <= cumulative:
            chosen = x["t"]
            break

    parts = ctx.message.content.split(maxsplit=1)
    target = parts[1] if len(parts) > 1 else ctx.author.name
    response = f"@{target} получил{chosen}"
    await ctx.send(response)