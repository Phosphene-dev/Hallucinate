"""Build the 1280x640 social preview (assets/logo/social-preview.png) from the logo and the current Home screenshot.

Usage: python scripts/make_social.py        (needs Pillow and the Inter font)

Run it after scripts/screenshots.py so the preview shows the app as it looks now. GitHub doesn't read the file
from the repository: upload it under Settings → General → Social preview. The website uses it directly.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "logo" / "hallucinate-logo.png"
SHOT = ROOT / "docs" / "screenshots" / "home.png"
OUT = ROOT / "assets" / "logo" / "social-preview.png"
W, H = 1280, 640
# The website's colours (site/style.css).
BG = (5, 4, 8)
TEXT = (241, 236, 251)
DIM = (179, 169, 201)
FAINT = (138, 128, 162)
BORDER = (58, 48, 88)
GRAD = ((220, 195, 255), (242, 167, 214), (143, 179, 255))
FONT_DIRS = (Path("/usr/share/fonts"), Path.home() / ".local/share/fonts", Path("C:/Windows/Fonts"),
             Path("/Library/Fonts"), Path.home() / "Library/Fonts")


def font(names, size):
    for d in FONT_DIRS:
        for name in names:
            for path in d.rglob(name) if d.is_dir() else ():
                return ImageFont.truetype(str(path), size)
    raise SystemExit(f"Install the Inter font (looked for {names[0]})")


def glow(size, centre, radius, colour, strength):
    layer = Image.new("RGB", size, (0, 0, 0))
    x, y = centre
    ImageDraw.Draw(layer).ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.6))
    return Image.eval(layer, lambda v: int(v * strength))


def gradient_text(img, xy, text, fnt):
    """Text filled with the website's lavender → pink → sky gradient."""
    x, y = xy
    box = ImageDraw.Draw(img).textbbox((x, y), text, font=fnt)
    w, h = box[2] - box[0], box[3] - box[1]
    fill = Image.new("RGB", (w, 1))
    for i in range(w):
        t = i / max(1, w - 1) * 2
        a, b = (GRAD[0], GRAD[1]) if t <= 1 else (GRAD[1], GRAD[2])
        t = t if t <= 1 else t - 1
        fill.putpixel((i, 0), tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    fill = fill.resize((w, h))
    mask = Image.new("L", (w, h))
    ImageDraw.Draw(mask).text((x - box[0], y - box[1]), text, font=fnt, fill=255)
    img.paste(fill, (box[0], box[1]), mask)


def rounded(im, radius):
    """`im` with antialiased rounded corners, as RGBA (drawn at 4x, then scaled down)."""
    big = Image.new("L", (im.width * 4, im.height * 4))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, big.width - 1, big.height - 1), radius * 4, fill=255)
    out = im.convert("RGBA")
    out.putalpha(big.resize(im.size, Image.LANCZOS))
    return out


def main():
    card = Image.new("RGB", (W, H), BG)
    # soft light behind the logo and the screenshot, like the website's hero
    card = ImageChops.add(card, glow((W, H), (320, 300), 230, (120, 80, 190), 0.55))
    card = ImageChops.add(card, glow((W, H), (950, 440), 260, (110, 70, 160), 0.30))

    # The logo has its own dark, hazy square background: screen-blend it over the glow and fade its edges
    # out so no square shows.
    logo = Image.open(LOGO).convert("RGB").resize((560, 560), Image.LANCZOS)
    region = card.crop((40, 40, 600, 600))
    fade = Image.new("L", logo.size)
    ImageDraw.Draw(fade).ellipse((40, 30, 520, 530), fill=255)
    fade = fade.filter(ImageFilter.GaussianBlur(40))
    card.paste(ImageChops.screen(region, logo), (40, 40), fade)

    x = 660
    draw = ImageDraw.Draw(card)
    head = font(("InterDisplay-SemiBold.otf", "Inter-SemiBold.otf", "Inter-SemiBold.ttf"), 46)
    sub = font(("Inter-Regular.otf", "Inter-Regular.ttf"), 24)
    draw.text((x, 70), "A fast desktop music player", font=head, fill=TEXT)
    gradient_text(card, (x, 126), "for the music you own.", head)
    draw = ImageDraw.Draw(card)
    draw.text((x, 196), "Instant search · gapless · visualizers · your history", font=sub, fill=DIM)

    # The app itself, with rounded corners, a thin border and a shadow.
    sw = W - x - 48
    shot = Image.open(SHOT).convert("RGB")
    shot = shot.resize((sw, round(shot.height * sw / shot.width)), Image.LANCZOS)
    top = 250
    shadow = Image.new("L", (W, H))
    ImageDraw.Draw(shadow).rounded_rectangle((x, top + 14, x + sw, top + shot.height + 14), 14, fill=170)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    card.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow)
    frame = Image.new("RGB", (sw + 2, shot.height + 2), BORDER)
    card.paste(rounded(frame, 15), (x - 1, top - 1), rounded(frame, 15))
    card.paste(rounded(shot, 14), (x, top), rounded(shot, 14))

    small = font(("Inter-Medium.otf", "Inter-Medium.ttf"), 19)
    draw = ImageDraw.Draw(card)
    note = "Linux · Windows · macOS   ·   free & open source"
    nw = draw.textlength(note, font=small)
    draw.text((320 - nw / 2, 590), note, font=small, fill=FAINT)
    card.save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
