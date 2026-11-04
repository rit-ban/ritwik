#!/usr/bin/env python3
"""Prepare a folder of trek photos for et-elia.html.

Usage (from the website folder):
    python3 Trek/make_album.py Trek/Hampta

For every photo in the folder, writes next to it:
    <name>.jpg        full resolution at JPEG quality 95 with full colour detail
                      and the camera's own colour profile; opens in the lightbox.
                      Made only from HEIC/PNG originals, because browsers other
                      than Safari cannot show HEIC. A JPEG original is used as is.
    <name>-thumb.jpg  800 px preview for the thumbnail strip.
The originals are never changed. (If a folder holds both IMG_1.HEIC and
IMG_1.jpg, the .jpg is taken to be this script's output and is rewritten.)

Then prints one HTML line per photo, sorted by capture time, ready to paste
into a .strip-track block. Fill in the alt="" text by hand.

Needs macOS `sips` (built in, decodes HEIC) and Pillow.
"""
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

THUMB_EDGE = 800
SITE_ROOT = Path(__file__).resolve().parent.parent
CONVERT = {".heic", ".png"}                 # originals that need a JPEG copy
EXTS = CONVERT | {".jpg", ".jpeg"}


def capture_time(p):
    """Capture time from the photo's EXIF, read with sips."""
    out = subprocess.run(["sips", "-g", "creation", str(p)], capture_output=True, text=True).stdout
    m = re.search(r"creation: (\d{4}:\d\d:\d\d \d\d:\d\d:\d\d)", out)
    return datetime.strptime(m.group(1), "%Y:%m:%d %H:%M:%S") if m else None


def main(folder):
    src = Path(folder).resolve()
    by_stem = {}
    for p in src.iterdir():
        if p.suffix.lower() in EXTS and not p.stem.endswith("-thumb"):
            by_stem.setdefault(p.stem, []).append(p)

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for stem, files in sorted(by_stem.items()):
            original = next((f for f in files if f.suffix.lower() in CONVERT), None)
            if original:
                # 1. sips decodes the HEIC losslessly to TIFF, applying the camera's
                #    rotation, so the pixels come out upright.
                tif = Path(tmp) / f"{stem}.tif"
                subprocess.run(["sips", "-s", "format", "tiff", str(original), "--out", str(tif)],
                               check=True, capture_output=True)
                im = Image.open(tif)
                icc = im.info.get("icc_profile")    # keep the camera's colour profile (Display P3)
                im = im.convert("RGB")
                # 2. One high-quality JPEG encode at full resolution. No EXIF is
                #    written, so GPS location never reaches the public site.
                full = src / f"{stem}.jpg"
                im.save(full, "JPEG", quality=95, subsampling=0, optimize=True,
                        progressive=True, icc_profile=icc)
                taken = capture_time(original)
            else:
                # A JPEG original is published untouched; warn if it carries GPS.
                full = next(f for f in files if f.suffix.lower() in {".jpg", ".jpeg"})
                im = Image.open(full)
                icc = im.info.get("icc_profile")
                if im.getexif().get_ifd(0x8825):
                    print(f"  warning: {full.name} contains GPS location data", file=sys.stderr)
                im = ImageOps.exif_transpose(im).convert("RGB")
                taken = capture_time(full)

            # 3. Small preview for the strip, same colour profile as the full image.
            thumb = im.copy()
            thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
            thumb.save(src / f"{stem}-thumb.jpg", "JPEG", quality=85, optimize=True,
                       progressive=True, icc_profile=icc)
            rows.append((taken, full.name, f"{stem}-thumb.jpg", *thumb.size))
            print(f"  done {stem}", file=sys.stderr)

    # 4. HTML for the strip, in the order the photos were taken.
    rel = src.relative_to(SITE_ROOT).as_posix()
    rows.sort(key=lambda r: (r[0] is None, r[0] or datetime.min, r[1]))
    for taken, full_name, thumb_name, w, h in rows:
        iso = taken.strftime("%Y-%m-%dT%H:%M") if taken else ""
        print(f'      <a class="photo" href="{rel}/{full_name}" data-taken="{iso}">'
              f'<img src="{rel}/{thumb_name}" width="{w}" height="{h}" alt="" loading="lazy"></a>')


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
