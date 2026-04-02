
import asyncio
import csv
import io
import logging
import re
from datetime import datetime
from pathlib import Path

import aiofiles
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

current_user: dict[int, bool] = {}
user_dates: dict[int, str] = {}
OUT_DIR = Path("homework_files")
OUT_DIR.mkdir(exist_ok=True)


def parse_date(text: str) -> str | None:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%d.%m.%Y")
        except Exception:
            continue
    return None


def safe_filename(date_str: str) -> str:
    safe = re.sub(r"[^0-9.]", "_", date_str)
    return f"homework_{safe}.csv"

@dp.message(CommandStart())
async def start(message: Message):
    await message.reply("Привет👋, введи /help.")

@dp.message(Command(commands=["help"]))
async def help(message: Message):
    await message.reply("Привет, я бот для сохранения дз.\n"
                        "Вот, что я могу:\n"
                        "/set_date: это команда для установки даты, используй ее для сохранения дз и  для его вывода (/set_date xx.xx.xxxx) \n"
                        "/hw_today: это команда сохранения дз, перед тем как использовать ее введи /set_date(P.s в чате /hw_today не работает только через лс)\n"
                        "/print_hw: это команда для вывода сохраненного дз, перед тем как ее использовать введи /set_date для установки даты.")

@dp.message(Command(commands=["set_date"]))
async def set_date(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Использование: /set_date DD.MM.YYYY или /set_date YYYY-MM-DD")
        return
    parsed = parse_date(parts[1].strip())
    if not parsed:
        await message.answer("Не удалось распознать дату. Формат: DD.MM.YYYY или YYYY-MM-DD")
        return
    user_dates[message.from_user.id] = parsed
    await message.answer(f"Дата установлена: {parsed}. Теперь отправьте домашку командой /hw_today.")


@dp.message(Command(commands=["hw_today"]))
async def hw_today(message: Message):
    user_id = message.from_user.id
    if user_id not in user_dates:
        await message.answer("Сначала установите дату с помощью /set_date.")
        return
    current_user[user_id] = True
    await message.answer("Введите домашку за выбранную дату:")


# основной обработчик — игнорируем команды с помощью лямбда-фильтра
@dp.message(lambda m: (m.text is not None) and (not m.text.startswith("/")))
async def process_hw(message: Message):
    user_id = message.from_user.id
    if not current_user.get(user_id):
        return
    hw_text = (message.text or "").strip()
    date = user_dates.get(user_id)
    if not date:
        await message.answer("Ошибка: дата не найдена. Установите дату заново.")
        current_user.pop(user_id, None)
        return

    path = OUT_DIR / safe_filename(date)

    buf = io.StringIO()
    csv.writer(buf).writerow([hw_text])
    line = buf.getvalue()

    try:
        async with aiofiles.open(path, "a", encoding="utf-8", newline="") as af:
            await af.write(line)
    except Exception as e:
        logger.exception("Ошибка записи в файл")
        await message.answer(f"Не удалось сохранить домашку: {e}")
        current_user.pop(user_id, None)
        return

    current_user.pop(user_id, None)
    await message.answer("Домашка сохранена.")


@dp.message(Command(commands=["print_hw"]))
async def print_hw(message: Message):
    user_id = message.from_user.id
    if user_id not in user_dates:
        await message.answer("Сначала установите дату с помощью /set_date.")
        return
    date = user_dates[user_id]
    path = OUT_DIR / safe_filename(date)

    if not path.exists():
        await message.answer("Файл за эту дату не найден.")
        return

    try:
        async with aiofiles.open(path, "r", encoding="utf-8", newline="") as af:
            content = await af.read()
    except Exception as e:
        logger.exception("Ошибка чтения файла")
        await message.answer(f"Ошибка при чтении файла: {e}")
        return

    reader = csv.reader(io.StringIO(content))
    lines = []
    for row in reader:
        if not row:
            continue
        task = row[0] if len(row) > 0 else ""
        lines.append(f"Задание: {task}")

    if not lines:
        await message.answer("Нет записей в этом файле.")
        return

    # Разбиваем на части, чтобы не превысить лимит Telegram (≈4096)
    chunk = []
    cur_len = 0
    for ln in lines:
        if cur_len + len(ln) + 1 > 3900:
            await message.answer("\n".join(chunk))
            chunk = [ln]
            cur_len = len(ln) + 1
        else:
            chunk.append(ln)
            cur_len += len(ln) + 1
    if chunk:
        await message.answer("\n".join(chunk))


async def main():
    logger.info("Starting bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
