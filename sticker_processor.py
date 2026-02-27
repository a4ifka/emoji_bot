"""
StickerProcessor
────────────────
• recolor(img_bytes, hex_color)              → PNG bytes с новым цветом
• recolor_tgs(tgs_bytes, hex_color)          → TGS bytes с новым цветом (Lottie)
• to_svg(img_bytes, is_animated)             → SVG string
• add_background(img_bytes, bg_key)          → PNG bytes со статичным стикером на фоне
• tgs_to_media(tgs_bytes, bg_key, as_gif)    → PNG/GIF bytes анимированного стикера
"""

import asyncio
import gzip
import io
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

# Пул потоков — используем все CPU + запас для I/O-bound задач
_pool = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) + 4))

# ── Фоны для конвертации ──────────────────────────────────────────────────────
CONVERT_BG_COLORS: dict[str, tuple[int, int, int] | None] = {
    "transparent": None,
    "green":       (0, 255, 0),
    "black":       (0, 0, 0),
    "white":       (255, 255, 255),
    "red":         (255, 0, 0),
}

# ── Соотношения сторон (canvas в пикселях) ────────────────────────────────────
# 910 / 512 ≈ 16/9,  512 / 910 ≈ 9/16
CONVERT_RATIOS: dict[str, tuple[int, int]] = {
    "1x1":  (512, 512),
    "16x9": (910, 512),
    "9x16": (512, 910),
}

# ── Опциональная зависимость rlottie ─────────────────────────────────────────
try:
    from rlottie_python import LottieAnimation as _LottieAnim
    _HAS_RLOTTIE = True
except ImportError:
    _HAS_RLOTTIE = False


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ── Перекраска статичного стикера ─────────────────────────────────────────────
def _recolor_sync(img_bytes: bytes, hex_color: str) -> bytes:
    """
    Алгоритм:
    1. Переводим в RGBA
    2. Вычисляем luminance каждого пикселя (яркость)
    3. Заменяем RGB → target_color × luminance (сохраняем тени/светлые зоны)
    4. Сохраняем alpha без изменений
    """
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception:
        return img_bytes

    rt, gt, bt = [x / 255.0 for x in _hex_to_rgb(hex_color)]

    arr = np.array(img, dtype=np.float32) / 255.0
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]

    # Luminance (перцептивная яркость)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

    # Степень насыщенности пикселя (насколько он «цветной»)
    mx = np.maximum(r, np.maximum(g, b))
    mn = np.minimum(r, np.minimum(g, b))
    saturation = np.where(mx > 0.001, (mx - mn) / mx, 0.0)

    # Если пиксель очень тёмный или белый — смешиваем меньше
    blend = np.clip(saturation * 0.6 + 0.4, 0.3, 1.0)

    # Новый цвет = target × luminance × 2 (×2 чтобы середина была яркой)
    nr = np.clip(rt * lum * 2.0 * blend + lum * (1 - blend), 0, 1)
    ng = np.clip(gt * lum * 2.0 * blend + lum * (1 - blend), 0, 1)
    nb = np.clip(bt * lum * 2.0 * blend + lum * (1 - blend), 0, 1)

    result = np.stack([
        (nr * 255).astype(np.uint8),
        (ng * 255).astype(np.uint8),
        (nb * 255).astype(np.uint8),
        (a * 255).astype(np.uint8),
    ], axis=-1)

    out = io.BytesIO()
    Image.fromarray(result, "RGBA").save(out, format="PNG")
    return out.getvalue()


# ── Перекраска анимированного TGS (Lottie JSON) ───────────────────────────────
def _recolor_lottie_sync(tgs_bytes: bytes, hex_color: str) -> bytes:
    """
    Разбирает Lottie JSON внутри TGS, применяет luminance-тинт
    ко всем цветам (fill, stroke, gradient) и упаковывает обратно в TGS.
    """
    try:
        lottie_json = gzip.decompress(tgs_bytes).decode("utf-8")
        data = json.loads(lottie_json)
    except Exception:
        return tgs_bytes

    rt, gt, bt = [x / 255.0 for x in _hex_to_rgb(hex_color)]

    def tint(r: float, g: float, b: float):
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        mx, mn = max(r, g, b), min(r, g, b)
        sat = (mx - mn) / mx if mx > 0.001 else 0.0
        blend = min(max(sat * 0.6 + 0.4, 0.3), 1.0)
        nr = min(rt * lum * 2.0 * blend + lum * (1 - blend), 1.0)
        ng = min(gt * lum * 2.0 * blend + lum * (1 - blend), 1.0)
        nb = min(bt * lum * 2.0 * blend + lum * (1 - blend), 1.0)
        return nr, ng, nb

    def recolor_k(k: list) -> list:
        """Статичный цвет k = [r, g, b] или [r, g, b, a]."""
        if len(k) < 3 or not all(isinstance(v, (int, float)) for v in k[:3]):
            return k
        nr, ng, nb = tint(float(k[0]), float(k[1]), float(k[2]))
        return [nr, ng, nb] + ([float(k[3])] if len(k) >= 4 else [])

    def recolor_color_prop(c: dict):
        """Lottie color property {a:0/1, k:[...]}."""
        if not isinstance(c, dict):
            return
        if c.get("a", 0) == 0:
            if isinstance(c.get("k"), list):
                c["k"] = recolor_k(c["k"])
        else:
            for kf in (c.get("k") or []):
                if isinstance(kf, dict):
                    if isinstance(kf.get("s"), list):
                        kf["s"] = recolor_k(kf["s"])
                    if isinstance(kf.get("e"), list):
                        kf["e"] = recolor_k(kf["e"])

    def recolor_gradient(g_obj: dict):
        """
        Gradient property {p: N, k: {a:, k:[pos,r,g,b, pos,r,g,b, ..., pos,a, ...]}}
        Первые N*4 элементов — цветовые стопы, остальные — альфа-стопы.
        """
        if not isinstance(g_obj, dict):
            return
        num_stops = g_obj.get("p", 0)
        kprop = g_obj.get("k")
        if not isinstance(kprop, dict) or num_stops <= 0:
            return

        def recolor_flat(arr: list) -> list:
            arr = list(arr)
            for i in range(num_stops):
                base = i * 4
                if base + 3 >= len(arr):
                    break
                nr, ng, nb = tint(float(arr[base + 1]), float(arr[base + 2]), float(arr[base + 3]))
                arr[base + 1], arr[base + 2], arr[base + 3] = nr, ng, nb
            return arr

        if kprop.get("a", 0) == 0:
            if isinstance(kprop.get("k"), list):
                kprop["k"] = recolor_flat(kprop["k"])
        else:
            for kf in (kprop.get("k") or []):
                if isinstance(kf, dict):
                    if isinstance(kf.get("s"), list):
                        kf["s"] = recolor_flat(kf["s"])
                    if isinstance(kf.get("e"), list):
                        kf["e"] = recolor_flat(kf["e"])

    def walk(obj):
        if isinstance(obj, dict):
            ty = obj.get("ty")
            if ty in ("fl", "st") and "c" in obj:
                recolor_color_prop(obj["c"])
            elif ty in ("gf", "gs") and "g" in obj:
                recolor_gradient(obj["g"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    modified = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return gzip.compress(modified, compresslevel=9)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _place_on_canvas(
    sticker: Image.Image,
    bg_rgb: tuple[int, int, int] | None,
    canvas_wh: tuple[int, int],
) -> Image.Image:
    """
    Масштабирует стикер (RGBA) чтобы вписать в canvas, центрирует.
    Возвращает RGB-изображение (с фоном) или RGBA (прозрачный фон).
    """
    cw, ch = canvas_wh
    sw, sh = sticker.size

    scale = min(cw / sw, ch / sh)
    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))
    sticker_rs = sticker.resize((nw, nh), Image.LANCZOS)

    x = (cw - nw) // 2
    y = (ch - nh) // 2

    if bg_rgb is not None:
        canvas = Image.new("RGB", (cw, ch), bg_rgb)
        canvas.paste(sticker_rs, (x, y), mask=sticker_rs.split()[3])
    else:
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        canvas.paste(sticker_rs, (x, y), mask=sticker_rs.split()[3])

    return canvas


# ── Добавление фона к статичному стикеру ─────────────────────────────────────
def _add_background_sync(
    img_bytes: bytes,
    bg_key: str,
    canvas_wh: tuple[int, int] | None = None,
) -> bytes:
    """
    PNG/WebP стикер → PNG с залитым фоном.
    canvas_wh=None  → оригинальный размер (режим фото)
    canvas_wh=(w,h) → стикер вписывается в canvas с соотношением сторон
    """
    bg_rgb = CONVERT_BG_COLORS.get(bg_key)
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception:
        return img_bytes

    if canvas_wh is not None:
        result = _place_on_canvas(img, bg_rgb, canvas_wh)
        out = io.BytesIO()
        result.save(out, format="PNG")
        return out.getvalue()

    # Оригинальный размер
    if bg_rgb is None:
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    bg = Image.new("RGB", img.size, bg_rgb)
    bg.paste(img, mask=img.split()[3])
    out = io.BytesIO()
    bg.save(out, format="PNG")
    return out.getvalue()


# ── TGS → фото (первый кадр) или GIF ─────────────────────────────────────────
def _tgs_to_media_sync(
    tgs_bytes: bytes,
    bg_key: str,
    as_gif: bool,
    canvas_wh: tuple[int, int] | None = None,
) -> bytes:
    """
    Рендерит TGS анимацию через rlottie-python.
    as_gif=False   → PNG первого кадра
    as_gif=True    → GIF со всеми кадрами
    canvas_wh=None → оригинальный размер стикера (512×512)
    canvas_wh=(w,h)→ стикер вписывается в canvas (16:9, 9:16, 1:1 с отступами)
    """
    if not _HAS_RLOTTIE:
        raise RuntimeError(
            "Для анимированных стикеров требуется rlottie-python.\n"
            "Установи: pip install rlottie-python"
        )

    bg_rgb = CONVERT_BG_COLORS.get(bg_key)

    with tempfile.TemporaryDirectory() as tmpdir:
        tgs_path = os.path.join(tmpdir, "sticker.tgs")
        with open(tgs_path, "wb") as f:
            f.write(tgs_bytes)

        anim = _LottieAnim.from_tgs(tgs_path)
        total = anim.lottie_animation_get_totalframe()
        fps = anim.lottie_animation_get_framerate()
        duration_ms = max(20, int(1000 / fps)) if fps > 0 else 33

        def _process_frame(frame: Image.Image) -> Image.Image:
            if canvas_wh is not None:
                return _place_on_canvas(frame, bg_rgb, canvas_wh)
            # Оригинальный размер
            if bg_rgb is not None:
                bg = Image.new("RGB", frame.size, bg_rgb)
                bg.paste(frame, mask=frame.split()[3])
                return bg
            return frame.convert("RGBA")

        if not as_gif:
            frame = anim.render_pillow_frame(frame_num=0)
            result = _process_frame(frame)
            out = io.BytesIO()
            result.save(out, format="PNG")
            return out.getvalue()

        # Все кадры → GIF
        frames = [_process_frame(anim.render_pillow_frame(frame_num=i)) for i in range(total)]

        if not frames:
            raise RuntimeError("Нет кадров в анимации")

        out = io.BytesIO()
        frames[0].save(
            out, format="GIF",
            append_images=frames[1:],
            save_all=True,
            loop=0,
            duration=duration_ms,
        )
        return out.getvalue()


# ── SVG-конвертация ───────────────────────────────────────────────────────────
def _static_to_svg(img_bytes: bytes) -> str:
    """Конвертирует WebP/PNG в SVG с встроенным base64-изображением."""
    import base64

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception:
        return _error_svg("Не удалось открыть изображение")

    w, h = img.size
    out = io.BytesIO()
    img.save(out, format="PNG")
    b64 = base64.b64encode(out.getvalue()).decode()

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
        f'  <image href="data:image/png;base64,{b64}" '
        f'xlink:href="data:image/png;base64,{b64}" '
        f'x="0" y="0" width="{w}" height="{h}"/>\n'
        f'</svg>'
    )


def _tgs_to_svg_preview(tgs_bytes: bytes) -> str:
    """
    Для анимированных TGS стикеров:
    Распаковываем Lottie JSON и генерируем SVG-превью первого кадра.
    """
    try:
        lottie_json = gzip.decompress(tgs_bytes).decode("utf-8")
        data = json.loads(lottie_json)
        w = data.get("w", 512)
        h = data.get("h", 512)
        import base64
        lottie_b64 = base64.b64encode(lottie_json.encode()).decode()
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'data-lottie="{lottie_b64}" data-type="animated">\n'
            f'  <rect width="{w}" height="{h}" fill="none"/>\n'
            f'  <!-- Animated TGS sticker — requires lottie-player -->\n'
            f'  <text x="50%" y="50%" text-anchor="middle" '
            f'fill="#888" font-family="sans-serif" font-size="24">▶ Animated</text>\n'
            f'</svg>'
        )
    except Exception as e:
        return _error_svg(f"TGS parse error: {e}")


def _error_svg(msg: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        f'<rect width="200" height="200" rx="20" fill="#1a1a1a"/>'
        f'<text x="100" y="100" text-anchor="middle" fill="#ff4444" '
        f'font-family="sans-serif" font-size="12">{msg}</text>'
        '</svg>'
    )


# ── Public API ────────────────────────────────────────────────────────────────
class StickerProcessor:
    async def recolor(self, img_bytes: bytes, hex_color: str) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, _recolor_sync, img_bytes, hex_color)

    async def recolor_tgs(self, tgs_bytes: bytes, hex_color: str) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, _recolor_lottie_sync, tgs_bytes, hex_color)

    async def to_svg(self, img_bytes: bytes, is_animated: bool = False) -> str:
        loop = asyncio.get_event_loop()
        if is_animated:
            return await loop.run_in_executor(_pool, _tgs_to_svg_preview, img_bytes)
        else:
            return await loop.run_in_executor(_pool, _static_to_svg, img_bytes)

    async def add_background(
        self,
        img_bytes: bytes,
        bg_key: str,
        canvas_wh: tuple[int, int] | None = None,
    ) -> bytes:
        """Статичный стикер → PNG с выбранным фоном [и соотношением сторон]."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, _add_background_sync, img_bytes, bg_key, canvas_wh)

    async def tgs_to_media(
        self,
        tgs_bytes: bytes,
        bg_key: str,
        as_gif: bool,
        canvas_wh: tuple[int, int] | None = None,
    ) -> bytes:
        """TGS анимация → PNG первого кадра (as_gif=False) или GIF (as_gif=True) [с соотношением сторон]."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, _tgs_to_media_sync, tgs_bytes, bg_key, as_gif, canvas_wh)

    @staticmethod
    def rlottie_available() -> bool:
        return _HAS_RLOTTIE
