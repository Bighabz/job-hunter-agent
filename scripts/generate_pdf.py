#!/usr/bin/env python3
"""
generate_pdf.py — Convert markdown resume/cover letter to ATS-friendly PDF

Usage:
    python generate_pdf.py applications/company_role_date/resume.md
    python generate_pdf.py applications/company_role_date/cover_letter.md
    python generate_pdf.py applications/company_role_date/resume.md --output custom_name.pdf

Requirements:
    pip install markdown weasyprint --break-system-packages
"""

import argparse
import sys
from pathlib import Path

try:
    import markdown
    from weasyprint import HTML
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "markdown", "weasyprint", "--break-system-packages", "-q"
    ])
    import markdown
    from weasyprint import HTML


# ATS-friendly CSS — single column, standard fonts, no graphics
RESUME_CSS = """
@page {
    size: letter;
    margin: 0.6in 0.7in;
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.4;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 18pt;
    font-weight: 700;
    margin: 0 0 4pt 0;
    color: #0d0d0d;
    border-bottom: 1.5pt solid #2c3e50;
    padding-bottom: 4pt;
}

h2 {
    font-size: 12pt;
    font-weight: 700;
    margin: 12pt 0 4pt 0;
    color: #2c3e50;
    text-transform: uppercase;
    letter-spacing: 0.5pt;
    border-bottom: 0.75pt solid #bdc3c7;
    padding-bottom: 2pt;
}

h3 {
    font-size: 11pt;
    font-weight: 600;
    margin: 8pt 0 2pt 0;
    color: #1a1a1a;
}

p {
    margin: 2pt 0;
}

ul {
    margin: 2pt 0 6pt 0;
    padding-left: 18pt;
}

li {
    margin: 1pt 0;
}

strong {
    font-weight: 600;
}

a {
    color: #2c3e50;
    text-decoration: none;
}

/* Contact info line */
h1 + p, h1 + p + p {
    font-size: 9.5pt;
    color: #555;
    margin: 1pt 0;
}

/* Table styling for certs/skills */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 4pt 0;
    font-size: 10pt;
}

th, td {
    text-align: left;
    padding: 2pt 6pt;
    border-bottom: 0.5pt solid #ecf0f1;
}

th {
    font-weight: 600;
    color: #2c3e50;
}

hr {
    border: none;
    border-top: 0.75pt solid #bdc3c7;
    margin: 8pt 0;
}
"""

COVER_LETTER_CSS = """
@page {
    size: letter;
    margin: 1in;
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #1a1a1a;
}

h1 {
    font-size: 14pt;
    font-weight: 700;
    margin: 0 0 6pt 0;
}

p {
    margin: 0 0 10pt 0;
}

strong {
    font-weight: 600;
}

a {
    color: #2c3e50;
    text-decoration: none;
}

hr {
    border: none;
    border-top: 0.75pt solid #bdc3c7;
    margin: 12pt 0;
}
"""


def md_to_pdf(md_path: Path, output_path: Path = None):
    """Convert a markdown file to PDF."""
    content = md_path.read_text(encoding="utf-8")
    
    # Strip template comments (<!-- ... -->)
    import re
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Convert markdown to HTML
    html_body = markdown.markdown(
        content, 
        extensions=['tables', 'meta', 'sane_lists']
    )
    
    # Pick CSS based on filename
    is_cover_letter = 'cover' in md_path.stem.lower()
    css = COVER_LETTER_CSS if is_cover_letter else RESUME_CSS
    
    # Full HTML document
    html_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{css}</style></head>
<body>{html_body}</body>
</html>"""
    
    # Output path
    if output_path is None:
        output_path = md_path.with_suffix('.pdf')
    
    # Generate PDF
    HTML(string=html_doc).write_pdf(str(output_path))
    print(f"✓ Generated: {output_path}")
    print(f"  Source:    {md_path}")
    print(f"  Size:     {output_path.stat().st_size / 1024:.1f} KB")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Convert markdown to ATS-friendly PDF")
    parser.add_argument("input", help="Path to markdown file")
    parser.add_argument("--output", "-o", help="Output PDF path (default: same name, .pdf extension)")
    args = parser.parse_args()
    
    md_path = Path(args.input)
    if not md_path.exists():
        print(f"Error: {md_path} not found")
        sys.exit(1)
    
    output_path = Path(args.output) if args.output else None
    md_to_pdf(md_path, output_path)


if __name__ == "__main__":
    main()
