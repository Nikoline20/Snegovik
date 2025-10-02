import aiohttp
import datetime
import os
import logging

CHANNEL = os.getenv("CHANNEL")
CLIENT_ID = os.getenv("CLIENT_ID")
USER_OAUTH = os.getenv("USER_OAUTH")  # токен со scope moderator:read:followers
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

async def run(ctx):
    bot = ctx.bot
    session = bot.session

    if not USER_OAUTH:
        await ctx.send("Нет токена USER_OAUTH в .env (нужен scope moderator:read:followers).")
        return

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {USER_OAUTH}"
    }

    user = ctx.author.name

    async def get_app_access_token(session):
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        try:
            async with session.post(url, data=data) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logging.error(f"Ошибка получения App Token: HTTP {resp.status} — {text}")
                    return None, 0
                js = await resp.json()
                token = js.get("access_token")
                expires = int(js.get("expires_in", 0))
                logging.info("Получен App Access Token")
                return token, expires
        except Exception as e:
            logging.exception(f"Исключение при запросе App Token: {e}")
            return None, 0

    # --- получаем user_id зрителя ---
    url_users = "https://api.twitch.tv/helix/users"
    async with session.get(url_users, headers=headers, params={"login": user}) as resp:
        js = await resp.json()
        if resp.status != 200:
            await ctx.send(f"Ошибка при получении данных пользователя: {js}")
            return
        if not js.get("data"):
            await ctx.send("Не нашёл пользователя.")
            return
        user_id = js["data"][0]["id"]

    # --- получаем broadcaster_id канала ---
    async with session.get(url_users, headers=headers, params={"login": CHANNEL}) as resp:
        js = await resp.json()
        if resp.status != 200:
            await ctx.send(f"Ошибка при получении данных канала: {js}")
            return
        if not js.get("data"):
            await ctx.send("Не нашёл канал.")
            return
        channel_id = js["data"][0]["id"]

    # --- проверяем фолловера ---
    url_follows = "https://api.twitch.tv/helix/channels/followers"
    params = {"broadcaster_id": channel_id, "user_id": user_id}

    async with session.get(url_follows, headers=headers, params=params) as resp:
        js = await resp.json()
        if resp.status != 200:
            await ctx.send(f"Ошибка при проверке фолловеров: {js}")
            return

        data = js.get("data", [])
        if not data:
            await ctx.send(f"@{user}, похоже ты ещё не зафолловлен! Поддержи стримера ❤️")
            return

        followed_at = data[0]["followed_at"]
        dt_follow = datetime.datetime.fromisoformat(followed_at.replace("Z", "+00:00"))
        delta = datetime.datetime.now(datetime.timezone.utc) - dt_follow

        days = delta.days
        months, days = divmod(days, 30)
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)

        msg_parts = []
        if months > 0:
            msg_parts.append(f"{months} мес.")
        if days > 0:
            msg_parts.append(f"{days} дн.")
        if hours > 0:
            msg_parts.append(f"{hours} ч.")
        if minutes > 0:
            msg_parts.append(f"{minutes} мин.")

        await ctx.send(f"@{user}, ты фолловишь канал уже {' '.join(msg_parts)}!")