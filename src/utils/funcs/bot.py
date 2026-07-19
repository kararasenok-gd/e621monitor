import aiogram


def get_args(message: aiogram.types.Message):
    txt = message.caption or message.text
    words = txt.split(" ")

    if words[0].startswith("/"):
        words = words[1:]

    if len(words) == 0:
        return None

    return " ".join(words).strip()

async def get_url_with_start_params(bot: aiogram.Bot, params: str):
    return f"https://t.me/{(await bot.get_me()).username}?start={params}"