"""
Keyboards — inline-клавиатуры бота.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Цвета ─────────────────────────────────────────────────────────────────────
COLORS: dict[str, dict] = {
    "red":    {"hex": "#E63946", "label": "Красный",    "icon": "🔴"},
    "orange": {"hex": "#F4772E", "label": "Оранжевый",  "icon": "🟠"},
    "yellow": {"hex": "#F9C74F", "label": "Жёлтый",    "icon": "🟡"},
    "green":  {"hex": "#2DC653", "label": "Зелёный",   "icon": "🟢"},
    "blue":   {"hex": "#3A86FF", "label": "Синий",     "icon": "🔵"},
    "violet": {"hex": "#7B2FBE", "label": "Фиолетовый","icon": "🟣"},
    "pink":   {"hex": "#FF4DA6", "label": "Розовый",   "icon": "🩷"},
    "cyan":   {"hex": "#00B4D8", "label": "Голубой",   "icon": "🩵"},
    "gold":   {"hex": "#FFB703", "label": "Золотой",   "icon": "💛"},
    "teal":   {"hex": "#0D9488", "label": "Бирюзовый", "icon": "🫧"},
    "white":  {"hex": "#F0F0F4", "label": "Белый",     "icon": "🤍"},
    "black":  {"hex": "#1A1A2E", "label": "Чёрный",    "icon": "🖤"},
}

# ── Фоны для конвертации ──────────────────────────────────────────────────────
CONVERT_BG_OPTIONS: list[tuple[str, str, str]] = [
    ("transparent", "Без фона",  "🔲"),
    ("green",       "Зелёный",   "🟩"),
    ("black",       "Чёрный",    "⬛"),
    ("white",       "Белый",     "⬜"),
    ("red",         "Красный",   "🟥"),
]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎨  Перекрасить стикеры",   callback_data="mode:recolor")],
            [InlineKeyboardButton(text="📋  Получить ID стикеров",   callback_data="mode:id")],
            [InlineKeyboardButton(text="〈/〉  Экспортировать SVG",   callback_data="mode:svg")],
            [InlineKeyboardButton(text="🖼  Конвертировать стикер",  callback_data="mode:convert")],
        ]
    )


def color_keyboard() -> InlineKeyboardMarkup:
    keys = list(COLORS.items())
    rows = []
    # 3 кнопки в ряд — удобнее на мобильном
    for i in range(0, len(keys), 3):
        row = [
            InlineKeyboardButton(
                text=f"{v['icon']} {v['label']}",
                callback_data=f"color:{k}",
            )
            for k, v in keys[i : i + 3]
        ]
        rows.append(row)

    rows.append([InlineKeyboardButton(text="✏️  Свой цвет (HEX)", callback_data="color:custom")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="back:menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


RATIO_LABELS: dict[str, str] = {
    "1x1":  "⬜ 1:1 — Квадрат",
    "16x9": "🖥 16:9 — Горизонтально",
    "9x16": "📱 9:16 — Вертикально",
}


def convert_ratio_keyboard() -> InlineKeyboardMarkup:
    """Выбор соотношения сторон для видео-формата."""
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"cvt_ratio:{key}")]
        for key, label in RATIO_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="back:convert_opts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def convert_options_keyboard() -> InlineKeyboardMarkup:
    """
    Двухколоночная клавиатура: левая — 📷 Фото (PNG), правая — 🎬 Видео (GIF).
    Каждая строка — один вариант фона.
    """
    rows = []
    for bg_key, label, icon in CONVERT_BG_OPTIONS:
        rows.append([
            InlineKeyboardButton(
                text=f"📷 {icon} {label}",
                callback_data=f"cvt:photo:{bg_key}",
            ),
            InlineKeyboardButton(
                text=f"🎬 {icon} {label}",
                callback_data=f"cvt:video:{bg_key}",
            ),
        ])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
