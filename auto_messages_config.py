# Список авто-сообщений
# file: имя скрипта в папке auto_messages
# interval: интервал в секундах
# min_chat_messages: минимальное количество сообщений в чате перед отправкой
import time

AUTO_MESSAGES = [
    {'file': 'discord_tg.py', 'interval': 15 * 60, 'min_chat_messages': 5},
    {'file': 'команды.py', 'interval': 10 * 60, 'min_chat_messages': 3},
    {'file': 'info.py', 'interval': 10 * 60, 'min_chat_messages': 3},
]


def load_auto_messages():
    messages = []
    for am in AUTO_MESSAGES:
        entry = am.copy()
        entry['last_sent'] = 0
        entry['counter'] = 0
        messages.append(entry)
    return messages