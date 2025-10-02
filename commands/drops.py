import os
import aiohttp

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Название или ID игры для проверки
GAME_NAME = "STALCRAFT: X"

# --- получаем app access token ---
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
    session = ctx.bot.session

    token = await get_app_token(session)
    if not token:
        await ctx.send("Не удалось получить токен Twitch API.")
        return

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    # --- получаем game_id по названию игры ---
    async with session.get(
        "https://api.twitch.tv/helix/games",
        headers=headers,
        params={"name": GAME_NAME}
    ) as resp:
        if resp.status != 200:
            await ctx.send("Ошибка при получении ID игры.")
            return
        js = await resp.json()
        if not js.get("data"):
            await ctx.send("Игра не найдена.")
            return
        game_id = js["data"][0]["id"]

    # --- проверяем кампании дропсов ---
    async with session.get(
        "https://api.twitch.tv/helix/drops/campaigns",
        headers=headers,
        params={"game_id": game_id}
    ) as resp:
        js = await resp.json()
        campaigns = js.get("data", [])
        if not campaigns:
            await ctx.send(f"@{ctx.author.name} На {GAME_NAME} сейчас нет активных дропсов. Но можно подготовиться к ним, по ссылке вся информация: https://clck.ru/3N9YnH.")
            return

        await ctx.send(
            f"@{ctx.author.name} На канале присутствуют дропсы. Инструкция как их получить и как привязать по данной ссылке: https://clck.ru/3N9YnH. "
            f" Если присутствуют проблемы то пишите в тех. поддержку EXBO: https://support.exbo.net/ru. Для обращения в тех поддержку надо выбрать: Категория обращения: Учётная запись EXBO, Характер обращения: Привязка Twitch к EXBO и дальше пишите свою проблему."
        )