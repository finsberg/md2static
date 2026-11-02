import html
import logging
import argparse
import re
from typing import Sequence
from pathlib import Path
from importlib.resources import files
import cmarkgfm
from cmarkgfm.cmark import Options
import emoji
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.style import Style
from pygments.token import (
    Comment,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    String,
)
from pygments.util import ClassNotFound
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


class GitHubLightStyle(Style):
    """Pygments style using the colors of GitHub's light theme."""

    background_color = "#f6f8fa"
    styles = {
        Comment: "#59636e",
        Keyword: "#cf222e",
        Keyword.Constant: "#0550ae",
        Operator.Word: "#cf222e",
        Name.Builtin: "#0550ae",
        Name.Function: "#6639ba",
        Name.Class: "#953800",
        Name.Decorator: "#6639ba",
        Name.Tag: "#116329",
        Name.Attribute: "#0550ae",
        Name.Variable: "#953800",
        Number: "#0550ae",
        String: "#0a3069",
        Generic.Deleted: "#82071e bg:#ffebe9",
        Generic.Inserted: "#116329 bg:#dafbe1",
        Generic.Heading: "bold #0550ae",
        Generic.Emph: "italic",
        Generic.Strong: "bold",
    }


CODE_BLOCK = re.compile(r'<pre lang="([^"]+)"><code>(.*?)</code></pre>', re.DOTALL)
TASK_LIST_ITEM = re.compile(r'<li>(\s*(?:<p>)?)<input type="checkbox"')
CODE_OR_TAG = re.compile(r"(<pre.*?</pre>|<code>.*?</code>|<[^>]*>)", re.DOTALL)


def highlight_code(html_content):
    """Syntax highlight fenced code blocks that specify a language."""

    def replace(match):
        lang, code = match.groups()
        try:
            lexer = get_lexer_by_name(html.unescape(lang))
        except ClassNotFound:
            logger.debug(f"No lexer found for {lang!r}, leaving code block as is")
            return match.group(0)
        return highlight(html.unescape(code), lexer, HtmlFormatter())

    return CODE_BLOCK.sub(replace, html_content)


def add_task_list_classes(html_content):
    """Add the classes GitHub uses so task list items are rendered without bullets."""
    return TASK_LIST_ITEM.sub(
        r'<li class="task-list-item">\1<input type="checkbox" class="task-list-item-checkbox"',
        html_content,
    )


def render_emoji(html_content):
    """Replace emoji shortcodes such as :tada: outside of code and tags."""
    parts = CODE_OR_TAG.split(html_content)
    # Every odd part is a code block or an HTML tag, which we leave untouched
    return "".join(
        part if i % 2 else emoji.emojize(part, language="alias")
        for i, part in enumerate(parts)
    )


def markdown_to_html(md_text):
    # cmark-gfm is the parser GitHub itself uses, so this matches the
    # GitHub API output without needing network access or a token
    logger.debug("Rendering markdown with cmark-gfm")
    html_content = cmarkgfm.github_flavored_markdown_to_html(
        md_text, options=Options.CMARK_OPT_GITHUB_PRE_LANG
    )
    html_content = render_emoji(html_content)
    html_content = add_task_list_classes(html_content)
    html_content = highlight_code(html_content)

    css = (files("md2static") / "static" / "github-markdown-light.css").read_text()
    css += HtmlFormatter(style=GitHubLightStyle).get_style_defs(
        ".markdown-body .highlight"
    )

    # Updated HTML template with MathJax injected
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Markdown Export</title>
        <style>
            {css}
        </style>
        <style>
            body {{
                box-sizing: border-box;
                min-width: 200px;
                max-width: 980px;
                margin: 0 auto;
                padding: 45px;
            }}
        </style>

        <!-- MathJax Configuration -->
        <script>
            MathJax = {{
                tex: {{
                    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
                }},
                svg: {{
                    fontCache: 'global'
                }}
            }};
        </script>
        <!-- MathJax Library -->
        <script type="text/javascript" id="MathJax-script" async
          src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js">
        </script>

    </head>
    <body class="markdown-body">
        {html_content}
    </body>
    </html>
    """
    return html_template


def convert_md_to_static(input_file: Path, output_file: Path) -> int:
    logger.debug(f"Reading {input_file = }")
    md_text = input_file.read_text()

    logger.info(f"Rendering '{input_file}'...")
    html_data = markdown_to_html(md_text)

    format_type = output_file.suffix.lower()
    if format_type == ".html":
        output_file.write_text(html_data)
        return 0

    temp_html = Path("temp_github_output.html")
    logger.debug(f"Writing temporary HTML to {temp_html}")
    temp_html.write_text(html_data)

    logger.info(f"Converting HTML to {format_type.upper()}...")
    try:
        with sync_playwright() as p:
            logger.debug("Launching browser...")
            browser = p.chromium.launch()
            page = browser.new_page()

            file_url = temp_html.absolute().as_uri()
            logger.debug(f"Navigating to {file_url}")
            page.goto(file_url, wait_until="networkidle")

            if format_type == ".pdf":
                logger.debug(f"Saving page as PDF to {output_file}")
                page.pdf(path=output_file, print_background=True)
            else:
                # Try to take a screenshot
                logger.debug(f"Saving page as image to {output_file}")
                page.screenshot(path=output_file, full_page=True)

            browser.close()
            logger.info(f"Successfully created '{output_file}'!")

    except Exception as e:
        logger.error(f"Error during rendering: {e}")
        return 1

    finally:
        temp_html.unlink(missing_ok=True)

    return 0


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Convert Markdown to PDF/Image with GitHub styling."
    )
    parser.add_argument("input", type=Path, help="Path to the input Markdown file")
    parser.add_argument("output", type=Path, help="Path to the output file")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = vars(parser.parse_args(argv))
    if args["verbose"]:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    if not args["input"].is_file():
        logger.error(f"Error: Input file '{args['input']}' does not exist.")
        return 1
    else:
        return convert_md_to_static(
            input_file=args["input"], output_file=args["output"]
        )


# # In cli.py, update the Playwright navigation block:
# page.goto(file_url, wait_until="networkidle")

# # Force Playwright to wait for MathJax to render at least one equation (if math exists)
# # We use a slight timeout or check for the MathJax output container
# try:
#     page.wait_for_selector("mjx-container", timeout=3000)
# except Exception:
#     pass # If there is no math on the page, it will just timeout and continue safely
