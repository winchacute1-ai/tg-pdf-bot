import io
import asyncio
from datetime import datetime
from typing import Dict, List
from PIL import Image

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.enums import ParseMode

BOT_TOKEN = "8588564662:AAFM0m6hqoDe3paSN7fKeBTkPNMAVdo_KAY"
ALLOWED_USERS = {852954946}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище сессий: {user_id: [BytesIO, ...]}
user_sessions: Dict[int, List[io.BytesIO]] = {}


def get_queue_keyboard(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✨ Собрать документ ({count})",
                    callback_data="build_pdf"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Очистить очередь",
                    callback_data="clear_queue"
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return

    user_sessions[message.from_user.id] = []
    text = (
        "👋 *Привет!*\n\n"
        "Я помогу быстро склеить изображения в аккуратный PDF-документ.\n\n"
        "📌 *Как пользоваться:*\n"
        "• Отправляй JPG или PNG (как обычные фото или без сжатия файлами)\n"
        "• Страницы будут идти строго в том порядке, в котором ты их присылаешь\n"
        "• Нажми *«Собрать документ»*, когда все страницы загружены\n\n"
        "_Готов к работе. Жду первые страницы..._"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return

    user_sessions[message.from_user.id] = []
    await message.answer("🗑 *Очередь страниц очищена.*", parse_mode=ParseMode.MARKDOWN)


@dp.message(F.photo | F.document)
async def handle_incoming_image(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type in ["image/jpeg", "image/png", "image/webp"]:
        file_id = message.document.file_id

    if not file_id:
        return

    file_obj = await bot.get_file(file_id)
    image_bytes = await bot.download_file(file_obj.file_path)

    if user_id not in user_sessions:
        user_sessions[user_id] = []

    user_sessions[user_id].append(image_bytes)
    count = len(user_sessions[user_id])

    text = (
        f"📥 *Страница добавлена: #{count}*\n"
        f"Всего в очереди: `{count}` шт.\n\n"
        f"_Присылай ещё или нажми на кнопку сборки._"
    )

    await message.answer(
        text,
        reply_markup=get_queue_keyboard(count),
        parse_mode=ParseMode.MARKDOWN
    )


@dp.callback_query(F.data == "clear_queue")
async def cb_clear(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_sessions[user_id] = []
    await callback.message.edit_text(
        "🗑 *Очередь сброшена.*\nМожешь присылать страницы заново.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@dp.callback_query(F.data == "build_pdf")
async def cb_build_pdf(callback: CallbackQuery):
    user_id = callback.from_user.id
    images_data = user_sessions.get(user_id, [])

    if not images_data:
        await callback.answer("⚠️ Очередь пуста. Сначала отправь фото.", show_alert=True)
        return

    await callback.message.edit_text(
        "⚙️ *Собираю PDF-документ...*\n_Оптимизирую страницы и склеиваю слои._",
        parse_mode=ParseMode.MARKDOWN
    )

    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(None, compile_pdf, images_data)

    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"scan_{date_str}.pdf"

    document = BufferedInputFile(pdf_bytes.getvalue(), filename=filename)

    caption = (
        f"📄 *Документ успешно сформирован!*\n\n"
        f"• *Файл:* `{filename}`\n"
        f"• *Количество страниц:* `{len(images_data)}`\n"
        f"• *Статус:* готов к печати или отправке"
    )

    await callback.message.answer_document(
        document=document,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN
    )

    user_sessions[user_id] = []
    await callback.message.delete()
    await callback.answer()


def compile_pdf(images_data: List[io.BytesIO]) -> io.BytesIO:
    pil_images = []
    for raw in images_data:
        raw.seek(0)
        img = Image.open(raw)
        if img.mode != "RGB":
            img = img.convert("RGB")
        pil_images.append(img)

    output = io.BytesIO()
    first_image = pil_images[0]
    rest_images = pil_images[1:] if len(pil_images) > 1 else []

    first_image.save(
        output,
        format="PDF",
        save_all=True,
        append_images=rest_images,
        resolution=100.0,
        quality=85
    )
    output.seek(0)
    return output


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
