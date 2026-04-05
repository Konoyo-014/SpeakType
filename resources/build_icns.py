#!/usr/bin/env python3
"""
Build SpeakType.icns from icon.svg.
Renders SVG to PNG at all required macOS iconset sizes, then runs iconutil.
"""

import os
import subprocess
import shutil
import cairosvg
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_PATH = os.path.join(BASE_DIR, "icon.svg")
ICONSET_DIR = os.path.join(BASE_DIR, "SpeakType.iconset")
ICNS_PATH = os.path.join(BASE_DIR, "SpeakType.icns")

# macOS iconset requires these sizes:
# icon_16x16.png, icon_16x16@2x.png (32),
# icon_32x32.png, icon_32x32@2x.png (64),
# icon_128x128.png, icon_128x128@2x.png (256),
# icon_256x256.png, icon_256x256@2x.png (512),
# icon_512x512.png, icon_512x512@2x.png (1024)
ICON_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def main():
    # Clean up any previous iconset
    if os.path.exists(ICONSET_DIR):
        shutil.rmtree(ICONSET_DIR)
    os.makedirs(ICONSET_DIR)

    print(f"Reading SVG from: {SVG_PATH}")

    # First render at max resolution (1024x1024), then downscale for quality
    print("Rendering SVG to 1024x1024 master PNG...")
    master_png = cairosvg.svg2png(
        url=SVG_PATH,
        output_width=1024,
        output_height=1024,
    )

    # Save master PNG for reference
    master_path = os.path.join(BASE_DIR, "icon_1024.png")
    with open(master_path, "wb") as f:
        f.write(master_png)
    print(f"Master PNG saved: {master_path}")

    # Open master with Pillow for high-quality downscaling
    master_img = Image.open(master_path)

    # Generate all iconset sizes
    for filename, size in ICON_SIZES:
        out_path = os.path.join(ICONSET_DIR, filename)
        resized = master_img.resize((size, size), Image.LANCZOS)
        resized.save(out_path, "PNG")
        print(f"  Created {filename} ({size}x{size})")

    print(f"\nIconset directory: {ICONSET_DIR}")

    # Remove old .icns if it exists
    if os.path.exists(ICNS_PATH):
        os.remove(ICNS_PATH)

    # Run iconutil to create .icns
    print("Running iconutil -c icns ...")
    result = subprocess.run(
        ["iconutil", "-c", "icns", ICONSET_DIR, "-o", ICNS_PATH],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"ERROR: iconutil failed: {result.stderr}")
        return 1

    print(f"Successfully created: {ICNS_PATH}")
    icns_size = os.path.getsize(ICNS_PATH)
    print(f"File size: {icns_size:,} bytes")

    # Clean up iconset directory
    shutil.rmtree(ICONSET_DIR)
    print("Cleaned up iconset directory.")

    return 0


if __name__ == "__main__":
    exit(main())
