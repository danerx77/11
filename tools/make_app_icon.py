"""Generuje ikonę aplikacji: assets/energodok.ico oraz assets/energodok.png.

Ikona jest rysowana w dużej rozdzielczości i pomniejszana z wygładzaniem,
dzięki czemu każdy rozmiar zapisany w pliku ICO pozostaje czytelny — również
mały 16x16 widoczny na pasku zadań Windows.

Skrypt korzysta wyłącznie z biblioteki Pillow, która jest już wymagana przez
program (requirements-windows.txt). Plik .ico jest zapisany w repozytorium,
więc build_windows.ps1 nie musi go generować; ten skrypt służy do odtworzenia
ikony po zmianie kolorów lub kształtu.

Uruchomienie:

    python tools/make_app_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Rozmiary wymagane przez Windows dla czytelnego pliku .ico.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

# Rysujemy w tej rozdzielczości i dopiero potem pomniejszamy (antyaliasing).
CANVAS = 1024

BACKGROUND_TOP = (43, 139, 239)
BACKGROUND_BOTTOM = (13, 79, 158)
BORDER_COLOR = (8, 53, 108)
LETTER_COLOR = (255, 255, 255)
# Litera na ikonie — pierwsza litera nazwy programu (EnergoDok).
APP_LETTER = "E"
BOLT_COLOR = (255, 211, 77)
BOLT_EDGE = (181, 124, 0)

# Znormalizowany kształt błyskawicy w układzie 0..1 wewnątrz jej odznaki.
BOLT_POINTS = (
    (0.585, 0.070),
    (0.305, 0.560),
    (0.480, 0.560),
    (0.395, 0.930),
    (0.700, 0.440),
    (0.520, 0.440),
)

FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def _load_font(pixel_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, pixel_size)
        except OSError:
            continue
    # Ostatecznie rysujemy czcionką wbudowaną; ikona nadal powstanie.
    return ImageFont.load_default()


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        ratio = y / max(1, size - 1)
        gradient.putpixel(
            (0, y),
            tuple(
                round(top[channel] + (bottom[channel] - top[channel]) * ratio)
                for channel in range(3)
            ),
        )
    return gradient.resize((size, size), Image.Resampling.BICUBIC)


def render_master() -> Image.Image:
    """Rysuje ikonę w rozdzielczości CANVAS x CANVAS."""

    size = CANVAS
    margin = round(size * 0.045)
    radius = round(size * 0.22)
    box = (margin, margin, size - margin - 1, size - margin - 1)

    # Zaokrąglona maska tła z gradientem.
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste(
        _vertical_gradient(size, BACKGROUND_TOP, BACKGROUND_BOTTOM).convert("RGBA"),
        (0, 0),
        mask,
    )

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        box,
        radius=radius,
        outline=BORDER_COLOR + (255,),
        width=max(2, round(size * 0.035)),
    )

    # Litera E – znak rozpoznawczy programu. Jest lekko przesunięta w lewo,
    # aby odznaka z błyskawicą w prawym dolnym rogu jej nie zasłaniała.
    font = _load_font(round(size * 0.60))
    letter_box = draw.textbbox((0, 0), APP_LETTER, font=font)
    letter_x = (size - (letter_box[2] - letter_box[0])) / 2 - letter_box[0] - size * 0.085
    letter_y = (size - (letter_box[3] - letter_box[1])) / 2 - letter_box[1] - size * 0.055
    draw.text((letter_x, letter_y), APP_LETTER, font=font, fill=LETTER_COLOR + (255,))

    # Błyskawica jako osobna odznaka: czytelny znak inwestycji
    # elektroenergetycznych, który nie nachodzi na literę.
    badge_size = round(size * 0.44)
    badge_left = round(size * 0.505)
    badge_top = round(size * 0.505)
    badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.ellipse(
        (0, 0, badge_size - 1, badge_size - 1),
        fill=(255, 255, 255, 255),
        outline=BORDER_COLOR + (255,),
        width=max(2, round(badge_size * 0.055)),
    )
    badge_draw.polygon(
        [(x * badge_size, y * badge_size) for x, y in BOLT_POINTS],
        fill=BOLT_COLOR + (255,),
        outline=BOLT_EDGE + (255,),
    )
    image.alpha_composite(badge, (badge_left, badge_top))

    return image


def render_small_master() -> Image.Image:
    """Wariant bez błyskawicy dla najmniejszych rozmiarów (16–20 px).

    Przy tak małej ikonie błyskawica zlewa się z literą, dlatego zostaje
    wyłącznie czytelne „E” na niebieskim tle.
    """

    size = CANVAS
    margin = round(size * 0.045)
    radius = round(size * 0.22)
    box = (margin, margin, size - margin - 1, size - margin - 1)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste(
        _vertical_gradient(size, BACKGROUND_TOP, BACKGROUND_BOTTOM).convert("RGBA"),
        (0, 0),
        mask,
    )

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        box,
        radius=radius,
        outline=BORDER_COLOR + (255,),
        width=max(2, round(size * 0.05)),
    )

    font = _load_font(round(size * 0.70))
    letter_box = draw.textbbox((0, 0), APP_LETTER, font=font)
    letter_x = (size - (letter_box[2] - letter_box[0])) / 2 - letter_box[0]
    letter_y = (size - (letter_box[3] - letter_box[1])) / 2 - letter_box[1]
    draw.text((letter_x, letter_y), APP_LETTER, font=font, fill=LETTER_COLOR + (255,))
    return image


def build_images() -> list[Image.Image]:
    master = render_master()
    small_master = render_small_master()
    images = []
    for size in ICON_SIZES:
        source = small_master if size <= 20 else master
        images.append(source.resize((size, size), Image.Resampling.LANCZOS))
    return images


def main() -> int:
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    images = build_images()
    largest = images[-1]

    ico_path = assets_dir / "energodok.ico"
    png_path = assets_dir / "energodok.png"

    largest.save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        append_images=images[:-1],
    )
    largest.save(png_path, format="PNG")

    print(f"Zapisano: {ico_path}")
    print(f"Zapisano: {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
