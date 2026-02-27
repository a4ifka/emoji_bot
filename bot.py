"""
Sticker Pack Bot
────────────────
Режимы: Перекрасить | ID | SVG | Конвертировать
Вход — ссылка на стикер-пак (t.me/addstickers/...).
"""

import asyncio
import logging
import os
import re
import time
import hashlib
from aiogram import Bot, Dispatcher, F
from aiogram.enums import MessageEntityType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputSticker,
    Message,
)
from dotenv import load_dotenv

from html_generator import HTMLGenerator
from keyboards import (
    main_menu_keyboard,
    color_keyboard,
    convert_options_keyboard,
    convert_ratio_keyboard,
    COLORS,
    CONVERT_BG_OPTIONS,
    RATIO_LABELS,
)
from sticker_processor import StickerProcessor, CONVERT_RATIOS

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
processor = StickerProcessor()
html_gen = HTMLGenerator()


# ── FSM ──────────────────────────────────────────────────────────────────────
class Flow(StatesGroup):
    choosing_mode = State()
    waiting_link = State()             # ждём ссылку на пак
    waiting_color = State()            # ждём выбор цвета (только для recolor)
    waiting_sticker_convert = State()  # ждём стикер/эмодзи для конвертации


# ── Helpers ───────────────────────────────────────────────────────────────────
LINK_RE = re.compile(
    r"(?:https?://)?t\.me/(?:addstickers|addemoji)/([A-Za-z0-9_]{5,64})"
)

# Метки фонов для отображения пользователю
_BG_LABELS: dict[str, str] = {bg_key: label for bg_key, label, _ in CONVERT_BG_OPTIONS}


def parse_pack_name(text: str) -> str | None:
    text = text.strip()
    m = LINK_RE.search(text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_]{5,64}", text):
        return text
    return None


async def fetch_sticker_bytes(file_id: str, retries: int = 4) -> bytes:
    """Скачивает файл стикера с retry при SSL/сетевых ошибках."""
    last_err = None
    for attempt in range(retries):
        try:
            file_info = await bot.get_file(file_id)
            raw = await bot.download_file(file_info.file_path)
            return raw.read()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
            logger.warning(f"fetch_sticker_bytes attempt {attempt + 1}/{retries} failed: {e}")
    raise last_err


def short_name_for(user_id: int, bot_username: str) -> str:
    ts = int(time.time()) % 100000
    h = hashlib.md5(f"{user_id}{ts}".encode()).hexdigest()[:4]
    base = f"rc{h}{ts}_by_{bot_username}"
    return base[:64]


# ── /start ────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я Sticker Pack Bot.</b>\n\n"
        "Выбери что хочешь сделать со стикер-паком:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(Flow.choosing_mode)


@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Главное меню — выбери режим:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(Flow.choosing_mode)


# ── Кнопки главного меню ──────────────────────────────────────────────────────
@dp.callback_query(F.data.in_({"mode:recolor", "mode:id", "mode:svg", "mode:convert"}))
async def cb_mode(call: CallbackQuery, state: FSMContext):
    mode = call.data.split(":")[1]

    if mode == "convert":
        await state.clear()
        await state.set_state(Flow.waiting_sticker_convert)
        await call.message.edit_text(
            "🖼 <b>Конвертировать стикер</b>\n\n"
            "Отправь один стикер или кастомный эмодзи.\n"
            "<i>Для кастомных эмодзи отправь сообщение с ровно одним эмодзи.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Назад", callback_data="back:menu")
            ]]),
            parse_mode="HTML",
        )
        await call.answer()
        return

    mode_labels = {
        "recolor": "🎨 Перекрасить",
        "id": "📋 Получить ID",
        "svg": "〈/〉 Экспорт SVG",
    }
    await state.update_data(mode=mode)
    await state.set_state(Flow.waiting_link)

    await call.message.edit_text(
        f"<b>{mode_labels[mode]}</b>\n\n"
        "Пришли ссылку на стикер-пак или его название:\n\n"
        "<code>https://t.me/addstickers/PackName</code>\n"
        "<i>или просто</i> <code>PackName</code>\n\n"
        "Работает как с обычными, так и с премиум-паками.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="← Назад", callback_data="back:menu")
            ]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "back:menu")
async def cb_back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "Выбери режим:",
        reply_markup=main_menu_keyboard(),
    )
    await state.set_state(Flow.choosing_mode)
    await call.answer()


# ── Получение ссылки на пак ───────────────────────────────────────────────────
@dp.message(Flow.waiting_link)
async def handle_link(message: Message, state: FSMContext):
    pack_name = parse_pack_name(message.text or "")
    if not pack_name:
        await message.answer(
            "❌ Не могу распознать ссылку.\n"
            "Попробуй: <code>https://t.me/addstickers/PackName</code>",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    mode = data.get("mode", "id")

    # Проверяем что пак существует
    try:
        sticker_set = await bot.get_sticker_set(pack_name)
    except Exception:
        await message.answer(
            f"❌ Стикер-пак <code>{pack_name}</code> не найден.\n"
            f"Проверь название и попробуй ещё раз.",
            parse_mode="HTML",
        )
        return

    await state.update_data(
        pack_name=pack_name,
        pack_title=sticker_set.title,
        total=len(sticker_set.stickers),
    )

    if mode == "recolor":
        await state.set_state(Flow.waiting_color)
        await message.answer(
            f"✅ Пак найден: <b>{sticker_set.title}</b> ({len(sticker_set.stickers)} стикеров)\n\n"
            "🎨 <b>Выбери цвет для перекраски:</b>",
            reply_markup=color_keyboard(),
            parse_mode="HTML",
        )
    else:
        # ID или SVG — сразу обрабатываем
        await process_pack(message, state, pack_name, sticker_set, mode)


# ── Выбор цвета ───────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("color:"))
async def cb_color(call: CallbackQuery, state: FSMContext):
    color_key = call.data.split(":", 1)[1]

    if color_key == "custom":
        await call.message.edit_text(
            "✏️ Введи свой цвет в формате HEX:\n"
            "<code>#FF5733</code>  <code>#1A2B3C</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Назад к цветам", callback_data="back:colors")
            ]]),
            parse_mode="HTML",
        )
        await state.update_data(awaiting_custom_color=True)
        await call.answer()
        return

    if color_key not in COLORS:
        await call.answer("Неизвестный цвет", show_alert=True)
        return

    hex_color = COLORS[color_key]["hex"]
    await call.answer(f"Цвет выбран: {hex_color}")

    data = await state.get_data()
    pack_name = data.get("pack_name")
    pack_title = data.get("pack_title")

    try:
        sticker_set = await bot.get_sticker_set(pack_name)
    except Exception:
        await call.message.answer("❌ Ошибка загрузки пака. Начни заново /menu")
        return

    await call.message.edit_text(
        f"⏳ Перекрашиваю пак <b>{pack_title}</b>...\n"
        f"Цвет: <code>{hex_color}</code> · {len(sticker_set.stickers)} стикеров",
        parse_mode="HTML",
    )

    await do_recolor(call.message, state, pack_name, sticker_set, hex_color, COLORS[color_key]["label"])


@dp.callback_query(F.data == "back:colors")
async def cb_back_colors(call: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_custom_color=False)
    await call.message.edit_text(
        "🎨 <b>Выбери цвет для перекраски:</b>",
        reply_markup=color_keyboard(),
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(Flow.waiting_color)
async def handle_custom_color(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("awaiting_custom_color"):
        await message.answer("Пожалуйста, выбери цвет из кнопок ниже 👇")
        return

    text = message.text.strip()
    if not re.match(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$", text):
        await message.answer(
            "❌ Неверный формат. Введи HEX-цвет: <code>#FF5733</code>",
            parse_mode="HTML",
        )
        return

    hex_color = text.upper()
    await state.update_data(awaiting_custom_color=False)

    pack_name = data.get("pack_name")
    pack_title = data.get("pack_title")

    try:
        sticker_set = await bot.get_sticker_set(pack_name)
    except Exception:
        await message.answer("❌ Ошибка загрузки пака. Начни заново /menu")
        return

    progress = await message.answer(
        f"⏳ Перекрашиваю пак <b>{pack_title}</b>...\n"
        f"Цвет: <code>{hex_color}</code> · {len(sticker_set.stickers)} стикеров",
        parse_mode="HTML",
    )
    await do_recolor(progress, state, pack_name, sticker_set, hex_color, hex_color)


# ── Обработка пака (ID / SVG) ─────────────────────────────────────────────────
async def process_pack(
    message: Message,
    state: FSMContext,
    pack_name: str,
    sticker_set,
    mode: str,
):
    await state.clear()
    total = len(sticker_set.stickers)

    progress = await message.answer(
        f"⏳ {'Собираю ID' if mode == 'id' else 'Конвертирую в SVG'}...\n"
        f"Пак: <b>{sticker_set.title}</b> · {total} стикеров",
        parse_mode="HTML",
    )

    try:
        stickers_data = []
        for i, sticker in enumerate(sticker_set.stickers):
            if i % 8 == 0 and i > 0:
                await progress.edit_text(
                    f"⏳ Обрабатываю {i}/{total}...\n"
                    f"Пак: <b>{sticker_set.title}</b>",
                    parse_mode="HTML",
                )

            img_bytes = await fetch_sticker_bytes(sticker.file_id)

            entry = {
                "index": i + 1,
                "file_id": sticker.file_id,
                "file_unique_id": sticker.file_unique_id,
                "file_path": "",
                "emoji": sticker.emoji or "🎭",
                "width": sticker.width,
                "height": sticker.height,
                "is_animated": sticker.is_animated,
                "is_video": sticker.is_video,
                "img_bytes": img_bytes,
            }

            if mode == "svg":
                svg_content = await processor.to_svg(img_bytes, sticker.is_animated)
                entry["svg_content"] = svg_content

            stickers_data.append(entry)

        if mode == "id":
            html_bytes = html_gen.id_report(
                set_name=pack_name,
                title=sticker_set.title,
                stickers=stickers_data,
            ).encode("utf-8")
            filename = f"{pack_name}_ids.html"
            caption = (
                f"📋 <b>ID стикер-пака</b>\n\n"
                f"📦 {sticker_set.title}\n"
                f"📊 Стикеров: {total}\n\n"
                "Открой HTML в браузере — там все ID, коды и превью."
            )
        else:  # svg
            html_bytes = html_gen.svg_report(
                set_name=pack_name,
                title=sticker_set.title,
                stickers=stickers_data,
            ).encode("utf-8")
            filename = f"{pack_name}_svg.html"
            caption = (
                f"〈/〉 <b>SVG экспорт</b>\n\n"
                f"📦 {sticker_set.title}\n"
                f"📊 Стикеров: {total}\n\n"
                "Открой HTML — все стикеры в векторном SVG формате с возможностью скачать каждый."
            )

        await message.answer_document(
            BufferedInputFile(html_bytes, filename=filename),
            caption=caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← В меню", callback_data="back:menu_fresh")
            ]]),
        )
        await progress.delete()

    except Exception as e:
        logger.error(f"Error in process_pack: {e}", exc_info=True)
        await progress.edit_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ── Перекраска + создание нового пака (параллельная) ─────────────────────────
async def do_recolor(
    progress_msg: Message,
    state: FSMContext,
    pack_name: str,
    sticker_set,
    hex_color: str,
    color_label: str,
):
    await state.clear()
    total = len(sticker_set.stickers)
    stickers = sticker_set.stickers

    try:
        me = await bot.get_me()
        new_name = short_name_for(progress_msg.chat.id, me.username)
        new_title = f"{sticker_set.title} [{color_label}]"[:64]

        # ── Фаза 1: параллельная загрузка ────────────────────────────────────
        await progress_msg.edit_text(
            f"⬇️ Скачиваю {total} стикеров...\n"
            f"Цвет: <code>{hex_color}</code>",
            parse_mode="HTML",
        )
        dl_sem = asyncio.Semaphore(8)

        async def _fetch(sticker):
            async with dl_sem:
                return await fetch_sticker_bytes(sticker.file_id)

        raw_list = await asyncio.gather(*[_fetch(s) for s in stickers])

        # ── Фаза 2: параллельная перекраска ──────────────────────────────────
        await progress_msg.edit_text(
            f"🎨 Перекрашиваю {total} стикеров...\n"
            f"Цвет: <code>{hex_color}</code>",
            parse_mode="HTML",
        )

        async def _recolor_one(sticker, raw):
            if sticker.is_animated:
                rc = await processor.recolor_tgs(raw, hex_color)
                return (rc, sticker.emoji or "⭐", True, False)
            elif sticker.is_video:
                return (raw, sticker.emoji or "⭐", False, True)
            else:
                rc = await processor.recolor(raw, hex_color)
                return (rc, sticker.emoji or "⭐", False, False)

        recolored = list(await asyncio.gather(
            *[_recolor_one(s, r) for s, r in zip(stickers, raw_list)]
        ))

        # ── Фаза 3: создание пака (первый стикер) ────────────────────────────
        await progress_msg.edit_text(
            f"📤 Создаю пак и загружаю {total} стикеров...",
            parse_mode="HTML",
        )

        first_bytes, first_emoji, first_anim, first_vid = recolored[0]
        first_fmt = "animated" if first_anim else ("video" if first_vid else "static")
        first_fn = "sticker.tgs" if first_anim else ("sticker.webm" if first_vid else "sticker.png")

        await bot.create_new_sticker_set(
            user_id=progress_msg.chat.id,
            name=new_name,
            title=new_title,
            stickers=[InputSticker(
                sticker=BufferedInputFile(first_bytes, filename=first_fn),
                emoji_list=[first_emoji],
                format=first_fmt,
            )],
            sticker_type=sticker_set.sticker_type,
        )

        # ── Фаза 4: параллельная загрузка остальных стикеров ─────────────────
        upload_sem = asyncio.Semaphore(3)
        uploaded = 0  # сколько стикеров загружено в фазе 4

        async def _upload(item):
            nonlocal uploaded
            img_bytes, emoji, is_anim, is_vid = item
            fmt = "animated" if is_anim else ("video" if is_vid else "static")
            fn = "sticker.tgs" if is_anim else ("sticker.webm" if is_vid else "sticker.png")
            async with upload_sem:
                try:
                    await bot.add_sticker_to_set(
                        user_id=progress_msg.chat.id,
                        name=new_name,
                        sticker=InputSticker(
                            sticker=BufferedInputFile(img_bytes, filename=fn),
                            emoji_list=[emoji],
                            format=fmt,
                        ),
                    )
                except Exception as e:
                    logger.warning(f"Skip sticker: {e}")
            uploaded += 1

        async def _show_upload_progress():
            """Обновляем прогресс каждые 2с, пока все стикеры не загружены."""
            remaining = total - 1  # сколько ещё загружать
            while uploaded < remaining:
                try:
                    await progress_msg.edit_text(
                        f"📤 Загружаю стикеры... {uploaded + 1}/{remaining}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                await asyncio.sleep(2)

        if len(recolored) > 1:
            await asyncio.gather(
                asyncio.gather(*[_upload(item) for item in recolored[1:]]),
                _show_upload_progress(),
            )

        # ── Готово ────────────────────────────────────────────────────────────
        new_link = f"https://t.me/addstickers/{new_name}"
        await progress_msg.edit_text(
            f"✅ <b>Готово!</b>\n\n"
            f"🎨 Цвет: <code>{hex_color}</code>\n"
            f"📦 Оригинал: {sticker_set.title}\n"
            f"✨ Новый пак: <b>{new_title}</b>\n"
            f"📊 Стикеров: {total}\n\n"
            f"👇 Жми на ссылку чтобы добавить пак:\n"
            f"<a href='{new_link}'>{new_link}</a>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить стикер-пак", url=new_link)],
                [InlineKeyboardButton(text="← В меню", callback_data="back:menu_fresh")],
            ]),
            disable_web_page_preview=False,
        )

    except Exception as e:
        logger.error(f"Recolor error: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ Ошибка при перекраске:\n<code>{e}</code>\n\n"
            "Возможно, бот не может создать пак от твоего имени. "
            "Сначала отправь боту /start и попробуй ещё раз.",
            parse_mode="HTML",
        )


# ── Конвертация стикера: приём стикера ────────────────────────────────────────
@dp.message(Flow.waiting_sticker_convert)
async def handle_convert_sticker(message: Message, state: FSMContext):
    """
    Принимает стикер или сообщение с кастомным эмодзи (ровно 1 шт.).
    Проверяет что прислали именно один стикер/эмодзи.
    """
    file_id: str | None = None
    is_animated = False
    is_video = False
    emoji = "⭐"

    if message.sticker:
        # Обычный стикер
        s = message.sticker
        file_id = s.file_id
        is_animated = s.is_animated
        is_video = s.is_video
        emoji = s.emoji or "⭐"

    elif message.text and message.entities:
        # Кастомный эмодзи в тексте
        custom = [e for e in message.entities if e.type == MessageEntityType.CUSTOM_EMOJI]
        if len(custom) > 1:
            await message.answer(
                "❌ Отправь только <b>один</b> эмодзи или стикер.",
                parse_mode="HTML",
            )
            return
        elif len(custom) == 1:
            try:
                stickers = await bot.get_custom_emoji_stickers(
                    custom_emoji_ids=[custom[0].custom_emoji_id]
                )
                if not stickers:
                    await message.answer("❌ Не удалось получить данные эмодзи.")
                    return
                s = stickers[0]
                file_id = s.file_id
                is_animated = s.is_animated
                is_video = s.is_video
                emoji = s.emoji or "⭐"
            except Exception as e:
                await message.answer(
                    f"❌ Ошибка при получении эмодзи: <code>{e}</code>",
                    parse_mode="HTML",
                )
                return
        else:
            await message.answer(
                "❌ Нужно отправить стикер или кастомный эмодзи.",
                parse_mode="HTML",
            )
            return
    else:
        await message.answer(
            "❌ Нужно отправить <b>стикер</b> или <b>кастомный эмодзи</b>.\n"
            "Обычные Unicode-эмодзи (😀) не поддерживаются.",
            parse_mode="HTML",
        )
        return

    await state.update_data(
        convert_file_id=file_id,
        convert_is_animated=is_animated,
        convert_is_video=is_video,
        convert_emoji=emoji,
    )

    sticker_type_label = (
        "🎞 Анимированный" if is_animated
        else ("📹 Видео" if is_video
              else "🖼 Статичный")
    )

    video_note = ""
    if is_video:
        video_note = "\n\n⚠️ <i>Видео-стикеры (WebM): доступно только первый кадр.</i>"
    elif is_animated and not processor.rlottie_available():
        video_note = (
            "\n\n⚠️ <i>rlottie-python не установлен — "
            "анимация будет экспортирована только первым кадром.\n"
            "Установи: <code>pip install rlottie-python</code></i>"
        )

    await message.answer(
        f"✅ Получен стикер — <b>{sticker_type_label}</b>\n\n"
        "Выбери формат (📷 Фото = PNG, 🎬 Видео = GIF) и фон:"
        f"{video_note}",
        reply_markup=convert_options_keyboard(),
        parse_mode="HTML",
    )


# ── Конвертация стикера: выбор фон+формат ────────────────────────────────────
@dp.callback_query(F.data.startswith("cvt:"))
async def cb_convert_options(call: CallbackQuery, state: FSMContext):
    """cvt:{fmt}:{bg_key}  →  fmt = photo | video"""
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Неверный формат.", show_alert=True)
        return

    _, fmt, bg_key = parts

    data = await state.get_data()
    if not data.get("convert_file_id"):
        await call.answer("Стикер не найден. Отправь стикер заново.", show_alert=True)
        return

    await call.answer()

    if fmt == "video":
        # Видео → сначала выбор соотношения сторон
        await state.update_data(convert_bg_key=bg_key)
        bg_label = _BG_LABELS.get(bg_key, bg_key)
        await call.message.edit_text(
            f"🎬 Видео · фон: <b>{bg_label}</b>\n\n"
            "Выбери соотношение сторон:",
            reply_markup=convert_ratio_keyboard(),
            parse_mode="HTML",
        )
        return

    # Фото — сразу обрабатываем
    await _do_convert(call, state, bg_key, fmt="photo", ratio=None)


# ── Конвертация стикера: выбор соотношения сторон (только для видео) ──────────
@dp.callback_query(F.data.startswith("cvt_ratio:"))
async def cb_convert_ratio(call: CallbackQuery, state: FSMContext):
    """cvt_ratio:{ratio}  →  ratio = 1x1 | 16x9 | 9x16"""
    ratio = call.data.split(":")[1]
    data = await state.get_data()
    bg_key: str | None = data.get("convert_bg_key")

    if not data.get("convert_file_id") or not bg_key:
        await call.answer("Ошибка сессии. Отправь стикер заново.", show_alert=True)
        return

    await call.answer()
    await _do_convert(call, state, bg_key, fmt="video", ratio=ratio)


@dp.callback_query(F.data == "back:convert_opts")
async def cb_back_convert_opts(call: CallbackQuery, state: FSMContext):
    """Возврат к выбору формата и фона."""
    data = await state.get_data()
    is_animated = data.get("convert_is_animated", False)
    is_video = data.get("convert_is_video", False)
    sticker_type_label = (
        "🎞 Анимированный" if is_animated
        else ("📹 Видео" if is_video else "🖼 Статичный")
    )
    await call.message.edit_text(
        f"✅ Стикер — <b>{sticker_type_label}</b>\n\n"
        "Выбери формат (📷 Фото = PNG, 🎬 Видео = GIF) и фон:",
        reply_markup=convert_options_keyboard(),
        parse_mode="HTML",
    )
    await call.answer()


# ── Конвертация: общая логика обработки ───────────────────────────────────────
async def _do_convert(
    call: CallbackQuery,
    state: FSMContext,
    bg_key: str,
    fmt: str,
    ratio: str | None,
) -> None:
    """
    Выполняет конвертацию стикера. Вызывается из cb_convert_options (photo)
    и cb_convert_ratio (video).
    """
    data = await state.get_data()
    file_id: str = data["convert_file_id"]
    is_animated: bool = data.get("convert_is_animated", False)
    is_video: bool = data.get("convert_is_video", False)

    canvas_wh = CONVERT_RATIOS.get(ratio) if ratio else None
    bg_label = _BG_LABELS.get(bg_key, bg_key)
    ratio_label = RATIO_LABELS.get(ratio, "") if ratio else ""

    await call.message.edit_text("⏳ Конвертирую...", reply_markup=None)

    back_btn = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="← В меню", callback_data="back:menu_fresh")
    ]])

    try:
        img_bytes = await fetch_sticker_bytes(file_id)

        if is_video:
            # WebM: не поддерживаем добавление фона
            await call.message.edit_text(
                "⚠️ Видео-стикеры (WebM) не поддерживают добавление фона.\n"
                "Отправляю исходный файл.",
                reply_markup=back_btn,
                parse_mode="HTML",
            )
            await call.message.answer_document(
                BufferedInputFile(img_bytes, filename="sticker.webm"),
                caption="📹 Исходный видео-стикер",
                reply_markup=back_btn,
            )
            await state.clear()
            return

        if is_animated:
            as_gif = (fmt == "video")

            if not processor.rlottie_available():
                # Нет rlottie — fallback на первый кадр
                await call.message.edit_text(
                    "⚠️ <code>rlottie-python</code> не установлен — "
                    "отдаю первый кадр как PNG.\n"
                    "<code>pip install rlottie-python</code>",
                    parse_mode="HTML",
                    reply_markup=back_btn,
                )
                await asyncio.sleep(1)
                result = await processor.tgs_to_media(img_bytes, bg_key, as_gif=False, canvas_wh=canvas_wh)
                caption = f"📷 Первый кадр · {bg_label}"
                if ratio_label:
                    caption += f" · {ratio_label}"
                await call.message.answer_photo(
                    BufferedInputFile(result, filename="sticker.png"),
                    caption=caption,
                    reply_markup=back_btn,
                )
            elif as_gif:
                result = await processor.tgs_to_media(img_bytes, bg_key, as_gif=True, canvas_wh=canvas_wh)
                caption = f"🎬 Анимация · {bg_label}"
                if ratio_label:
                    caption += f" · {ratio_label}"
                await call.message.answer_animation(
                    BufferedInputFile(result, filename="sticker.gif"),
                    caption=caption,
                    reply_markup=back_btn,
                )
            else:
                result = await processor.tgs_to_media(img_bytes, bg_key, as_gif=False, canvas_wh=canvas_wh)
                await call.message.answer_photo(
                    BufferedInputFile(result, filename="sticker.png"),
                    caption=f"📷 Первый кадр · {bg_label}",
                    reply_markup=back_btn,
                )
        else:
            # Статичный стикер → PNG (с canvas для видео-режима)
            result = await processor.add_background(img_bytes, bg_key, canvas_wh=canvas_wh)
            caption = f"📷 Стикер · {bg_label}"
            if ratio_label:
                caption += f" · {ratio_label}"
            if fmt == "video":
                caption += "\n<i>(статичный стикер → PNG с нужным соотношением сторон)</i>"
            await call.message.answer_photo(
                BufferedInputFile(result, filename="sticker.png"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=back_btn,
            )

        await call.message.delete()
        await state.clear()

    except RuntimeError as e:
        await call.message.edit_text(
            f"❌ {e}",
            parse_mode="HTML",
            reply_markup=back_btn,
        )
    except Exception as e:
        logger.error(f"Convert error: {e}", exc_info=True)
        await call.message.edit_text(
            f"❌ Ошибка конвертации: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=back_btn,
        )


# ── Кнопка "В меню" из документа ─────────────────────────────────────────────
@dp.callback_query(F.data == "back:menu_fresh")
async def cb_menu_fresh(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(
        "Выбери режим:",
        reply_markup=main_menu_keyboard(),
    )
    await call.answer()


# ── Fallback ──────────────────────────────────────────────────────────────────
@dp.message()
async def fallback(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer(
            "Используй /start или /menu чтобы начать.",
            reply_markup=main_menu_keyboard(),
        )
        await state.set_state(Flow.choosing_mode)


# ── Entry ─────────────────────────────────────────────────────────────────────
async def main():
    logger.info("Bot starting...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
