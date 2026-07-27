# md2static/cli.py
import argparse
from typing import Sequence
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright


def get_github_html(md_text):
    url = "https://api.github.com/markdown"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    payload = {"text": md_text, "mode": "gfm"}

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    html_content = response.text

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Markdown Export</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown-light.min.css">
        <style>
            body {{
                box-sizing: border-box;
                min-width: 200px;
                max-width: 980px;
                margin: 0 auto;
                padding: 45px;
            }}
        </style>
    </head>
    <body class="markdown-body">
        {html_content}
    </body>
    </html>
    """
    return html_template


def convert_md_to_static(input_file: Path, output_file: Path) -> int:
    md_text = input_file.read_text()

    print(f"Asking GitHub API to render '{input_file}'...")
    try:
        html_data = get_github_html(md_text)
    except Exception as e:
        print(f"Error reaching GitHub API: {e}")
        return 1

    temp_html = Path("temp_github_output.html")
    temp_html.write_text(html_data)
    format_type = output_file.suffix
    if format_type == ".html":
        temp_html.rename(output_file)
        return 0

    print(f"Converting HTML to {format_type.upper()}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            file_url = f"file://{temp_html.absolute().as_posix()}"
            page.goto(file_url, wait_until="networkidle")

            if format_type == ".pdf":
                page.pdf(path=output_file, print_background=True)
            else:
                # Try to take a screenshot
                page.screenshot(path=output_file, full_page=True)

            browser.close()
            print(f"Successfully created '{output_file}'!")

    except Exception as e:
        print(f"Error during rendering: {e}")

    finally:
        temp_html.unlink(missing_ok=True)
        return 0


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Convert Markdown to PDF/Image using GitHub's API."
    )
    parser.add_argument("input", type=Path, help="Path to the input Markdown file")
    parser.add_argument("output", type=Path, help="Path to the output file")

    args = vars(parser.parse_args(argv))
    if not args["input"].is_file():
        print(f"Error: Input file '{args['input']}' does not exist.")
        return 1
    else:
        return convert_md_to_static(
            input_file=args["input"], output_file=args["output"]
        )
