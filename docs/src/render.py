"""Render the HTML diagram sources in this folder to PNG images in ../images.

Usage:  python3 docs/src/render.py            # render all diagrams
        python3 docs/src/render.py 01         # render only files starting with "01"

Requires: pip install playwright && playwright install chromium
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "images"
SCALE = 2  # device pixel ratio -> crisp, print-quality PNGs


def main(prefix: str = "") -> None:
    pages = sorted(p for p in SRC.glob("*.html") if p.name.startswith(prefix) and not p.name.startswith("_"))
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for page_path in pages:
            page = browser.new_page(viewport={"width": 2400, "height": 1200}, device_scale_factor=SCALE)
            page.goto(page_path.as_uri() + "?export=1")  # export mode: no fit-to-window viewer
            page.wait_for_function("window.__ready === true", timeout=30_000)
            target = OUT / f"{page_path.stem}.png"
            page.locator("#canvas").screenshot(path=str(target))
            print(f"rendered {target.relative_to(SRC.parent.parent)}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
