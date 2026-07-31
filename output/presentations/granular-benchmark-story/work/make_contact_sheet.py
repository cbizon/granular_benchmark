from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
RENDERED = ROOT / "rendered"
SLIDES = sorted(RENDERED.glob("slide-*.png"))
THUMBNAIL = (384, 216)
COLUMNS = 4
GAP = 18
LABEL = 26


def main() -> None:
    rows = (len(SLIDES) + COLUMNS - 1) // COLUMNS
    sheet = Image.new(
        "RGB",
        (
            COLUMNS * THUMBNAIL[0] + (COLUMNS + 1) * GAP,
            rows * (THUMBNAIL[1] + LABEL) + (rows + 1) * GAP,
        ),
        "#D9D9D9",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, slide_path in enumerate(SLIDES):
        row, column = divmod(index, COLUMNS)
        x = GAP + column * (THUMBNAIL[0] + GAP)
        y = GAP + row * (THUMBNAIL[1] + LABEL + GAP)
        slide = Image.open(slide_path).convert("RGB").resize(
            THUMBNAIL,
            Image.Resampling.LANCZOS,
        )
        sheet.paste(slide, (x, y))
        draw.text(
            (x, y + THUMBNAIL[1] + 6),
            f"Slide {index + 1}",
            fill="#111111",
            font=font,
        )
    sheet.save(RENDERED / "contact-sheet.png")


if __name__ == "__main__":
    main()
