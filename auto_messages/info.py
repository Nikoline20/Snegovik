import os
import datetime
import aiohttp

CHANNEL = os.getenv("CHANNEL")
CLIENT_ID = os.getenv("CLIENT_ID")
# GAME_WHITELIST — название(я) игр, при которых сообщение должно отправляться
GAME_WHITELIST = {"STALCRAFT: X"}

async def run(chan, bot):
    if getattr(bot, "session", None) is None or getattr(bot.session, "closed", True):
        bot.session = aiohttp.ClientSession()

    ok = await bot._ensure_app_token()
    if not ok:
        # не получилось получить app token — просто не отправляем сообщение
        return

    session = bot.session
    app_token = bot.app_token

    headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {app_token}"}

    # получаем broadcaster_id
    url_users = "https://api.twitch.tv/helix/users"
    async with session.get(url_users, headers=headers, params={"login": CHANNEL}) as resp:
        if resp.status != 200:
            return
        js = await resp.json()
        data = js.get("data", [])
        if not data:
            return
        broadcaster_id = data[0]["id"]

    # получаем инфо канала (в т.ч. game_name)
    url_channels = "https://api.twitch.tv/helix/channels"
    async with session.get(url_channels, headers=headers, params={"broadcaster_id": broadcaster_id}) as resp:
        if resp.status != 200:
            return
        js = await resp.json()
        data = js.get("data", [])
        if not data:
            return
        current_game = data[0].get("game_name", "")

    # если стример играет не в нужную игру — молчим
    if current_game not in GAME_WHITELIST:
        return

    # иначе отправляем сообщение
    try:
        await chan.send(
            "Стример играет только с виперами и друзьями(в опене). "
            "В друзьях нет места и в ближайшее время не планируется освобождаться. "
            "(Интим не предлагать даже) У стримера нет вебки и не будет в ближайшее время."
        )
    except Exception:
        # безопасно игнорируем ошибки отправки
        pass