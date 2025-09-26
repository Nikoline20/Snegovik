import os
import time
import asyncio
import logging
import importlib.util
import inspect
import twitchAPI
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from twitchio.ext import commands
from twitchAPI.twitch import Twitch

# ========== Настройки ==========
load_dotenv()
TOKEN = os.getenv("TWITCH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CHANNEL = os.getenv("TWITCH_CHANNEL")

COMMANDS_DIR = "commands"
AUTOMSG_DIR = "automsg"
LOGS_DIR = "logs"

# ========== Логи ==========
os.makedirs(LOGS_DIR, exist_ok=True)
log_file = os.path.join(LOGS_DIR, "bot.log")
handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler, logging.StreamHandler()]
)

# ========== Бот ==========
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(token=TOKEN, prefix="!", initial_channels=[CHANNEL])
        self.custom_command_files = {}
        self.auto_messages = []
        self.ensure_dirs()
        self.scan_command_files()
        self.load_auto_messages_config()

        # API Twitch
        self.twitch = Twitch(CLIENT_ID, CLIENT_SECRET)
        self.stream_online = False

        # Ограничение команд
        self.cooldowns = {}

    def ensure_dirs(self):
        os.makedirs(COMMANDS_DIR, exist_ok=True)
        os.makedirs(AUTOMSG_DIR, exist_ok=True)

    # Сканируем папку commands/
    def scan_command_files(self):
        new_command_files = {}
        for fname in os.listdir(COMMANDS_DIR):
            if fname.endswith(".py"):
                name = fname[:-3]
                path = os.path.join(COMMANDS_DIR, fname)
                new_command_files[name] = path

        # Логируем только если список изменился
        if set(new_command_files.keys()) != set(self.custom_command_files.keys()):
            logging.info(f"Найдено кастомных команд: {list(new_command_files.keys())}")

        self.custom_command_files = new_command_files

    # Загружаем авто-сообщения
    def load_auto_messages_config(self):
        try:
            import auto_messages_config as cfg
            self.auto_messages = []
            for am in getattr(cfg, "AUTO_MESSAGES", []):
                entry = am.copy()
                entry.setdefault("last_sent", 0)
                entry.setdefault("counter", 0)
                self.auto_messages.append(entry)
            logging.info(f"Загружены авто-сообщения: {[a['file'] for a in self.auto_messages]}")
        except Exception as e:
            logging.warning(f"auto_messages_config.py не загружен: {e}")
            self.auto_messages = []

    # ================= События =================
    async def event_ready(self):
        logging.info(f"Бот готов: {self.nick} -> канал: {CHANNEL}")
        asyncio.create_task(self.periodic_scan_commands())
        asyncio.create_task(self.auto_message_loop())
        asyncio.create_task(self.stream_status_checker())

    async def periodic_scan_commands(self):
        while True:
            try:
                self.scan_command_files()
            except Exception as e:
                logging.error(f"Ошибка при сканировании команд: {e}")
            await asyncio.sleep(10)

    async def event_message(self, message):
        if message.echo or not self.stream_online:
            return

        # Ограничение команд
        user = message.author.name
        now = time.time()
        if user in self.cooldowns and now - self.cooldowns[user] < 2:
            return
        self.cooldowns[user] = now

        # Считаем сообщения для авто-сообщений
        for am in self.auto_messages:
            am['counter'] += 1

        # Кастомные команды
        if message.content.startswith("!"):
            cmd_name = message.content.split()[0][1:]
            if cmd_name in self.custom_command_files:
                await self.run_custom_command(cmd_name, message)
                return

        await self.handle_commands(message)

    # ========== Выполнение кастомной команды ==========
    async def run_custom_command(self, cmd_name, message):
        path = self.custom_command_files.get(cmd_name)
        if not path or not os.path.exists(path):
            logging.warning(f"Команда {cmd_name} не найдена: {path}")
            return

        try:
            spec = importlib.util.spec_from_file_location(f"commands.{cmd_name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logging.error(f"Ошибка загрузки команды {cmd_name}: {e}")
            await message.channel.send(f"Ошибка загрузки команды {cmd_name}")
            return

        if not hasattr(module, "run"):
            logging.error(f"В модуле {cmd_name} нет функции run")
            await message.channel.send(f"Команда {cmd_name} некорректна (нет run)")
            return

        func = module.run
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        nparams = len(params)

        ctx = None
        if nparams >= 1:
            if params[0].name.lower() in ("ctx", "context"):
                ctx = await self.get_context(message)

        try:
            if asyncio.iscoroutinefunction(func):
                if nparams == 2:
                    if ctx:
                        await func(self, ctx)
                    else:
                        await func(self, message)
                elif nparams == 1:
                    if ctx:
                        await func(ctx)
                    else:
                        await func(message)
                else:
                    await func()
            else:
                if nparams == 2:
                    if ctx:
                        res = func(self, ctx)
                    else:
                        res = func(self, message)
                elif nparams == 1:
                    if ctx:
                        res = func(ctx)
                    else:
                        res = func(message)
                else:
                    res = func()
                if inspect.isawaitable(res):
                    await res
        except Exception as e:
            logging.exception(f"Ошибка в выполнении команды {cmd_name}: {e}")
            try:
                await message.channel.send(f"Ошибка в команде {cmd_name}: {e}")
            except Exception:
                pass

    # ================= Авто-сообщения =================
    async def auto_message_loop(self):
        while True:
            if self.stream_online:
                now = time.time()
                for am in self.auto_messages:
                    try:
                        interval = am.get("interval", 600)
                        last = am.get("last_sent", 0)
                        counter = am.get("counter", 0)
                        min_chat = am.get("min_chat_messages", 0)

                        if now - last >= interval and counter >= min_chat:
                            chan = self.get_channel(CHANNEL)
                            if chan:
                                path = os.path.join(AUTOMSG_DIR, am['file'])
                                if os.path.exists(path):
                                    try:
                                        spec = importlib.util.spec_from_file_location(f"automsg.{am['file']}", path)
                                        module = importlib.util.module_from_spec(spec)
                                        spec.loader.exec_module(module)
                                        if hasattr(module, "run"):
                                            if asyncio.iscoroutinefunction(module.run):
                                                await module.run(chan)
                                            else:
                                                res = module.run(chan)
                                                if inspect.isawaitable(res):
                                                    await res
                                            logging.info(f"Отправлено авто-сообщение {am['file']}")
                                        else:
                                            logging.warning(f"Авто-файл {am['file']} не содержит run(chan)")
                                    except Exception as e:
                                        logging.exception(f"Ошибка авто-сообщения {am['file']}: {e}")
                                else:
                                    logging.warning(f"Файл авто-сообщения {am['file']} не найден: {path}")

                            am['last_sent'] = now
                            am['counter'] = 0
                    except Exception as e:
                        logging.exception(f"Ошибка в авто-сообщении: {e}")
            await asyncio.sleep(5)

    # ================= Проверка статуса стрима =================
    async def stream_status_checker(self):
        chan = self.get_channel(CHANNEL)
        while True:
            try:
                user_info = await self.twitch.get_users(logins=[CHANNEL])
                if not user_info["data"]:
                    await asyncio.sleep(60)
                    continue

                user_id = user_info["data"][0]["id"]
                stream = await self.twitch.get_streams(user_id=user_id)

                if stream["data"] and not self.stream_online:
                    # Стрим начался
                    self.stream_online = True
                    logging.info("Стрим начался")
                    if chan:
                        await chan.send("Теперь я тоже смотрю стрим 👀")

                elif not stream["data"] and self.stream_online:
                    # Стрим закончился
                    self.stream_online = False
                    logging.info("Стрим завершился")
                    if chan:
                        await chan.send("Теперь мне нечего смотреть 😔")

            except Exception as e:
                logging.error(f"Ошибка при проверке статуса стрима: {e}")

            await asyncio.sleep(60)


# ========== Запуск ==========
if __name__ == "__main__":
    bot = Bot()
    bot.run()
