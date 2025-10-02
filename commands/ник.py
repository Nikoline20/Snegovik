import os
import aiohttp

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CHANNEL = os.getenv("CHANNEL")  # канал из .env

# --- список игр и текстов ---
GAME_RESPONSES = {
    "STALCRAFT: X": "Ник: ХКлиХ  Группировка: Рубеж",
    "League of Legends": "Ник: Snegurka666",
    "Genshin Impact": "UID: 747598589",
    "Honkai: Star Rail": "UID: 714798751",
    "Wuthering Waves": "UID: 600762760"
}


# --- получаем app token ---
async def get_app_token(session):
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    async with session.post(url, params=params) as resp:
        js = await resp.json()
        return js.get("access_token")


async def run(ctx):
    bot = ctx.bot
    session = bot.session

    token = await get_app_token(session)
    if not token:
        await ctx.send("Ошибка авторизации Twitch API.")
        return

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    # --- получаем id канала ---
    async with session.get(
        "https://api.twitch.tv/helix/users",
        headers=headers,
        params={"login": CHANNEL}
    ) as resp:
        js = await resp.json()
        if not js.get("data"):
            await ctx.send("Ошибка: не удалось найти канал.")
            return
        broadcaster_id = js["data"][0]["id"]

    # --- получаем текущую игру ---
    async with session.get(
        "https://api.twitch.tv/helix/channels",
        headers=headers,
        params={"broadcaster_id": broadcaster_id}
    ) as resp:
        js = await resp.json()
        if not js.get("data"):
            await ctx.send("Ошибка: не удалось получить данные о канале.")
            return
        current_game = js["data"][0]["game_name"]

    # --- проверка ---
    if current_game in GAME_RESPONSES:
        await ctx.send(GAME_RESPONSES[current_game])
    else:
        await ctx.send("Подходящего ника для этой игры нет 😢")