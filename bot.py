# bot.py
import os
import time
import asyncio
import logging
import importlib.util
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from twitchio.ext import commands
import aiohttp
import inspect
import json

# ========== Настройки ==========
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL = os.getenv("CHANNEL")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

COMMANDS_DIR = "commands"
AUTOMSG_DIR = "auto_messages"
LOGS_DIR = "logs"
STATE_FILE = "auto_messages_state.json"

COMMAND_COOLDOWN = 5  # секунд

# ========== Логи ==========
os.makedirs(LOGS_DIR, exist_ok=True)
log_file = os.path.join(LOGS_DIR, "bot.log")
handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler, logging.StreamHandler()]
)

    # ---------- загрузка сохраения ----------
def load_auto_messages_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}
    
    # ---------- сохранение ----------
def save_auto_messages_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        logging.exception("Не удалось сохранить состояние авто-сообщений")

# ========== Helix helpers (aiohttp) ==========
async def get_app_access_token(session):
    """
    Получает App Access Token (client_credentials).
    Возвращает (token, expires_in) или (None, 0) при ошибке.
    """
    url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
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


async def helix_is_stream_live(session, app_token, channel_name):
    """
    Возвращает True/False или None при ошибке.
    """
    url = "https://api.twitch.tv/helix/streams"
    headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {app_token}"}
    params = {"user_login": channel_name}
    try:
        async with session.get(url, headers=headers, params=params) as resp:
            text = await resp.text()
            if resp.status == 401:
                logging.warning(f"Helix 401: токен недействителен или нет прав: {text}")
                return None
            if resp.status >= 400:
                logging.error(f"Helix запрос вернул HTTP {resp.status}: {text}")
                return None
            js = await resp.json()
            data = js.get("data", [])
            return len(data) > 0
    except Exception as e:
        logging.exception(f"Ошибка запроса Helix streams: {e}")
        return None


# ========== Бот ==========
class Bot(commands.Bot):
    def __init__(self):
        if not TOKEN or not CHANNEL:
            logging.error("TOKEN или CHANNEL не установлены в .env — бот не запустится.")
            raise SystemExit("TOKEN или CHANNEL отсутствуют")

        super().__init__(token=TOKEN, prefix="!", initial_channels=[CHANNEL])

        # команды
        self.custom_command_files = {}
        self._last_command_keys = set()

        # авто-сообщения (загрузится через конфиг)
        self.auto_messages = []

        # Twitch app token cache
        self.app_token = None
        self.app_token_expire_at = 0  # epoch

        # session создаём в event_ready (чтобы избежать RuntimeError)
        self.session = None

        # stream state
        self.stream_online = False
        self.last_stream_state = None

        # cooldowns
        self.cooldowns = {}  # username -> timestamp

        # main channel fallback (заполняется при первом сообщении)
        self.main_channel = None

        # ensure dirs, load commands/auto messages metadata
        os.makedirs(COMMANDS_DIR, exist_ok=True)
        os.makedirs(AUTOMSG_DIR, exist_ok=True)
        self.scan_command_files()

    # ---------- commands scanning ----------
    def scan_command_files(self):
        new = {}
        for fname in os.listdir(COMMANDS_DIR):
            if fname.endswith(".py"):
                name = fname[:-3]
                new[name] = os.path.join(COMMANDS_DIR, fname)
        new_keys = set(new.keys())
        if new_keys != self._last_command_keys:
            logging.info(f"Найдено кастомных команд: {sorted(list(new_keys))}")
            self._last_command_keys = new_keys
        self.custom_command_files = new

    # ---------- load auto messages ----------
    def load_auto_messages_config(self):
        try:
            import auto_messages_config as cfg
            load = getattr(cfg, "load_auto_messages", None)
            if callable(load):
                self.auto_messages = load()
            else:
                self.auto_messages = getattr(cfg, "AUTO_MESSAGES", [])
                for am in self.auto_messages:
                    am.setdefault("last_sent", 0)
                    am.setdefault("counter", 0)
            logging.info(f"Загружены авто-сообщения: {[a['file'] for a in self.auto_messages]}")
        except Exception as e:
            logging.warning(f"auto_messages_config не загружен: {e}")
            self.auto_messages = []

    # ---------- lifecycle ----------
    async def event_ready(self):
        logging.info(f"Bot ready: {self.nick} -> {CHANNEL}")

        # создаём session здесь — уже есть running loop
        if self.session is None or getattr(self.session, "closed", True):
            self.session = aiohttp.ClientSession()

        # загрузим авто-сообщения из конфига
        self.load_auto_messages_config()

        # периодические задачи
        asyncio.create_task(self._periodic_scan_commands())
        asyncio.create_task(self._auto_message_loop())
        asyncio.create_task(self._stream_status_loop())

        self.auto_messages_state = load_auto_messages_state()
        for am in self.auto_messages:
            fname = am["file"]
            if fname in self.auto_messages_state:
                st = self.auto_messages_state[fname]
                am["last_sent"] = st.get("last_sent", 0)
                am["counter"] = st.get("counter", 0)

    async def event_close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        logging.info("aiohttp.ClientSession закрыт")

    async def _periodic_scan_commands(self):
        while True:
            try:
                self.scan_command_files()
            except Exception as e:
                logging.exception(f"Ошибка сканирования команд: {e}")
            await asyncio.sleep(30)

    # ---------- messages ----------
    async def event_message(self, message):
        # не обрабатываем собственные сообщения
        if message.echo:
            return

        # запомним main_channel (фолбэк для авто-писем)
        if not self.main_channel:
            try:
                self.main_channel = message.channel
            except Exception:
                self.main_channel = None

        # обработка команды (начинается с "!")
        content = (message.content or "").strip()
        if not content.startswith("!"):
            # позволяем twitchio обрабатывать прочее
            await self.handle_commands(message)
            return

        # считаем сообщения для авто-сообщений (нужно для min_chat_messages)
        for am in self.auto_messages:
            am['counter'] = am.get('counter', 0) + 1

        username = message.author.name.lower()
        now = time.time()
        last = self.cooldowns.get(username, 0)
        if now - last < COMMAND_COOLDOWN:
            logging.info(f"Игнорируем команду от {username} — cooldown ({now-last:.2f}s)")
            return
        self.cooldowns[username] = now

        cmd_name = content.split()[0][1:]
        if cmd_name in self.custom_command_files:
            await self.run_custom_command(cmd_name, message)
            return

        # иначе даём handle_commands (если есть зарегистрированная команда)
        await self.handle_commands(message)

    # ---------- выполнение кастомной команды ----------
    async def run_custom_command(self, cmd_name, message):
        path = self.custom_command_files.get(cmd_name)
        if not path:
            logging.warning(f"Команда {cmd_name} не найдена (path пустой).")
            return
        if not os.path.exists(path):
            logging.warning(f"Файл команды {path} не найден.")
            return

        try:
            # Импортируем модуль динамически (чтобы сразу видеть изменения)
            spec = importlib.util.spec_from_file_location(f"commands.{cmd_name}_{int(time.time())}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logging.exception(f"Ошибка при загрузке команды {cmd_name}: {e}")
            try:
                await message.channel.send(f"Ошибка загрузки команды {cmd_name}")
            except Exception:
                pass
            return

        func = getattr(module, "run", None)
        if not func:
            logging.warning(f"В модуле {cmd_name} нет функции run")
            return

        # предпочитаем ctx (Context), но если команда написана иначе — пробуем message
        try:
            ctx = await self.get_context(message)
            if inspect.iscoroutinefunction(func):
                await func(ctx)
            else:
                res = func(ctx)
                if inspect.isawaitable(res):
                    await res
        except TypeError:
            logging.info(f"run(ctx) не подошёл для {cmd_name}, пробуем run(message)")
            try:
                if inspect.iscoroutinefunction(func):
                    await func(message)
                else:
                    res = func(message)
                    if inspect.isawaitable(res):
                        await res
            except Exception as e:
                logging.exception(f"Ошибка выполнения команды {cmd_name}: {e}")
                try:
                    await message.channel.send(f"Ошибка в команде {cmd_name}")
                except Exception:
                    pass
        except Exception as e:
            logging.exception(f"Ошибка выполнения команды {cmd_name}: {e}")
            try:
                await message.channel.send(f"Ошибка в команде {cmd_name}: {e}")
            except Exception:
                pass

    # ---------- авто-сообщения ----------
    def _get_send_channel(self):
        try:
            ch = self.get_channel(CHANNEL)
            if ch:
                return ch
        except Exception:
            pass
        try:
            if getattr(self, "connected_channels", None):
                if len(self.connected_channels) > 0:
                    return self.connected_channels[0]
        except Exception:
            pass
        return getattr(self, "main_channel", None)

    # ---------- цикл ----------
    async def _auto_message_loop(self):
        if not self.auto_messages:
            self.load_auto_messages_config()

        while True:
            if not self.stream_online:
                await asyncio.sleep(5)
                continue

            now = time.time()
            for am in self.auto_messages:
                try:
                    interval = am.get("interval", 600)
                    last_sent = am.get("last_sent", 0)
                    min_chat = am.get("min_chat_messages", 0)
                    counter = am.get("counter", 0)

                    if now - last_sent >= interval and counter >= min_chat:
                        chan = self._get_send_channel()
                        if chan:
                            p = os.path.join(AUTOMSG_DIR, am["file"])
                            if os.path.exists(p):
                                try:
                                    spec = importlib.util.spec_from_file_location(
                                        f"auto_msg_{os.path.splitext(am['file'])[0]}_{int(now)}",
                                        p
                                    )
                                    module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(module)

                                    runfn = getattr(module, "run", None)
                                    if runfn:
                                        sig = inspect.signature(runfn)
                                        params = len(sig.parameters)

                                        if params >= 2:
                                            res = runfn(chan, self)
                                        elif params == 1:
                                            res = runfn(chan)
                                        else:
                                            res = runfn()

                                        if inspect.isawaitable(res):
                                            await res

                                        logging.info(f"Отправлено авто-сообщение {am['file']}")
                                except Exception as e:
                                    logging.exception(f"Ошибка при исполнении авто-сообщения {am['file']}: {e}")
                            else:
                                logging.warning(f"Авто-файл не найден: {p}")

                        am["last_sent"] = now
                        am["counter"] = 0

                        # сохраняем состояние в JSON
                        self.auto_messages_state[am["file"]] = {
                            "last_sent": am["last_sent"],
                            "counter": am["counter"]
                        }
                        save_auto_messages_state(self.auto_messages_state)

                except Exception as e:
                    logging.exception(f"Ошибка в обработке авто-сообщения {am.get('file')}: {e}")

            await asyncio.sleep(5)

    # ---------- проверка статуса стрима ----------
    async def _ensure_app_token(self):
        # создаём session, если потребуется (в безопасном месте — уже в async)
        if self.session is None or getattr(self.session, "closed", True):
            self.session = aiohttp.ClientSession()

        if not CLIENT_ID or not CLIENT_SECRET:
            logging.warning("CLIENT_ID/CLIENT_SECRET не заданы — проверка стрима отключена.")
            return False

        now = time.time()
        if self.app_token and now < self.app_token_expire_at - 30:
            return True

        token, expires = await get_app_access_token(self.session)
        if token:
            self.app_token = token
            self.app_token_expire_at = now + max(10, int(expires))
            return True
        return False

    async def _stream_status_loop(self):
        while True:
            try:
                ok = await self._ensure_app_token()
                if not ok:
                    await asyncio.sleep(60)
                    continue

                live = await helix_is_stream_live(self.session, self.app_token, CHANNEL)
                if live is None:
                    # ошибка — освободим токен и повторим через короткий промежуток
                    self.app_token = None
                    await asyncio.sleep(15)
                    continue

                # смена статуса
                if live and not self.stream_online:
                    self.stream_online = True
                    logging.info("Стрим начался (детект).")
                    chan = self._get_send_channel()
                    if chan:
                        try:
                            await chan.send("Теперь я тоже смотрю стрим!")
                        except Exception:
                            pass

                elif not live and self.stream_online:
                    self.stream_online = False
                    logging.info("Стрим завершён (детект).")
                    chan = self._get_send_channel()
                    if chan:
                        try:
                            await chan.send("Стрим закончился, мне больше нечего смотреть...")
                        except Exception:
                            pass

                # сохраняем в last_stream_state
                self.last_stream_state = bool(live)

            except Exception as e:
                logging.exception(f"Ошибка в loop проверки стрима: {e}")

            await asyncio.sleep(30)


# ========== Запуск ==========
if __name__ == "__main__":
    bot = Bot()
    bot.run()
