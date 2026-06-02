"""Render a styled HTML file to a browser-quality PDF via headless Chromium.
Usage: python render_pdf.py <input.html> <output.pdf>
"""
import sys
import pathlib
from playwright.sync_api import sync_playwright


def render(html_path: str, pdf_path: str) -> None:
    uri = pathlib.Path(html_path).resolve().as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(uri, wait_until="networkidle")
        pg.pdf(
            path=pdf_path,
            format="Letter",
            print_background=True,
            prefer_css_page_size=True,
        )
        b.close()
    print(f"Rendered {pdf_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python render_pdf.py <input.html> <output.pdf>")
        sys.exit(1)
    render(sys.argv[1], sys.argv[2])
