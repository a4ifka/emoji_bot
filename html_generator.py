"""
HTMLGenerator — старый красивый стиль (Syne + DM Mono).
Генерирует два вида отчётов:
  • id_report()  — file_id, file_unique_id, emoji, превью
  • svg_report() — стикеры в SVG с кнопками скачивания
"""

import base64
import gzip
import json
from datetime import datetime
from io import BytesIO

from PIL import Image


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _to_png_src(img_bytes: bytes) -> str:
    if not img_bytes:
        return ""
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        out = BytesIO()
        img.save(out, format="PNG")
        b64 = base64.b64encode(out.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def _to_lottie_b64(tgs_bytes: bytes) -> str:
    """Распаковывает TGS → base64(Lottie JSON) для lottie-player."""
    try:
        return base64.b64encode(gzip.decompress(tgs_bytes)).decode()
    except Exception:
        return ""


def _lottie_player(b64: str, size: int = 140) -> str:
    if not b64:
        return '<span style="font-size:40px">🎞</span>'
    return (
        f'<lottie-player src="data:application/json;base64,{b64}" '
        f'background="transparent" speed="1" '
        f'style="width:{size}px;height:{size}px;display:block;margin:auto" '
        f'autoplay loop></lottie-player>'
    )


def _lighten(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r2 = min(255, int(r * 0.6 + b * 0.4 + 40))
        g2 = min(255, int(g * 0.6 + r * 0.4 + 20))
        b2 = min(255, int(b * 0.7 + g * 0.3 + 60))
        return f"#{r2:02X}{g2:02X}{b2:02X}"
    except Exception:
        return "#9B59B6"


# ─── CSS (старый стиль Syne + DM Mono) ───────────────────────────────────────
def _build_css(accent: str, accent2: str) -> str:
    return f"""\
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d0d0f;
    --surface: #161618;
    --surface2: #1e1e22;
    --border: #2a2a30;
    --accent: {accent};
    --accent2: {accent2};
    --text: #f0f0f4;
    --muted: #7a7a8a;
    --card-hover: #222228;
  }}

  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
  }}

  /* noise */
  body::before {{
    content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
    background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
  }}

  /* glow orbs */
  .glow-orb {{ position:fixed; border-radius:50%; filter:blur(120px); opacity:0.12; pointer-events:none; z-index:0; }}
  .glow-orb-1 {{ width:600px; height:600px; background:var(--accent); top:-200px; left:-200px; animation:drift1 18s ease-in-out infinite alternate; }}
  .glow-orb-2 {{ width:400px; height:400px; background:var(--accent2); bottom:-100px; right:-100px; animation:drift2 14s ease-in-out infinite alternate; }}
  @keyframes drift1 {{ to {{ transform:translate(120px,80px); }} }}
  @keyframes drift2 {{ to {{ transform:translate(-80px,-60px); }} }}

  /* header */
  header {{
    position:relative; z-index:1;
    padding:60px 40px 40px;
    border-bottom:1px solid var(--border);
    background:linear-gradient(180deg,rgba(255,255,255,.02) 0%,transparent 100%);
  }}
  .header-inner {{
    max-width:1400px; margin:0 auto;
    display:flex; align-items:flex-end;
    justify-content:space-between; gap:24px; flex-wrap:wrap;
  }}
  .badge {{
    display:inline-flex; align-items:center; gap:6px;
    font-family:'DM Mono',monospace; font-size:11px; font-weight:500;
    letter-spacing:.1em; text-transform:uppercase;
    color:var(--accent);
    background:color-mix(in srgb,var(--accent) 12%,transparent);
    border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);
    padding:5px 12px; border-radius:100px; margin-bottom:16px;
  }}
  .badge::before {{ content:'●'; font-size:8px; }}

  h1 {{ font-size:clamp(28px,5vw,52px); font-weight:800; line-height:1.1; letter-spacing:-.03em; }}
  h1 span {{
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
  }}

  .meta-pills {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; }}
  .pill {{
    font-family:'DM Mono',monospace; font-size:12px; color:var(--muted);
    background:var(--surface); border:1px solid var(--border);
    padding:6px 14px; border-radius:100px;
  }}
  .pill strong {{ color:var(--text); }}
  .color-swatch {{
    width:14px; height:14px; border-radius:50%; display:inline-block;
    vertical-align:middle; margin-right:4px; box-shadow:0 0 8px var(--accent);
  }}

  .header-stats {{ text-align:right; }}
  .big-num {{
    font-size:64px; font-weight:800; line-height:1;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
  }}
  .big-num-label {{
    font-size:12px; color:var(--muted); letter-spacing:.1em;
    text-transform:uppercase; margin-top:4px; font-family:'DM Mono',monospace;
  }}

  /* toolbar */
  .toolbar {{
    position:sticky; top:0; z-index:10;
    background:rgba(13,13,15,.85); backdrop-filter:blur(20px);
    border-bottom:1px solid var(--border); padding:12px 40px;
  }}
  .toolbar-inner {{
    max-width:1400px; margin:0 auto;
    display:flex; align-items:center; justify-content:space-between;
    gap:16px; flex-wrap:wrap;
  }}
  .search-box {{
    display:flex; align-items:center; gap:10px;
    background:var(--surface); border:1px solid var(--border);
    border-radius:10px; padding:8px 16px; flex:1; max-width:360px;
    transition:border-color .2s;
  }}
  .search-box:focus-within {{ border-color:var(--accent); }}
  .search-box input {{
    background:none; border:none; outline:none;
    color:var(--text); font-family:'DM Mono',monospace; font-size:13px; width:100%;
  }}
  .search-box input::placeholder {{ color:var(--muted); }}

  .view-btns {{
    display:flex; gap:4px;
    background:var(--surface); border:1px solid var(--border);
    border-radius:10px; padding:3px;
  }}
  .view-btn {{
    background:none; border:none; color:var(--muted); cursor:pointer;
    padding:6px 12px; border-radius:7px; font-size:16px; transition:all .2s;
  }}
  .view-btn.active {{ background:var(--surface2); color:var(--text); }}

  .export-btn {{
    font-family:'DM Mono',monospace; font-size:12px; cursor:pointer;
    padding:8px 16px; border-radius:10px;
    border:1px solid var(--border); background:var(--surface); color:var(--text);
    transition:all .2s;
  }}
  .export-btn:hover {{ border-color:var(--accent); color:var(--accent); }}

  /* main */
  main {{ position:relative; z-index:1; max-width:1400px; margin:0 auto; padding:40px; }}

  /* grid */
  .sticker-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:16px; }}
  .sticker-grid.list-view {{ grid-template-columns:1fr; gap:8px; }}

  /* card */
  .sticker-card {{
    background:var(--surface); border:1px solid var(--border);
    border-radius:16px; overflow:hidden;
    transition:all .25s cubic-bezier(.4,0,.2,1);
    animation:fadeUp .4s ease both;
  }}
  .sticker-card:hover {{
    background:var(--card-hover);
    border-color:color-mix(in srgb,var(--accent) 40%,transparent);
    transform:translateY(-3px);
    box-shadow:0 12px 40px rgba(0,0,0,.4),0 0 0 1px color-mix(in srgb,var(--accent) 20%,transparent);
  }}
  @keyframes fadeUp {{ from {{ opacity:0; transform:translateY(20px); }} to {{ opacity:1; transform:translateY(0); }} }}

  .card-img {{
    background:var(--surface2); display:flex; align-items:center;
    justify-content:center; padding:20px; aspect-ratio:1; position:relative;
  }}
  .card-img img, .card-img .svg-wrap {{
    width:100%; max-width:140px; height:auto; object-fit:contain;
    filter:drop-shadow(0 4px 12px rgba(0,0,0,.5));
    transition:transform .3s ease; display:block; margin:auto;
  }}
  .sticker-card:hover .card-img img,
  .sticker-card:hover .card-img .svg-wrap {{ transform:scale(1.08); }}

  .card-num {{
    position:absolute; top:8px; left:8px;
    font-family:'DM Mono',monospace; font-size:10px; color:var(--muted);
    background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:2px 7px;
  }}
  .card-emoji {{ position:absolute; top:8px; right:8px; font-size:18px; }}

  .card-info {{ padding:14px; border-top:1px solid var(--border); }}
  .code-row {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px; }}
  .code-row:last-child {{ margin-bottom:0; }}
  .code-label {{ font-family:'DM Mono',monospace; font-size:9px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); min-width:28px; }}
  .code-val {{
    font-family:'DM Mono',monospace; font-size:10px; color:var(--text);
    background:var(--bg); border:1px solid var(--border); border-radius:6px;
    padding:3px 8px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    cursor:pointer; transition:border-color .2s;
  }}
  .code-val:hover {{ border-color:var(--accent); color:var(--accent); }}

  .copy-btn {{
    background:none; border:1px solid var(--border); color:var(--muted); cursor:pointer;
    padding:3px 8px; border-radius:6px; font-family:'DM Mono',monospace; font-size:10px;
    transition:all .2s; white-space:nowrap;
  }}
  .copy-btn:hover {{ border-color:var(--accent); color:var(--accent); background:color-mix(in srgb,var(--accent) 10%,transparent); }}
  .copy-btn.copied {{ border-color:#38A169; color:#38A169; }}

  .dl-btn {{
    display:flex; align-items:center; justify-content:center; gap:5px;
    font-family:'DM Mono',monospace; font-size:10px; color:var(--muted);
    background:var(--bg); border:1px solid var(--border); border-radius:6px;
    padding:5px; cursor:pointer; text-decoration:none;
    transition:all .2s; margin-top:6px; width:100%;
  }}
  .dl-btn:hover {{ border-color:var(--accent); color:var(--accent); background:color-mix(in srgb,var(--accent) 6%,transparent); }}

  /* list view */
  .list-view .sticker-card {{ display:flex; align-items:center; border-radius:12px; }}
  .list-view .card-img {{ width:80px; min-width:80px; height:80px; aspect-ratio:unset; padding:10px; }}
  .list-view .card-img img, .list-view .card-img .svg-wrap {{ max-width:56px; }}
  .list-view .card-num {{ display:none; }}
  .list-view .card-emoji {{ display:none; }}
  .list-view .card-info {{
    flex:1; display:flex; align-items:center; gap:12px; flex-wrap:wrap;
    border-top:none; border-left:1px solid var(--border); padding:12px 16px;
  }}
  .list-view .code-row {{ margin-bottom:0; flex:1; min-width:200px; }}
  .list-num {{ display:none; }}
  .list-view .list-num {{ display:block; font-family:'DM Mono',monospace; font-size:11px; color:var(--muted); min-width:28px; }}

  .color-bar {{ height:3px; background:linear-gradient(90deg,var(--accent),var(--accent2)); border-radius:0 0 3px 3px; }}

  /* toast */
  #toast {{
    position:fixed; bottom:32px; right:32px;
    background:var(--surface2); border:1px solid var(--accent); color:var(--text);
    padding:12px 20px; border-radius:12px;
    font-family:'DM Mono',monospace; font-size:13px;
    z-index:100; opacity:0; transform:translateY(20px); transition:all .3s; pointer-events:none;
  }}
  #toast.show {{ opacity:1; transform:translateY(0); }}

  /* footer */
  footer {{
    position:relative; z-index:1; text-align:center;
    padding:40px; border-top:1px solid var(--border);
    font-family:'DM Mono',monospace; font-size:12px; color:var(--muted);
  }}
  footer a {{ color:var(--accent); text-decoration:none; }}

  @media(max-width:600px) {{
    header, main {{ padding:24px 16px; }}
    .toolbar {{ padding:12px 16px; }}
    .sticker-grid {{ grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }}
    .header-stats {{ display:none; }}
  }}
</style>"""


# ─── JS ───────────────────────────────────────────────────────────────────────
def _build_js(all_ids: list) -> str:
    ids_json = json.dumps(all_ids)
    return f"""\
<script>
const _ids = {ids_json};
function toast(m) {{
  const t = document.getElementById('toast');
  t.textContent = m; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}}
function _doCopy(text) {{
  if (navigator.clipboard && window.isSecureContext) {{
    return navigator.clipboard.writeText(text);
  }}
  /* Fallback: execCommand — работает в iOS file://, Telegram WebView */
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  var ok = false;
  try {{ ok = document.execCommand('copy'); }} catch(e) {{}}
  document.body.removeChild(ta);
  return ok ? Promise.resolve() : Promise.reject();
}}
function cp(text, btn) {{
  _doCopy(text).then(function() {{
    if (btn) {{
      var o = btn.textContent; btn.textContent = '✓'; btn.classList.add('copied');
      setTimeout(function() {{ btn.textContent = o; btn.classList.remove('copied'); }}, 1400);
    }}
    toast('Скопировано!');
  }}).catch(function() {{ toast('Не удалось скопировать'); }});
}}
function cpAll() {{
  _doCopy(_ids.join('\\n')).then(function() {{
    toast('Скопировано ' + _ids.length + ' ID!');
  }}).catch(function() {{ toast('Не удалось скопировать'); }});
}}
function setView(v) {{
  const g = document.getElementById('grid');
  const gb = document.getElementById('btn-grid'), lb = document.getElementById('btn-list');
  if (v === 'list') {{
    g.classList.add('list-view'); lb.classList.add('active'); gb.classList.remove('active');
    localStorage.setItem('sv', 'list');
  }} else {{
    g.classList.remove('list-view'); gb.classList.add('active'); lb.classList.remove('active');
    localStorage.setItem('sv', 'grid');
  }}
}}
const _sv = localStorage.getItem('sv'); if (_sv) setView(_sv);
document.getElementById('search').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  document.querySelectorAll('.sticker-card').forEach(c =>
    c.style.display = (c.dataset.s || '').includes(q) ? '' : 'none'
  );
}});
document.querySelectorAll('.code-val[data-v]').forEach(el =>
  el.addEventListener('click', () => cp(el.dataset.v))
);
document.querySelectorAll('.sticker-card').forEach((c, i) =>
  c.style.animationDelay = (i * 0.03) + 's'
);
</script>"""


# ─── Page shell ───────────────────────────────────────────────────────────────
def _page(title, css, badge, heading, set_name, date, total,
          extra_pill, toolbar, cards, js, accent="") -> str:

    color_pill = (
        f'<div class="pill"><span class="color-swatch" style="background:{accent}"></span>'
        f'Цвет: <strong>{accent}</strong></div>'
        if accent else extra_pill
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{css}
</head>
<body>
<div class="glow-orb glow-orb-1"></div>
<div class="glow-orb glow-orb-2"></div>
<div id="toast"></div>

<header>
  <div class="header-inner">
    <div>
      <div class="badge">{badge}</div>
      <h1><span>{heading}</span></h1>
      <div class="meta-pills">
        <div class="pill">📦 <strong>@{set_name}</strong></div>
        <div class="pill">📅 <strong>{date}</strong></div>
        {color_pill}
      </div>
    </div>
    <div class="header-stats">
      <div class="big-num">{total}</div>
      <div class="big-num-label">стикеров</div>
    </div>
  </div>
</header>

{toolbar}

<main>
  <div class="sticker-grid" id="grid">
{cards}
  </div>
</main>

<footer>
  Сгенерировано <strong>Sticker Pack Bot</strong>&nbsp;·&nbsp;{date}&nbsp;·&nbsp;
  <a href="https://t.me/addstickers/{set_name}" target="_blank">@{set_name}</a>
</footer>

{js}
<script src="https://unpkg.com/@lottiefiles/lottie-player@2.0.8/dist/lottie-player.js"></script>
</body>
</html>"""


_TOOLBAR = """\
<div class="toolbar">
  <div class="toolbar-inner">
    <div class="search-box">
      <span style="color:var(--muted);font-size:16px">⌕</span>
      <input id="search" type="text" placeholder="Поиск по emoji или ID…">
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <div class="view-btns">
        <button class="view-btn active" id="btn-grid" onclick="setView('grid')" title="Сетка">⊞</button>
        <button class="view-btn" id="btn-list" onclick="setView('list')" title="Список">☰</button>
      </div>
      <button class="export-btn" onclick="cpAll()">⬇ Все ID</button>
    </div>
  </div>
</div>"""


# ─── Card builders ────────────────────────────────────────────────────────────
def _id_card(s: dict) -> str:
    fid   = s["file_id"]
    uid   = s["file_unique_id"]
    emoji = s.get("emoji", "🎭")
    idx   = s["index"]
    is_anim = s.get("is_animated", False)
    is_vid  = s.get("is_video", False)
    anim = " 🎞" if is_anim else (" 📹" if is_vid else "")

    if is_anim:
        img_tag = _lottie_player(_to_lottie_b64(s.get("img_bytes", b"")))
    elif is_vid:
        img_tag = '<span style="font-size:32px;color:var(--muted)">📹</span>'
    else:
        img_src = _to_png_src(s.get("img_bytes", b""))
        img_tag = (
            f'<img src="{img_src}" loading="lazy" alt=""/>'
            if img_src else '<span style="font-size:32px;color:var(--muted)">📦</span>'
        )
    return f"""\
    <div class="sticker-card" data-s="{emoji} {fid} {uid}">
      <div class="card-img">
        <span class="card-num">#{idx}</span>
        <span class="card-emoji">{emoji}</span>
        {img_tag}
      </div>
      <div class="card-info">
        <span class="list-num">#{idx}</span>
        <div class="code-row">
          <span class="code-label">ID</span>
          <span class="code-val" data-v="{fid}" title="{fid}">{fid[:22]}…</span>
          <button class="copy-btn" onclick="cp('{fid}',this)">copy</button>
        </div>
        <div class="code-row">
          <span class="code-label">UID</span>
          <span class="code-val" data-v="{uid}" title="{uid}">{uid}</span>
          <button class="copy-btn" onclick="cp('{uid}',this)">copy</button>
        </div>
        <div class="code-row">
          <span class="code-label">EMJ</span>
          <span class="code-val">{emoji}{anim}</span>
        </div>
      </div>
      <div class="color-bar"></div>
    </div>"""


def _svg_card(s: dict) -> str:
    svg_content = s.get("svg_content", "")
    uid   = s["file_unique_id"]
    fid   = s["file_id"]
    emoji = s.get("emoji", "🎭")
    idx   = s["index"]
    is_anim = s.get("is_animated", False)

    # Download link
    if svg_content and not is_anim:
        b64 = base64.b64encode(svg_content.encode()).decode()
        dl_tag = f'<a class="dl-btn" href="data:image/svg+xml;base64,{b64}" download="sticker_{idx}.svg">⬇ Скачать SVG</a>'
    else:
        dl_tag = ""

    # Display
    # Для анимированных — lottie-player; для статичных — PNG <img>
    # (inline SVG с <image href="data:..."> ненадёжно рендерится на iOS Safari)
    if is_anim:
        display = _lottie_player(_to_lottie_b64(s.get("img_bytes", b"")))
    else:
        img_src = _to_png_src(s.get("img_bytes", b""))
        display = (
            f'<img src="{img_src}" '
            f'style="max-width:140px;width:100%;height:auto;display:block;margin:auto" '
            f'loading="lazy" alt=""/>'
            if img_src else '<span style="font-size:32px;color:var(--muted)">📦</span>'
        )

    anim_lbl = (
        '<span style="font-family:\'DM Mono\',monospace;font-size:9px;'
        'color:var(--accent);letter-spacing:.08em">ANIM</span>'
        if is_anim else ""
    )

    return f"""\
    <div class="sticker-card" data-s="{emoji} {uid} {fid}">
      <div class="card-img">
        <span class="card-num">#{idx}</span>
        <span class="card-emoji">{emoji}</span>
        {display}
      </div>
      <div class="card-info">
        <span class="list-num">#{idx}</span>
        <div class="code-row">
          <span class="code-label">UID</span>
          <span class="code-val" data-v="{uid}" title="{uid}">{uid}</span>
          <button class="copy-btn" onclick="cp('{uid}',this)">copy</button>
        </div>
        <div class="code-row">
          <span class="code-label">ID</span>
          <span class="code-val" data-v="{fid}" title="{fid}">{fid[:22]}…</span>
          <button class="copy-btn" onclick="cp('{fid}',this)">copy</button>
        </div>
        <div class="code-row">
          <span class="code-label">EMJ</span>
          <span class="code-val">{emoji} {anim_lbl}</span>
        </div>
        {dl_tag}
      </div>
      <div class="color-bar"></div>
    </div>"""


# ─── Public API ───────────────────────────────────────────────────────────────
class HTMLGenerator:

    def id_report(self, set_name: str, title: str, stickers: list) -> str:
        date    = datetime.now().strftime("%d.%m.%Y %H:%M")
        all_ids = [s["file_id"] for s in stickers]
        cards   = "\n".join(_id_card(s) for s in stickers)
        return _page(
            title    = f"{title} — IDs",
            css      = _build_css("#6C63FF", "#FF6584"),
            badge    = "STICKER IDs",
            heading  = title,
            set_name = set_name,
            date     = date,
            total    = len(stickers),
            extra_pill = "",
            toolbar  = _TOOLBAR,
            cards    = cards,
            js       = _build_js(all_ids),
        )

    def svg_report(self, set_name: str, title: str, stickers: list) -> str:
        date    = datetime.now().strftime("%d.%m.%Y %H:%M")
        all_ids = [s["file_unique_id"] for s in stickers]
        cards   = "\n".join(_svg_card(s) for s in stickers)
        svg_pill = '<div class="pill">〈/〉 <strong>SVG формат</strong></div>'
        return _page(
            title    = f"{title} — SVG",
            css      = _build_css("#FF5733", "#FFB703"),
            badge    = "SVG EXPORT",
            heading  = title,
            set_name = set_name,
            date     = date,
            total    = len(stickers),
            extra_pill = svg_pill,
            toolbar  = _TOOLBAR,
            cards    = cards,
            js       = _build_js(all_ids),
        )
