"""Generate synthetic demo passport / identity images.

These images are entirely fictional (country UTO/UTO, invented names).  They
are produced so that the OCR pipeline reads real text and the MRZ zone parses
with correct check digits, enabling an honest end-to-end demo without using any
real personal data.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

# Make `app` importable when run as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.services.mrz import compute_check_digit  # noqa: E402

SAMPLE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "samples"))
FONT_DIR = r"C:\Windows\Fonts"


def _font(name: str, size: int):
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _pad_to(value: str, width: int) -> str:
    return value.ljust(width, "<")[:width]


def build_td3(doc_num, country, surname, given, dob, sex, expiry,
              personal=None, tamper_doc=False) -> list[str]:
    if tamper_doc:
        dc = str((compute_check_digit(doc_num) + 1) % 10)
    else:
        dc = str(compute_check_digit(doc_num))
    dc_dob = str(compute_check_digit(dob))
    dc_exp = str(compute_check_digit(expiry))
    personal = personal or ("0" + "<" * 13)
    dc_personal = str(compute_check_digit(personal))
    # MRZ names must contain ONLY letters/digits/'<' (no spaces)
    surname_mrz = "".join(ch.upper() for ch in surname if ch.isalnum())
    given_mrz = "".join(ch.upper() for ch in given if ch.isalnum())
    name_field = _pad_to(f"{surname_mrz}<<{given_mrz}", 39)
    line1 = f"P<{country}{name_field}".ljust(44, "<")[:44]
    core = _pad_to(doc_num, 9) + dc + country + dob + dc_dob + sex + expiry + \
        dc_exp + personal + dc_personal
    dc_comp = str(compute_check_digit(core))
    line2 = (core + dc_comp).ljust(44, "<")[:44]
    return [line1, line2]


def _draw_line(draw, xy, text, font, fill=(0, 0, 0)):
    draw.text(xy, text, font=font, fill=fill)


def make_passport(output: str, doc_num="P12345678", surname="RAIJILO",
                  given="MARK THOMAS", dob="000504", sex="M", expiry="250912",
                  nationality="UTO", mrz=None, tamper_doc=False,
                  add_photo=True, photo_path=None) -> None:
    W, H = 1300, 880
    img = Image.new("RGB", (W, H), (235, 222, 196))  # anthracite data page tone
    draw = ImageDraw.Draw(img)

    # Borders / pattern
    draw.rectangle([0, 0, W - 1, H - 1], outline=(40, 60, 120), width=4)
    draw.rectangle([8, 8, W - 9, H - 9], outline=(60, 80, 140), width=1)

    # Header
    f_title = _font("ariblk.ttf", 48)
    f_field = _font("arial.ttf", 28)
    f_field_b = _font("arialbd.ttf", 30)
    f_mrz = _font("arialbd.ttf", 46)  # Bold sans reads best with RapidOCR

    _draw_line(draw, (40, 30), "REPUBLIC OF UTOPIA", f_title, (40, 40, 120))
    _draw_line(draw, (40, 95), "DEMONSTRATION PASSPORT - SAMPLE ONLY", f_field, (120, 120, 130))

    # Photo area
    photo_x, photo_y, photo_w, photo_h = 960, 160, 280, 320
    draw.rectangle([photo_x, photo_y, photo_x + photo_w, photo_y + photo_h],
                   outline=(60, 60, 60), width=2, fill=(180, 180, 150))
    _draw_line(draw, (photo_x, photo_y + photo_h + 6), "PHOTO", f_field, (80, 80, 80))

    # Data fields (label and value on the same line -> OCR-friendly)
    fields = [
        ("Surname", surname),
        ("Given names", given),
        ("Nationality", nationality),
        ("Date of birth", f"D.O.B. {dob[:2]}-{dob[2:4]}-{dob[4:]}"),
        ("Sex", "^" if sex == "M" else "F"),
        ("Date of issue", "24-05-04"),
        ("Date of expiry", f"{expiry[:2]}-{expiry[2:4]}-{expiry[4:]}"),
        ("Passport No.", doc_num),
    ]
    y = 180
    for label, val in fields:
        draw.rectangle([26, y - 4, 920, y + 40], outline=(140, 140, 140), width=1)
        _draw_line(draw, (40, y), f"{label}: {val}", f_field_b, (0, 0, 0))
        y += 64

    # MRZ zone (2x44 TD3)
    if mrz is None:
        mrz = build_td3(doc_num, nationality, surname, given, dob, sex, expiry,
                        tamper_doc=tamper_doc)
    mrz_y = H - 170
    draw.rectangle([20, mrz_y - 20, W - 20, H - 20], fill=(255, 255, 255),
                   outline=(0, 0, 0), width=1)
    for i, line in enumerate(mrz):
        _draw_line(draw, (60, mrz_y + i * 70), line, f_mrz, (0, 0, 0))

    img.save(output)
    print(f"  wrote {output}")


def make_face(output: str, variant: int = 0) -> None:
    """Create a stylised synthetic face for the demo (detection is best-effort)."""
    W, H = 400, 480
    img = Image.new("RGB", (W, H), (200, 200, 210))
    draw = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2

    # Hair
    draw.ellipse([cx - 150, cy - 190, cx + 150, cy + 40], fill=(60, 50, 40))
    # Head/face
    draw.ellipse([cx - 110, cy - 130, cx + 110, cy + 150], fill=(210, 180, 150))
    # Neck
    draw.rectangle([cx - 40, cy + 130, cx + 40, cy + 210], fill=(200, 170, 140))
    # Shoulders
    draw.rectangle([cx - 150, cy + 190, cx + 150, H], fill=(90, 60, 60))

    # Eyes
    eye_l = (cx - 45, cy - 30)
    eye_r = (cx + 45, cy - 30)
    if variant == 0:
        draw.ellipse([eye_l[0] - 22, eye_l[1] - 12, eye_l[0] + 22, eye_l[1] + 12], fill=(255, 255, 255))
        draw.ellipse([eye_r[0] - 22, eye_r[1] - 12, eye_r[0] + 22, eye_r[1] + 12], fill=(255, 255, 255))
        draw.ellipse([eye_l[0] - 8, eye_l[1] - 8, eye_l[0] + 8, eye_l[1] + 8], fill=(40, 40, 40))
        draw.ellipse([eye_r[0] - 8, eye_r[1] - 8, eye_r[0] + 8, eye_r[1] + 8], fill=(40, 40, 40))
        # Mouth
        draw.arc([cx - 50, cy + 40, cx + 50, cy + 110], 20, 160, fill=(120, 60, 60), width=6)
    else:
        # Different facing / glasses variant
        draw.ellipse([eye_l[0] - 25, eye_l[1] - 10, eye_l[0] + 25, eye_l[1] + 10], outline=(30, 30, 30), width=5)
        draw.ellipse([eye_r[0] - 25, eye_r[1] - 10, eye_r[0] + 25, eye_r[1] + 10], outline=(30, 30, 30), width=5)
        draw.ellipse([eye_l[0] - 6, eye_l[1] - 6, eye_l[0] + 6, eye_l[1] + 6], fill=(40, 40, 40))
        draw.ellipse([eye_r[0] - 6, eye_r[1] - 6, eye_r[0] + 6, eye_r[1] + 6], fill=(40, 40, 40))
        draw.line([cx - 40, cy + 70, cx + 40, cy + 60], fill=(120, 60, 60), width=6)

    img.save(output)
    print(f"  wrote {output}")


def generate_all() -> None:
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    print("Generating sample data...")

    # 1. Valid passport (future expiry relative to today 2026-09-02)
    make_passport(os.path.join(SAMPLE_DIR, "valid_passport.png"),
                  doc_num="P12345678", surname="RAIJILO", given="MARK THOMAS",
                  dob="000504", sex="M", expiry="330912", nationality="UTO")

    # 2. Expired passport
    make_passport(os.path.join(SAMPLE_DIR, "expired_passport.png"),
                  doc_num="P12345678", surname="RAIJILO", given="MARK THOMAS",
                  dob="000504", sex="M", expiry="200912", nationality="UTO")

    # 3. Tampered / MRZ-mismatch passport (visual doc number differs from MRZ
    #    AND the MRZ check digit is invalid -> doctored document).
    make_passport(os.path.join(SAMPLE_DIR, "mismatch_passport.png"),
                  doc_num="P12345678", surname="RAIJILO", given="MARK THOMAS",
                  dob="000504", sex="M", expiry="330912", nationality="UTO",
                  mrz=build_td3("P00000000", "UTO", "RAIJILO", "MARK THOMAS",
                                "000504", "M", "330912", tamper_doc=True))

    # 4. Watchlist passport
    make_passport(os.path.join(SAMPLE_DIR, "watchlist_passport.png"),
                  doc_num="X99887766", surname="DEMOOS", given="WATCH",
                  dob="850101", sex="M", expiry="330101", nationality="DMO")

    # Faces for the face demo (variant 0 ~ reference, variant 1 ~ provided)
    make_face(os.path.join(SAMPLE_DIR, "ref_face.png"), variant=0)
    make_face(os.path.join(SAMPLE_DIR, "provided_face.png"), variant=1)

    print("Sample generation complete.")


if __name__ == "__main__":
    generate_all()
