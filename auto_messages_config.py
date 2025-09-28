# Список авто-сообщений
# file: имя скрипта в папке auto_messages
# interval: интервал в секундах
# min_chat_messages: минимальное количество сообщений в чате перед отправкой
import time

auto_messages = [
    {'file': 'discord_tg.py', 'interval': 30 * 60, 'min_chat_messages': 6},
    {'file': 'команды.py', 'interval': 25 * 60, 'min_chat_messages': 5},
    {'file': 'info.py', 'interval': 21 * 60, 'min_chat_messages': 5},
]


def load_auto_messages():
    messages = []
    for am in auto_messages:
        entry = am.copy()
        entry['last_sent'] = 0
        entry['counter'] = 0
        messages.append(entry)
    return messages