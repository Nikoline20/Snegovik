import random

async def run(ctx):
    num = random.randint(-20, 100)

    parts = ctx.message.content.split(maxsplit=1)
    target = parts[1] if len(parts) > 1 else ctx.author.name
    target = f"@{target}"

    if num >= 80:
        response = f"Вот это да, да у {target} хуй {num} см. Мамма мия, как ты с таким ходишь?"
    elif num <= 0:
        response = f"Эммм, у {target} хуй {num} см. Он вообще есть у тебя? Или что это?"
    else:
        response = f"Вот это да, да у {target} хуй {num} см."

    await ctx.send(response)