"""Draws the 144x144 lamp key in the same style as the page-2 icons
(rounded dark gradient tile, thin border, white glyph)."""
import base64
import io
import os

from PIL import Image, ImageDraw, ImageFilter

S = 4            # supersample factor
W = 144 * S


def _tile() -> Image.Image:
    """Key background. Default: fully transparent, like the page-2 transparent icon set.
    Set USE_TILE = True to use the dark page-2 tile (images/tile.png) instead."""
    if not USE_TILE:
        return Image.new("RGBA", (W, W), (0, 0, 0, 0))
    path = os.path.join(IMAGES, "tile.png")
    if os.path.exists(path):
        return Image.open(path).convert("RGBA").resize((W, W), Image.NEAREST)
    grad = Image.new("RGB", (1, 144))
    for y in range(144):
        t = y / 143
        c = tuple(int(a + (b - a) * t) for a, b in zip((44, 44, 50), (10, 10, 13)))
        grad.putpixel((0, y), c)
    grad = grad.resize((W, W))
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, W - 1), radius=14 * S, fill=255)
    img.paste(grad, (0, 0), mask)
    ImageDraw.Draw(img).rounded_rectangle((2 * S, 2 * S, W - 2 * S, W - 2 * S), radius=12 * S,
                                          outline=(78, 78, 86, 255), width=S)
    return img


IMAGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
USE_TILE = False      # transparent background, matching page2-icons-transparent
GLYPH_H = 98          # glyph height on the 144 key (rays included) - same box as the transparent set
GLYPH_TOP = 23
BOLDEN = 7            # thicken strokes (px at 4x) to match the heavier page-2 glyphs
_cache: dict = {}


def _drawn(part: str) -> Image.Image:
    """Built-in bulb/rays glyph, used when images/<part>-mask.png isn't provided."""
    m = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(m)
    s = lambda *v: [x * S for x in v]
    if part == "bulb":
        d.ellipse(s(46, 36, 98, 88), outline=255, width=7 * S)                    # glass
        d.polygon(s(55, 80, 89, 80, 84, 95, 60, 95), fill=0)                      # open the neck
        d.line(s(57, 80, 61, 95), fill=255, width=7 * S)
        d.line(s(87, 80, 83, 95), fill=255, width=7 * S)
        for y in (100, 108):                                                      # screw base
            d.rounded_rectangle(s(59, y, 85, y + 5), radius=2 * S, fill=255)
        d.pieslice(s(64, 108, 80, 122), 0, 180, fill=255)
    else:
        for x0, y0, x1, y1 in ((72, 23, 72, 30), (40, 37, 45, 42), (104, 37, 99, 42),
                               (27, 62, 34, 62), (117, 62, 110, 62)):
            d.line(s(x0, y0, x1, y1), fill=255, width=6 * S)
    return m


def _glyph(part: str) -> Image.Image:
    """'bulb' or 'rays' as a full-key L mask, positioned the same for every state.
    Uses images/bulb-mask.png and images/rays-mask.png if present (your own artwork),
    otherwise the built-in drawn bulb."""
    if part not in _cache:
        path = os.path.join(IMAGES, f"{part}-mask.png")
        if not os.path.exists(path):
            _cache[part] = _drawn(part)
            return _cache[part]
        src = Image.open(path).convert("L")
        h = GLYPH_H * S
        w = round(src.width * h / src.height)
        m = Image.new("L", (W, W), 0)
        m.paste(src.resize((w, h), Image.LANCZOS), ((W - w) // 2, GLYPH_TOP * S))
        _cache[part] = m.filter(ImageFilter.MaxFilter(BOLDEN))
    return _cache[part]


def render(state: str, rgb=(255, 196, 120), brightness: int | None = None) -> str:
    """state: 'on' | 'off' | 'busy' | 'offline'.  Returns a data: URL PNG."""
    img = _tile()
    bulb = _glyph("bulb")
    if state == "on":
        # soft glow inside the bulb in the lamp's current colour, stronger when brighter
        k = 0.45 + 0.55 * ((brightness or 100) / 100)
        glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        cy = GLYPH_TOP + GLYPH_H * 0.48
        ImageDraw.Draw(glow).ellipse((44 * S, (cy - 26) * S, 100 * S, (cy + 26) * S), fill=rgb + (int(170 * k),))
        glow = glow.filter(ImageFilter.GaussianBlur(10 * S))
        img = Image.alpha_composite(img, glow)
        img.paste((255, 255, 255, 255), (0, 0), bulb)
        img.paste((255, 255, 255, 255), (0, 0), _glyph("rays"))
    else:
        grey = {"off": (120, 120, 128), "busy": (170, 170, 178), "offline": (90, 90, 96)}[state]
        img.paste(grey + (255,), (0, 0), bulb)
        if state == "offline":   # small amber "!" badge
            d = ImageDraw.Draw(img)
            d.ellipse((104 * S, 14 * S, 128 * S, 38 * S), fill=(255, 159, 10, 255))
            d.rounded_rectangle((114.5 * S, 19 * S, 117.5 * S, 29 * S), radius=S, fill=(20, 20, 24, 255))
            d.ellipse((114.5 * S, 31 * S, 117.5 * S, 34 * S), fill=(20, 20, 24, 255))
        if state == "busy":      # three small dots
            d = ImageDraw.Draw(img)
            for i in range(3):
                x = (60 + i * 12) * S
                d.ellipse((x - 2 * S, 127 * S, x + 2 * S, 131 * S), fill=(170, 170, 178, 255))
    out = img.resize((144, 144), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def save_png(path: str, *args, **kw) -> None:
    data = render(*args, **kw).split(",", 1)[1]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
