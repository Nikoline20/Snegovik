import os
import sys
import asyncio
import time
import importlib.util
import subprocess
import logging
from logging.handlers import TimedRotatingFileHandler
import requests
from twitchio.ext import commands
from dotenv import load_dotenv

# ==================== Логирование ====================
base_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
log_dir = os.path.join(base_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, "bot.log")

handler = TimedRotatingFileHandler(
    log_file, when="D", interval=1, backupCount=7, encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler]
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)

logging.info("Логирование инициализировано")

# ==================== Загрузка .env ====================
load_dotenv()
BOT_NICK = os.getenv("TWITCH_BOT_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")
TOKEN = os.getenv("TWITCH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

HELIX_STREAMS_URL = "https://api.twitch.tv/helix/streams"
APP_TOKEN = None
COMMANDS_DIR = "commands"
AUTOMSG_DIR = "auto_messages"

# ==================== Получение App Token ====================
def get_app_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, params=params)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    logging.info("Получен App Access Token")
    return token

# ==================== Импорт авто-сообщений ====================
from auto_messages_config import load_auto_messages  # функция возвращает список словарей

# ==================== Класс бота ====================
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(token=TOKEN, prefix="!", initial_channels=[CHANNEL])
        self.auto_messages = []
        self.chat_message_count = {}

    async def event_ready(self):
        logging.info(f"Бот {BOT_NICK} подключился к {CHANNEL}!")
        self.auto_messages = load_auto_messages()
        logging.info(f"Загружены авто-сообщения: {[am['file'] for am in self.auto_messages]}")
        self.load_custom_commands()
        asyncio.create_task(self.auto_message_loop())
        asyncio.create_task(self.check_stream_status())

    async def event_message(self, message):
        if message.echo:
            return
        for am in self.auto_messages:
            am['counter'] += 1
        await self.handle_commands(message)

    # ==================== Кастомные команды ====================
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
            logging.info(f"Загружены кастомные команды: {list(self.commands.keys())}")

    # ==================== Авто-сообщения ====================
    async def auto_message_loop(self):
        while True:
            now = time.time()
            for am in self.auto_messages:
                if now - am['last_sent'] >= am['interval'] and am['counter'] >= am['min_chat_messages']:
                    chan = self.get_channel(CHANNEL)
                    if chan:
                        spec = importlib.util.spec_from_file_location(
                            "module.name", os.path.join(AUTOMSG_DIR, am['file'])
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        await module.run(chan)
                        logging.info(f"Отправлено авто-сообщение {am['file']}")
                    am['last_sent'] = now
                    am['counter'] = 0
            await asyncio.sleep(5)

    # ==================== Команда обновления ====================
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
                    logging.info("Перезапуск бота после обновления")
                    os.execv(sys.executable, ["python"] + sys.argv)
            except Exception as e:
                await ctx.send(f"❌ Ошибка при обновлении: {e}")
                logging.error(f"Ошибка при обновлении: {e}")
        else:
            await ctx.send("⛔ Только модеры или стример могут обновлять бота!")

    # ==================== Проверка статуса стрима ====================
    async def check_stream_status(self):
        global APP_TOKEN
        while True:
            if not APP_TOKEN:
                try:
                    APP_TOKEN = get_app_access_token()
                except Exception as e:
                    logging.error(f"Ошибка получения App Token: {e}")
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
                    logging.info("Стрим запущен!")
                else:
                    logging.info("Стрим не идёт")
            except Exception as e:
                logging.error(f"Ошибка при проверке стрима: {e}")
            await asyncio.sleep(60)

# ==================== Запуск бота ====================
bot = Bot()

if __name__ == "__main__":
    bot.run()
