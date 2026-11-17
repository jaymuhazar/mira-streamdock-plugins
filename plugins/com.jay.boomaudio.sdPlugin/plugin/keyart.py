"""Key art for the Boom audio key, in the page-2 *transparent* style:
white glyph, no tile, no border, glyph inside the 23,27 - 121,117 box of a 144x144 key."""
import base64
import io
import os

from PIL import Image, ImageDraw, ImageFont

S = 4
W = 144 * S
IMAGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
WHITE = (255, 255, 255, 255)
SHOW_LABEL = False    # True = small device name under the glyph


def _s(*v):
    return [x * S for x in v]


def _headset(d):
    d.arc(_s(30, 26, 114, 110), 180, 360, fill=WHITE, width=10 * S)          # head band
    d.rounded_rectangle(_s(25, 64, 48, 106), radius=9 * S, fill=WHITE)       # left cup
    d.rounded_rectangle(_s(96, 64, 119, 106), radius=9 * S, fill=WHITE)      # right cup
    d.line(_s(30, 68, 30, 70), fill=WHITE, width=10 * S)
    d.arc(_s(36, 74, 88, 120), 90, 160, fill=WHITE, width=6 * S)             # mic boom
    d.ellipse(_s(56, 110, 70, 122), fill=WHITE)                              # mic tip


def _monitor(d):
    d.rounded_rectangle(_s(42, 25, 102, 119), radius=11 * S, outline=WHITE, width=8 * S)  # cabinet
    d.ellipse(_s(62, 37, 82, 57), fill=WHITE)                                # tweeter
    d.ellipse(_s(50, 66, 94, 110), outline=WHITE, width=7 * S)               # woofer ring
    d.ellipse(_s(64, 80, 80, 96), fill=WHITE)                                # woofer cap


def _speakers(d):
    """Placeholder: a pair of small desktop speakers."""
    for x0 in (26, 76):
        d.rounded_rectangle(_s(x0, 38, x0 + 42, 112), radius=8 * S, outline=WHITE, width=7 * S)
        d.ellipse(_s(x0 + 14, 50, x0 + 28, 64), fill=WHITE)
        d.ellipse(_s(x0 + 8, 74, x0 + 34, 100), outline=WHITE, width=6 * S)


GLYPHS = {"headset": _headset, "monitor": _monitor, "speakers": _speakers}


def _custom(kind):
    """A PNG in images/glyph-<kind>.png (white on transparent, 144x144) overrides the drawn glyph."""
    p = os.path.join(IMAGES, f"glyph-{kind}.png")
    if os.path.exists(p):
        return Image.open(p).convert("RGBA").resize((W, W), Image.LANCZOS)
    return None


def render(kind: str, state: str = "on", label: str = "") -> str:
    """kind: headset | monitor | speakers.  state: on | busy | offline."""
    img = _custom(kind)
    if img is None:
        img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        GLYPHS.get(kind, _speakers)(ImageDraw.Draw(img))
    if state in ("busy", "offline"):
        grey = (170, 170, 178) if state == "busy" else (90, 90, 96)
        a = img.getchannel("A")
        img = Image.new("RGBA", (W, W), grey + (0,))
        img.putalpha(a)
    d = ImageDraw.Draw(img)
    if state == "busy":
        for i in range(3):
            x = (60 + i * 12) * S
            d.ellipse((x - 2 * S, 128 * S, x + 2 * S, 132 * S), fill=(170, 170, 178, 255))
    if state == "offline":
        d.ellipse(_s(104, 14, 128, 38), fill=(255, 159, 10, 255))
        d.rounded_rectangle(_s(114.5, 19, 117.5, 29), radius=S, fill=(20, 20, 24, 255))
        d.ellipse(_s(114.5, 31, 117.5, 34), fill=(20, 20, 24, 255))
    out = img.resize((144, 144), Image.LANCZOS)
    if SHOW_LABEL and label and state == "on":
        dd = ImageDraw.Draw(out)
        try:
            f = ImageFont.truetype("segoeuib.ttf", 13)
        except OSError:
            f = ImageFont.load_default()
        tw = dd.textlength(label, font=f)
        dd.text(((144 - tw) / 2, 124), label, font=f, fill=(200, 200, 206, 255))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
