"""Five BookForge icon options, drawn at 1024 px and scaled down (Pillow + numpy)."""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 1024
OUT = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(7)


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def grad(size, c1, c2, angle=90):
    """Linear gradient image (RGBA) from c1 to c2; angle 90 = top->bottom."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle)
    t = (xx * math.cos(a) + yy * math.sin(a))
    t = (t - t.min()) / max(1e-6, (t.max() - t.min()))
    c1, c2 = np.array(hexrgb(c1), np.float32), np.array(hexrgb(c2), np.float32)
    arr = c1 + (c2 - c1) * t[..., None]
    out = np.dstack([arr, np.full((h, w), 255, np.float32)]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def radial(size, inner, outer, cx=0.5, cy=0.5, power=1.0):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx / w - cx) ** 2 + (yy / h - cy) ** 2)) / 0.7071
    t = np.clip(d, 0, 1) ** power
    c1, c2 = np.array(hexrgb(inner), np.float32), np.array(hexrgb(outer), np.float32)
    arr = c1 + (c2 - c1) * t[..., None]
    return Image.fromarray(np.dstack([arr, np.full((h, w), 255, np.float32)]).clip(0, 255).astype(np.uint8), "RGBA")


def texture(img, amount=10, scale=1.0, cloth=False):
    """Fine leather / cloth grain on an RGBA image."""
    w, h = img.size
    n = rng.normal(0, 1, (h // 2, w // 2)).astype(np.float32)
    n = np.array(Image.fromarray(((n * 40) + 128).clip(0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                 np.float32) - 128
    if cloth:
        yy, xx = np.mgrid[0:h, 0:w]
        n = n * 0.5 + 18 * (np.sin(xx * 0.9) * np.sin(yy * 0.9))
    arr = np.array(img, np.float32)
    arr[..., :3] += (n[..., None] / 128.0) * amount
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")


def mask_round(size, box, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, r, fill=255)
    return m


def paste_masked(base, fill, mask):
    base.alpha_composite(Image.composite(fill, Image.new("RGBA", base.size, (0, 0, 0, 0)), mask))


def drop_shadow(base, mask, offset=(0, 24), blur=34, opacity=110):
    sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
    m = ImageChops.offset(mask, *offset).filter(ImageFilter.GaussianBlur(blur))
    sh.putalpha(m.point(lambda v: v * opacity // 255))
    base.alpha_composite(sh)


def gold(size):
    return grad(size, "#FFF1B8", "#B8862B", 70)


def gilt_line(base, xy, width):
    """A gold line with a light top edge (embossed foil)."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.line(xy, fill=(120, 84, 22, 255), width=width + 4)
    d.line(xy, fill=(232, 192, 98, 255), width=width)
    d.line([(x, y - width / 3) for x, y in xy], fill=(255, 238, 170, 255), width=max(2, width // 3))
    base.alpha_composite(layer)


def gilt_shape(base, mask, glow=False):
    g = gold(base.size)
    edge = mask.filter(ImageFilter.GaussianBlur(3))
    dark = Image.new("RGBA", base.size, (110, 76, 18, 255))
    paste_masked(base, dark, ImageChops.offset(edge, 3, 4))
    paste_masked(base, g, mask)
    hi = ImageChops.subtract(mask, ImageChops.offset(mask, 0, 5)).filter(ImageFilter.GaussianBlur(1))
    paste_masked(base, Image.new("RGBA", base.size, (255, 248, 210, 255)), hi)


def anvil_mask(cx, cy, s):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    pts = [(-1.00, -0.30), (0.55, -0.30), (0.95, -0.42), (0.80, -0.12), (0.45, 0.02), (0.30, 0.10),
           (0.30, 0.32), (0.55, 0.50), (-0.55, 0.50), (-0.30, 0.32), (-0.30, 0.10), (-0.60, 0.02),
           (-0.95, -0.12)]
    d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=255)
    return m


def spark(base, cx, cy, r, color=(255, 236, 160)):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for a in range(0, 360, 45):
        rr = r if a % 90 == 0 else r * 0.45
        x, y = cx + rr * math.cos(math.radians(a)), cy + rr * math.sin(math.radians(a))
        d.line([(cx, cy), (x, y)], fill=color + (255,), width=max(2, int(r * 0.09)))
    d.ellipse((cx - r * 0.16, cy - r * 0.16, cx + r * 0.16, cy + r * 0.16), fill=(255, 255, 240, 255))
    glow = layer.filter(ImageFilter.GaussianBlur(r * 0.25))
    base.alpha_composite(glow)
    base.alpha_composite(layer)


# ------------------------------------------------------------------ a closed hard-cover book
def hardcover(cover_a, cover_b, spine_a, emblem, ribbon, cloth=False, frame=True):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    book = (196, 108, 836, 916)
    whole = mask_round((S, S), (book[0] - 26, book[1], book[2] + 34, book[3] + 10), 44)
    drop_shadow(img, whole, (14, 30), 40, 120)
    # page block (visible at fore-edge and bottom)
    pages = mask_round((S, S), (book[0] + 30, book[1] + 26, book[2] + 30, book[3] + 8), 26)
    pg = grad((S, S), "#FFFDF6", "#E6DCC6", 0)
    d = ImageDraw.Draw(pg)
    for i in range(0, 60, 5):
        d.line([(book[2] + 4 + i * 0.4, book[1] + 40), (book[2] + 4 + i * 0.4, book[3])], fill=(205, 194, 170, 255),
               width=1)
    paste_masked(img, pg, pages)
    # cover board
    cov = grad((S, S), cover_a, cover_b, 100)
    cov = texture(cov, 16 if not cloth else 9, cloth=cloth)
    cm = mask_round((S, S), book, 38)
    paste_masked(img, cov, cm)
    # spine
    sp = grad((S, S), spine_a, cover_b, 0)
    sm = mask_round((S, S), (book[0] - 26, book[1], book[0] + 74, book[3]), 40)
    paste_masked(img, texture(sp, 14, cloth=cloth), sm)
    shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle((book[0] + 70, book[1], book[0] + 92, book[3]), fill=(0, 0, 0, 70))
    img.alpha_composite(shade.filter(ImageFilter.GaussianBlur(8)))
    for y in (book[1] + 120, book[1] + 160, book[3] - 160, book[3] - 120):          # raised bands
        gilt_line(img, [(book[0] - 14, y), (book[0] + 62, y)], 9)
    # top-left sheen
    sheen = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sheen).ellipse((book[0] - 200, book[1] - 320, book[2] - 60, book[1] + 360), fill=90)
    sheen = ImageChops.multiply(sheen.filter(ImageFilter.GaussianBlur(60)), cm)
    paste_masked(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), sheen.point(lambda v: v // 2))
    if frame:
        x0, y0, x1, y1 = book[0] + 118, book[1] + 64, book[2] - 54, book[3] - 64
        gilt_line(img, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], 8)
        gilt_line(img, [(x0 + 22, y0 + 22), (x1 - 22, y0 + 22), (x1 - 22, y1 - 22), (x0 + 22, y1 - 22),
                        (x0 + 22, y0 + 22)], 4)
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):                    # corner diamonds
            m = Image.new("L", (S, S), 0)
            ImageDraw.Draw(m).polygon([(cx, cy - 26), (cx + 26, cy), (cx, cy + 26), (cx - 26, cy)], fill=255)
            gilt_shape(img, m)
    emblem(img, (book[0] + book[2]) // 2 + 30, (book[1] + book[3]) // 2)
    # ribbon bookmark
    rx = book[2] - 190
    rb = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rb).polygon([(rx, book[3] - 12), (rx + 54, book[3] - 12), (rx + 54, book[3] + 92),
                                (rx + 27, book[3] + 66), (rx, book[3] + 92)], fill=hexrgb(ribbon) + (255,))
    img.alpha_composite(texture(rb, 12, cloth=True))
    return img


def emblem_anvil(img, cx, cy):
    gilt_shape(img, anvil_mask(cx, cy + 40, 150))
    spark(img, cx + 120, cy - 120, 70)
    spark(img, cx + 40, cy - 170, 34)


def emblem_openbook(img, cx, cy):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    for side in (-1, 1):
        pts = [(cx, cy + 70)]
        for k in range(0, 21):
            t = k / 20
            pts.append((cx + side * 170 * t, cy + 70 - 40 * math.sin(math.pi * t) - 150 + 20 * t * t))
        pts += [(cx + side * 170, cy + 100), (cx, cy + 120)]
        d.polygon(pts, fill=255)
    gilt_shape(img, m)
    for k in range(-2, 3):                                           # rays
        a = math.radians(-90 + k * 22)
        gilt_line(img, [(cx + 40 * math.cos(a), cy - 120 + 40 * math.sin(a)),
                        (cx + 120 * math.cos(a), cy - 120 + 120 * math.sin(a))], 7)


def option_midnight():
    return hardcover("#26346F", "#0D1433", "#33448A", emblem_anvil, "#C2273F")


def option_teal():
    return hardcover("#2A9D96", "#0F4F4C", "#36B0A8", emblem_openbook, "#F26B5B", cloth=True)


# ------------------------------------------------------------------ spines on a shelf
def option_shelf():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = mask_round((S, S), (40, 40, 984, 984), 190)
    drop_shadow(img, tile, (0, 16), 30, 90)
    paste_masked(img, radial((S, S), "#FFFFFF", "#D6E2F3", 0.4, 0.25, 1.2), tile)
    plank = mask_round((S, S), (120, 790, 904, 860), 18)
    drop_shadow(img, plank, (0, 14), 16, 110)
    paste_masked(img, texture(grad((S, S), "#5C6E86", "#36465C"), 10), plank)
    spines = [("#4A6FA5", 210, 570), ("#3F7F86", 330, 520), ("#7D5A8E", 450, 600),
              ("#B0505C", 560, 480), ("#5E7F3A", 690, 540)]
    x = 180
    for i, (col, w_, h_) in enumerate(spines):
        w_ = [118, 104, 128, 96, 112][i]
        top = 790 - h_
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        m = mask_round((S, S), (x, top, x + w_, 792), 16)
        c = hexrgb(col)
        dark = "#%02X%02X%02X" % tuple(int(v * 0.62) for v in c)
        light = "#%02X%02X%02X" % tuple(min(255, int(v * 1.25)) for v in c)
        paste_masked(layer, texture(grad((S, S), light, dark, 0), 12, cloth=True), m)
        lab = mask_round((S, S), (x + 18, top + 120, x + w_ - 18, top + 230), 10)
        paste_masked(layer, grad((S, S), "#FFF6DA", "#E9D8A6"), lab)
        for yy in (top + 50, top + 80, 772 - 40):
            gilt_line(layer, [(x + 10, yy), (x + w_ - 10, yy)], 7)
        if i == len(spines) - 1:                     # the last book leans on its neighbour
            layer = layer.rotate(-11, resample=Image.BICUBIC, center=(x, 792))
        sh = layer.split()[3]
        drop_shadow(img, sh, (10, 0), 10, 90)
        img.alpha_composite(layer)
        x += w_ + 8
    return img


# ------------------------------------------------------------------ ember forge: an open book giving off sparks
def option_ember():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = mask_round((S, S), (40, 40, 984, 984), 190)
    drop_shadow(img, tile, (0, 16), 30, 110)
    paste_masked(img, radial((S, S), "#3B2F7A", "#120F2A", 0.5, 0.62, 0.9), tile)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((250, 300, 774, 700), fill=(255, 150, 60, 170))
    img.alpha_composite(Image.composite(glow.filter(ImageFilter.GaussianBlur(90)),
                                        Image.new("RGBA", (S, S), (0, 0, 0, 0)), tile))
    cx, cy = 512, 650
    for side in (-1, 1):                                  # cover under the pages
        m = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m).polygon([(cx, cy + 60), (cx + side * 330, cy - 10), (cx + side * 330, cy + 40),
                                   (cx, cy + 110)], fill=255)
        paste_masked(img, grad((S, S), "#B33A3A", "#5E1717", 90), m)
    for layer_i, lift in enumerate((0, 16, 32)):          # three page layers per side
        for side in (-1, 1):
            m = Image.new("L", (S, S), 0)
            pts = [(cx, cy + 50 - lift)]
            for k in range(21):
                t = k / 20
                pts.append((cx + side * (300 - layer_i * 6) * t, cy + 40 - lift - 120 * math.sin(math.pi * t * 0.9)
                            - 60 * t))
            pts += [(cx + side * (300 - layer_i * 6), cy + 40 - lift), (cx, cy + 70 - lift)]
            ImageDraw.Draw(m).polygon(pts, fill=255)
            shade = "#FFF7E8" if side == 1 else "#F3E6CC"
            paste_masked(img, grad((S, S), shade, "#E4C99A", 90 if side == 1 else 70), m)
    lines = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lines)
    for side in (-1, 1):
        for k in range(6):
            y0 = cy - 60 + k * 26
            d.line([(cx + side * 60, y0 - 70), (cx + side * 250, y0 - 105)], fill=(150, 120, 80, 150), width=6)
    img.alpha_composite(lines)
    gilt_line(img, [(cx, cy - 160), (cx, cy + 66)], 6)
    for (x, y, r) in [(512, 330, 90), (430, 250, 46), (610, 230, 56), (520, 170, 30), (380, 360, 32),
                      (660, 330, 38), (470, 120, 22), (580, 110, 18)]:
        spark(img, x, y, r, (255, 214, 120))
    return img


# ------------------------------------------------------------------ the binder's tools: signature + needle & thread
def option_needle():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = mask_round((S, S), (40, 40, 984, 984), 190)
    drop_shadow(img, tile, (0, 16), 30, 90)
    paste_masked(img, grad((S, S), "#EDE3FF", "#A9C1F5", 60), tile)
    # an opened signature seen from above: two page fans meeting at the fold (the spine)
    cx = 512
    for k in range(4, -1, -1):
        for side in (-1, 1):
            m = Image.new("L", (S, S), 0)
            w_ = 300 - k * 10
            ImageDraw.Draw(m).polygon([(cx, 250 - k * 6), (cx + side * w_, 210 + k * 8), (cx + side * w_, 760 + k * 8),
                                       (cx, 800 - k * 6)], fill=255)
            if k == 4:
                drop_shadow(img, m, (0, 14), 18, 70)
            shade = ("#FFFFFF", "#E8EDF7") if side == 1 else ("#F2F5FB", "#DCE3F0")
            paste_masked(img, grad((S, S), shade[0], shade[1], 0 if side == 1 else 180), m)
    crease = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(crease).line([(cx, 250), (cx, 800)], fill=(150, 165, 195, 255), width=5)
    img.alpha_composite(crease.filter(ImageFilter.GaussianBlur(1)))
    # running stitches down the fold
    th = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(th)
    ys = [300, 395, 490, 585, 680, 750]
    for a, b in zip(ys[::2], ys[1::2]):
        d.line([(cx, a), (cx, b)], fill=(200, 34, 64, 255), width=16)
        d.line([(cx - 3, a + 4), (cx - 3, b - 4)], fill=(255, 150, 160, 255), width=5)
    for y in ys:
        d.ellipse((cx - 9, y - 9, cx + 9, y + 9), fill=(80, 70, 100, 255))
    # loose thread leading to the needle
    tail = [(cx, 750), (cx + 60, 790), (cx + 150, 800), (cx + 230, 770), (cx + 290, 700)]
    d.line(tail, fill=(200, 34, 64, 255), width=12, joint="curve")
    d.line([(x - 2, y - 3) for x, y in tail], fill=(255, 150, 160, 255), width=4, joint="curve")
    img.alpha_composite(th)
    # straight needle, lying diagonally across the right-hand pages
    nd = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(nd)
    x0, y0, x1, y1 = cx + 290, 700, cx + 120, 300           # eye end -> point
    d.line([(x0, y0), (x1, y1)], fill=(80, 88, 104, 255), width=24)
    d.line([(x0, y0), (x1, y1)], fill=(200, 208, 222, 255), width=15)
    d.line([(x0 - 4, y0 - 3), (x1 - 4, y1 - 3)], fill=(255, 255, 255, 255), width=5)
    d.polygon([(x1 - 9, y1 + 4), (x1 + 9, y1 + 4), (x1 - 12, y1 - 60)], fill=(200, 208, 222, 255))
    ang = math.atan2(y1 - y0, x1 - x0)
    ex, ey = x0 + 40 * math.cos(ang), y0 + 40 * math.sin(ang)
    d.ellipse((ex - 6, ey - 16, ex + 6, ey + 16), fill=(60, 66, 80, 255))
    shadow = nd.split()[3].filter(ImageFilter.GaussianBlur(10))
    sh = Image.new("RGBA", (S, S), (40, 50, 80, 0))
    sh.putalpha(ImageChops.offset(shadow, 10, 14).point(lambda v: v * 90 // 255))
    img.alpha_composite(sh)
    img.alpha_composite(nd)
    return img


OPTIONS = [("A", "Midnight Grimoire", option_midnight), ("B", "Teal Bookcloth", option_teal),
           ("C", "Spines on a Shelf", option_shelf), ("D", "Ember Forge", option_ember),
           ("E", "Binder's Needle", option_needle)]

if __name__ == "__main__":
    from PIL import ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    cards = []
    for key, name, fn in OPTIONS:
        big = fn()
        big.save(os.path.join(OUT, f"option_{key}.png"))
        big.save(os.path.join(OUT, f"option_{key}.ico"),
                 sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
        card = Image.new("RGBA", (560, 520), (0, 0, 0, 0))
        for bx, bg in ((0, (246, 247, 250)), (280, (36, 38, 46))):
            ImageDraw.Draw(card).rectangle((bx, 0, bx + 280, 520), fill=bg + (255,))
            card.alpha_composite(big.resize((240, 240), Image.LANCZOS), (bx + 20, 70))
            x = bx + 22
            for sz in (64, 48, 32, 16):
                card.alpha_composite(big.resize((sz, sz), Image.LANCZOS), (x, 340 + (64 - sz) // 2))
                x += sz + 16
            ImageDraw.Draw(card).text((bx + 22, 430), "taskbar & title-bar sizes", fill=(140, 140, 150, 255), font=small)
        ImageDraw.Draw(card).rectangle((0, 0, 560, 60), fill=(255, 255, 255, 255))
        ImageDraw.Draw(card).text((20, 14), f"{key}  {name}", fill=(30, 30, 40, 255), font=font)
        cards.append(card)
    sheet = Image.new("RGBA", (3 * 580 + 20, 2 * 540 + 20), (210, 214, 222, 255))
    for i, c in enumerate(cards):
        sheet.alpha_composite(c, (20 + (i % 3) * 580, 20 + (i // 3) * 540))
    sheet.convert("RGB").save(os.path.join(OUT, "icon_options.png"))
    print("done")
