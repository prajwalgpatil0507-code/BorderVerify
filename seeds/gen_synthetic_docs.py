"""Generate SYNTHETIC demo identity documents for the tamper module.

These are FICTIONAL mockups for the SIH prototype.  They are NOT real Aadhaar,
PAN, passport, or college ID documents.  Every name, number, and address is
invented.  Do not use for any real verification.

For each document type we emit two images into ``data/samples``:
  * ``_valid``    - the pristine/original synthetic card
  * ``_tampered`` - the same card with controlled edits: altered name/date/ID,
                    a bright pasted photo region, and a shifted/relaid text block.

The tampered images deliberately carry visible structural anomalies so the
``document_anomaly`` image analysis can flag them without OCR needing to succeed.
"""
from __future__ import annotations

import os
import sys
from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import load_default  # noqa: F401 (kept for clarity)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "samples")
os.makedirs(OUT, exist_ok=True)


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return load_default()


_CARD = (240, 244, 248)         # card background
_DARK = (20, 22, 26)            # primary text
_MUTED = (90, 96, 104)          # secondary text
_ACCENT = (30, 90, 160)         # header accent
_PHOTO = (150, 158, 168)        # flat photo fill


def _base_card(w=620, h=392):
    img = Image.new("RGB", (w, h), _CARD)
    d = ImageDraw.Draw(img)
    # subtle card border
    d.rectangle([6, 6, w - 6, h - 6], outline=(210, 216, 224), width=2)
    return img, d


def _header(d, x, y, title, subtitle):
    d.text((x, y), title, fill=_ACCENT, font=_font(26, bold=True))
    d.text((x, y + 34), subtitle, fill=_MUTED, font=_font(14))


def _photo(d, x, y, size=140, border=False, bright=False):
    fill = (235, 238, 242) if bright else _PHOTO
    d.rectangle([x, y, x + size, y + size], fill=fill, outline=(180, 186, 194), width=2)
    # simple portrait silhouette
    d.ellipse([x + size * 0.32, y + size * 0.14, x + size * 0.68, y + size * 0.5],
              fill=(120, 128, 138))
    d.pieslice([x + size * 0.10, y + size * 0.45, x + size * 0.90, y + size * 1.05],
               180, 360, fill=(120, 128, 138))
    if border:
        # strong red box -> detectable edge discontinuity around the photo area
        d.rectangle([x - 6, y - 6, x + size + 6, y + size + 6],
                    outline=(200, 30, 30), width=5)
    return (x, y, x + size, y + size)


def _field(d, x, y, label, value, vfont_size=20, vcolor=_DARK, patch=None):
    d.text((x, y), label, fill=_MUTED, font=_font(13))
    if patch:
        # a pasted, differently-shaded strip behind the altered value
        d.rectangle([x - 2, y + 18, x + 230, y + 18 + 26],
                    fill=patch)  # patch is an RGB tuple
    d.text((x, y + 16), value, fill=vcolor, font=_font(vfont_size, bold=True))


# ---------------------------------------------------------------------------
# Aadhaar-style (12-digit ID)
# ---------------------------------------------------------------------------

def make_aadhaar(valid: bool):
    img, d = _base_card()
    _header(d, 20, 18, "GOVERNMENT OF INDIA  (SYNTHETIC)", "Unique Identification Authority")
    d.text((20, 58), "AADHAAR  ·  DEMO ONLY", fill=_DARK, font=_font(22, bold=True))

    _photo(d, 20, 96, 150, border=not valid, bright=not valid)

    aadhaar = "7654 1098 2310" if valid else "7654 1098 2319"   # last digit changed -> fails checksum
    name = "ANANYA SHARMA" if valid else "ROHAN VERMA"          # name changed
    dob = "12-04-1994" if valid else "01-01-1999"               # date changed
    gender = "FEMALE" if valid else "MALE"

    patch = (234, 228, 210) if not valid else None
    d.text((20, 96), "", fill=_DARK, font=_font(14))            # noop keeps layout stable
    _field(d, 190, 100, "Name", name, patch=patch)
    _field(d, 190, 156, "Date of Birth", dob, patch=patch)
    _field(d, 190, 212, "Gender", gender, patch=patch)
    _field(d, 190, 268, "Aadhaar No.", aadhaar,
           vfont_size=24, vcolor=(200, 40, 40) if not valid else _DARK,
           patch=patch)
    d.text((190, 320), "Address: 12, Demo Nagar, SIH (SYNTHETIC)", fill=_MUTED, font=_font(13))
    # QR-ish square
    d.rectangle([20, 300, 120, 392], fill=(235, 238, 242), outline=(200, 206, 214))
    return img


# ---------------------------------------------------------------------------
# PAN-style (10-char: AAAAA9999A)
# ---------------------------------------------------------------------------

def make_pan(valid: bool):
    img, d = _base_card()
    _header(d, 20, 18, "INCOME TAX DEPARTMENT  (SYNTHETIC)", "Permanent Account Number")
    d.text((20, 58), "PAN CARD  ·  DEMO ONLY", fill=_DARK, font=_font(22, bold=True))

    _photo(d, 20, 96, 140, border=not valid, bright=not valid)

    pan = "BKMPS4892L" if valid else "BKMPS4892X"   # check letter changed -> invalid
    name = "KIRAN MEHTA" if valid else "DEV PATEL"  # name changed
    fname = "K L MEHTA" if valid else "D PATEL"     # father name changed
    dob = "22-08-1991" if valid else "15-06-1995"   # date changed

    patch = (230, 224, 214) if not valid else None
    _field(d, 190, 100, "Name", name, vfont_size=22, patch=patch)
    _field(d, 190, 156, "Father's Name", fname, patch=patch)
    _field(d, 190, 212, "Date of Birth", dob, patch=patch)
    _field(d, 190, 268, "PAN", pan, vfont_size=26,
           vcolor=(200, 40, 40) if not valid else _DARK, patch=patch)
    d.text((20, 300), "Signature (synthetic scan)", fill=_MUTED, font=_font(13))
    return img


# ---------------------------------------------------------------------------
# College ID (roll number)
# ---------------------------------------------------------------------------

def make_college(valid: bool):
    img, d = _base_card()
    _header(d, 20, 18, "NATIONAL INSTITUTE OF DEMO  (SYNTHETIC)", "Student Identity Card")
    d.text((20, 58), "COLLEGE ID  ·  DEMO ONLY", fill=_DARK, font=_font(22, bold=True))

    _photo(d, 20, 96, 140, border=not valid, bright=not valid)

    roll = "2023CS0142" if valid else "2023CS0714"   # roll changed
    name = "PRIYA NAIR" if valid else "SAHIL KHAN"   # name changed
    branch = "B.Tech CSE" if valid else "B.Tech MECH"
    yr = "2023-2027" if valid else "2022-2026"        # date range changed

    patch = (228, 226, 218) if not valid else None
    _field(d, 190, 100, "Student Name", name, patch=patch)
    _field(d, 190, 156, "Branch", branch, patch=patch)
    _field(d, 190, 212, "Academic Year", yr, patch=patch)
    _field(d, 190, 268, "Roll No.", roll, vfont_size=26,
           vcolor=(200, 40, 40) if not valid else _DARK, patch=patch)
    d.text((20, 300), "Issued: SIH Demo Authority  ·  This card is synthetic.", fill=_MUTED, font=_font(13))
    return img


def main():
    specs = {
        "synthetic_aadhaar_valid.png": make_aadhaar(True),
        "synthetic_aadhaar_tampered.png": make_aadhaar(False),
        "synthetic_pan_valid.png": make_pan(True),
        "synthetic_pan_tampered.png": make_pan(False),
        "synthetic_collegeid_valid.png": make_college(True),
        "synthetic_collegeid_tampered.png": make_college(False),
    }
    for name, img in specs.items():
        path = os.path.join(OUT, name)
        img.save(path, "PNG")
        print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
