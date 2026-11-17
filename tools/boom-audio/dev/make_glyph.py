"""Turn white-on-black artwork into a white-on-transparent 144x144 key glyph,
fitted (keeping proportions) into the page-2 transparent set's box (23,27)-(121,117).

  python make_glyph.py <source.jpg|png> <out.png>
"""
import sys
from PIL import Image

src_path, out_path = sys.argv[1], sys.argv[2]
from collections import deque

MIN_SPECK = 150   # ink blobs smaller than this many source pixels are treated as stray marks

src = Image.open(src_path).convert("L")
# white ink -> opacity; values below 40 (JPEG noise on black) become fully transparent
a = src.point(lambda v: 0 if v < 40 else min(255, int((v - 40) * 255 / (215 - 40))))

# drop tiny isolated specks (e.g. a mouse cursor caught in a screenshot)
W, H = a.size
px = a.load()
seen = bytearray(W * H)
removed = []
for y in range(H):
    for x in range(W):
        if px[x, y] > 60 and not seen[y * W + x]:
            q = deque([(x, y)]); seen[y * W + x] = 1; blob = []
            while q:
                cx, cy = q.popleft(); blob.append((cx, cy))
                for nx in range(cx - 1, cx + 2):
                    for ny in range(cy - 1, cy + 2):
                        if 0 <= nx < W and 0 <= ny < H and not seen[ny * W + nx] and px[nx, ny] > 20:
                            seen[ny * W + nx] = 1; q.append((nx, ny))
            if len(blob) < MIN_SPECK:
                removed.append((len(blob), blob[0]))
                for bx, by in blob:
                    px[bx, by] = 0
if removed:
    print("removed stray specks (size, at):", removed)

bb = a.point(lambda v: 255 if v > 60 else 0).getbbox()
g = a.crop(bb)
scale = min(98 / g.width, 90 / g.height)
w, h = round(g.width * scale), round(g.height * scale)
g = g.resize((w, h), Image.LANCZOS)
alpha = Image.new("L", (144, 144), 0)
alpha.paste(g, (23 + (98 - w) // 2, 27 + (90 - h) // 2))
out = Image.new("RGBA", (144, 144), (255, 255, 255, 0))
out.putalpha(alpha)
out.save(out_path)
print(f"{src_path}: ink bbox {bb} -> glyph {w}x{h}, key bbox {alpha.getbbox()}")
