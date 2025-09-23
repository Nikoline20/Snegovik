import os
import sys
import subprocess
import asyncio
import requests
import importlib.util
from twitchio.ext import commands, routines
from dotenv import load_dotenv

# Загружаем конфиг
load_dotenv()

BOT_NICK = os.getenv("TWITCH_BOT_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")
TOKEN = os.getenv("TWITCH_TOKEN")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

HELIX_STREAMS_URL = "https://api.twitch.tv/helix/streams"

APP_TOKEN = None
COMMANDS_DIR = "commands"
AUTOMSG_DIR = "auto_messages"

# === Получаем App Token для API ===
def get_app_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, params=params)
    resp.raise_for_status()
    return resp.json()["access_token"]


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(token=TOKEN, prefix="!", initial_channels=[CHANNEL])

    async def event_ready(self):
        print(f"✅ Бот {BOT_NICK} подключился к {CHANNEL}!")
        self.load_custom_commands()

    async def event_message(self, message):
        if message.echo:
            return
        await self.handle_commands(message)

    # ==== Встроенные команды ====
    @commands.command(name="обновить")
    async def update_restart(self, ctx: commands.Context):
        if ctx.author.is_mod or ctx.author.name.lower() == CHANNEL.lower():
            await ctx.send("🔄 Проверяю обновления...")
            try:
                out = subprocess.check_output(["git", "pull"]).decode("utf-8")
                if "Already up to date" in out or "Уже обновлено" in out:
                    await ctx.send("✅ Обновлений нет, бот уже свежий.")
                else:
                    await ctx.send("♻️ Найдены обновления, перезапуск...")
                    os.execv(sys.executable, ["python"] + sys.argv)
            except Exception as e:
                await ctx.send(f"❌ Ошибка при обновлении: {e}")
        else:
            await ctx.send("⛔ Только модеры или стример могут обновлять бота!")

    # ==== Загрузка кастомных команд ====
    def load_custom_commands(self):
        if os.path.exists(COMMANDS_DIR):
            for fname in os.listdir(COMMANDS_DIR):
                if fname.endswith(".py"):
                    cmd_name = fname.replace(".py", "")

                    async def custom_cmd(ctx, file=fname):
                        spec = importlib.util.spec_from_file_location(
                            "module.name", os.path.join(COMMANDS_DIR, file)
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        await module.run(ctx)

                    if cmd_name not in self.commands:
                        self.add_command(commands.Command(name=cmd_name, func=custom_cmd))
            print(f"📦 Загружены кастомные команды: {list(self.commands.keys())}")


bot = Bot()

# ==== Автоматические сообщения ====
auto_messages_list = []
if os.path.exists(AUTOMSG_DIR):
    for fname in os.listdir(AUTOMSG_DIR):
        if fname.endswith(".py"):
            auto_messages_list.append(fname)


@routines.routine(minutes=10)
async def auto_message():
    if auto_messages_list:
        chan = bot.get_channel(CHANNEL)
        if chan:
            fname = auto_messages_list.pop(0)
            spec = importlib.util.spec_from_file_location(
                "module.name", os.path.join(AUTOMSG_DIR, fname)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            await module.run(chan)
            auto_messages_list.append(fname)


# ==== Проверка статуса стрима ====
async def check_stream_status():
    global APP_TOKEN
    while True:
        if not APP_TOKEN:
            try:
                APP_TOKEN = get_app_access_token()
            except Exception as e:
                print("Ошибка получения App Token:", e)
                await asyncio.sleep(60)
                continue

        headers = {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {APP_TOKEN}"
        }
        params = {"user_login": CHANNEL}
        try:
            resp = requests.get(HELIX_STREAMS_URL, headers=headers, params=params)
            data = resp.json()
            if "data" in data and len(data["data"]) > 0:
                print("🔴 Стрим запущен!")
                if not auto_message.is_running():
                    auto_message.start()
            else:
                print("⚫ Стрим не идёт")
                if auto_message.is_running():
                    auto_message.stop()
        except Exception as e:
            print("Ошибка при проверке стрима:", e)

        await asyncio.sleep(60)


# ==== Основной запуск ====
async def main():
    asyncio.create_task(check_stream_status())
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())