import random
import os

# Кого нельзя кусать (нижний регистр)
BLOCKED_USERS = {
    os.getenv("TWITCH_BOT_NICK", "").lower(),
}
# Удаляем пустые строки
BLOCKED_USERS = {x for x in BLOCKED_USERS if x}

BITE_MESSAGES = [
    "{user} чик — {target} укусил за ухо!",
    "{user} громко куснул {target} за палец!",
    "{user} тихо подкрался и кусьнул {target} за плечо!",
    "{user} укусил {target} за ногу!",
    "{user} укусил {target} за его деньги!",
    "{user} укусил {target} за его обереги! Поздравляю у вас -10к оберегов.",
    "{user} сделал большой кусь {target} — ого!"
]

def _get_name_from_chatter(ch):
    if ch is None:
        return None
    if isinstance(ch, str):
        return ch
    
    for attr in ("name", "display_name", "login", "user", "nick"):
        v = getattr(ch, attr, None)
        if isinstance(v, str) and v:
            return v
    # fallback
    try:
        return str(ch)
    except Exception:
        return None

async def run(ctx):
    author = ctx.author.name
    author_lc = author.lower()

    # Парсим аргумент (цель)
    parts = (ctx.message.content or "").split()
    target = None
    if len(parts) > 1:
        target = parts[1].lstrip("@").strip()
    else:
        # Попытка собрать список зрителей из разных мест
        candidates = []

        try:
            chatters = getattr(ctx.channel, "chatters", None)
            if chatters:
                candidates = [_get_name_from_chatter(c) for c in chatters]
        except Exception:
            candidates = []

        if not candidates:
            try:
                chs = getattr(ctx.bot, "connected_channels", None)
                if chs:
                    ch0 = chs[0]
                    chatters = getattr(ch0, "chatters", None)
                    if chatters:
                        candidates = [_get_name_from_chatter(c) for c in chatters]
            except Exception:
                pass

        # очищаем кандидатов и убираем None, пустые и автора
        candidates = [c for c in (candidates or []) if c and c.strip()]
        candidates = [c for c in candidates if c.lower() != author_lc]

        if not candidates:
            await ctx.send(f"@{author}, сейчас некому делать кусь — никого в чате не нашёл.")
            return

        # выбираем случайного
        target = random.choice(candidates)

    if not target:
        await ctx.send(f"@{author}, не получилось определить цель для кусь.")
        return

    target_str = str(target).strip()
    target_lc = target_str.lower()

    # Нельзя кусать из BLOCKED_USERS
    if target_lc in BLOCKED_USERS:
        blocked_list = ", ".join(sorted(x for x in BLOCKED_USERS if x))
        msg = f"@{author}, нельзя кусать {target_str}. Список запрещённых: {blocked_list}" if blocked_list else f"@{author}, нельзя кусать {target_str}."
        await ctx.send(msg)
        return

    # Нельзя кусать самого себя
    if target_lc == author_lc:
        await ctx.send(f"@{author}, ты не можешь кусать самого себя 😉")
        return

    # Случайное сообщение
    template = random.choice(BITE_MESSAGES)
    out = template.format(user=author, target=target_str)
    await ctx.send(out)