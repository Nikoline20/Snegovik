import aiohttp
import datetime
import os

CHANNEL = os.getenv("CHANNEL")  # чтобы взять имя из .env

async def run(ctx):
    bot = ctx.bot  # доступ к боту
    session = bot.session
    app_token = bot.app_token
    client_id = os.getenv("CLIENT_ID")

    if not app_token:
        await ctx.send("Не могу проверить фолловеров: токен ещё не получен.")
        return

    user = ctx.author.name

    # сначала получаем user_id по имени
    url_users = "https://api.twitch.tv/helix/users"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {app_token}"
    }

    async with session.get(url_users, headers=headers, params={"login": user}) as resp:
        if resp.status != 200:
            await ctx.send("Ошибка при получении данных пользователя.")
            return
        js = await resp.json()
        if not js.get("data"):
            await ctx.send("Не нашёл пользователя в Twitch API.")
            return
        user_id = js["data"][0]["id"]

    # получаем id канала (чтобы проверить follow)
    async with session.get(url_users, headers=headers, params={"login": CHANNEL}) as resp:
        if resp.status != 200:
            await ctx.send("Ошибка при получении данных канала.")
            return
        js = await resp.json()
        if not js.get("data"):
            await ctx.send("Не нашёл канал в Twitch API.")
            return
        channel_id = js["data"][0]["id"]

    # проверяем фоллов
    url_follows = "https://api.twitch.tv/helix/users/follows"
    params = {"from_id": user_id, "to_id": channel_id}

    async with session.get(url_follows, headers=headers, params=params) as resp:
        if resp.status != 200:
            await ctx.send("Ошибка при проверке фолловеров.")
            return
        js = await resp.json()
        data = js.get("data", [])
        if not data:
            await ctx.send(f"@{user}, похоже ты ещё не зафолловлен на канал! Поддержи стримера ❤️")
            return

        followed_at = data[0]["followed_at"]
        dt_follow = datetime.datetime.fromisoformat(followed_at.replace("Z", "+00:00"))
        delta = datetime.datetime.now(datetime.timezone.utc) - dt_follow

        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)

        await ctx.send(f"@{user}, ты фолловишь канал уже {days} дн. {hours} ч. {minutes} мин!")