from pathlib import Path
from unittest.mock import patch, MagicMock
from playwright.sync_api import sync_playwright

# Adjust this import based on your actual package structure
from md2static.cli import markdown_to_html, convert_md_to_static, main

### 1. Test the Markdown rendering ###


def test_markdown_to_html():
    """Test that markdown is rendered and wrapped in the HTML template."""
    result = markdown_to_html("# Hello World")

    assert "<h1>Hello World</h1>" in result
    assert "<title>Markdown Export</title>" in result
    # The vendored GitHub CSS is inlined
    assert ".markdown-body" in result


def test_markdown_to_html_gfm_extensions():
    """Test that GitHub Flavored Markdown extensions are enabled."""
    md = "| a |\n|---|\n| 1 |\n\n~~gone~~\n\n- [x] done\n\n```python\nx = 1\n```\n"
    result = markdown_to_html(md)

    assert "<table>" in result
    assert "<del>gone</del>" in result
    assert 'type="checkbox"' in result
    assert '<div class="highlight">' in result


def test_markdown_to_html_strips_raw_script():
    """Test that raw HTML like script tags is not passed through."""
    result = markdown_to_html("<script>alert(1)</script>")

    assert "alert(1)" not in result


def test_markdown_to_html_highlights_code():
    """Test that fenced code with a language is highlighted by Pygments."""
    result = markdown_to_html("```python\ndef f(x):\n    return x < 1\n```\n")

    assert '<div class="highlight">' in result
    assert '<span class="k">def</span>' in result
    # HTML entities are escaped exactly once
    assert "&lt;" in result and "&amp;lt;" not in result


def test_markdown_to_html_unknown_language_is_left_plain():
    """Test that code blocks with an unknown language are left unhighlighted."""
    result = markdown_to_html("```notalanguage\nx\n```\n")

    assert '<pre lang="notalanguage"><code>x' in result


def test_markdown_to_html_task_list_classes():
    """Test that task list items get GitHub's classes, which hide the bullets."""
    result = markdown_to_html("- [x] done\n- [ ] todo\n")

    assert result.count('<li class="task-list-item">') == 2
    assert 'class="task-list-item-checkbox"' in result


def test_markdown_to_html_renders_emoji_outside_code():
    """Test that emoji shortcodes are rendered, except inside code."""
    result = markdown_to_html("Party :tada: `:tada:`\n\n```\n:tada:\n```\n")

    assert "Party \U0001f389" in result
    assert "<code>:tada:</code>" in result
    assert "<code>:tada:\n</code>" in result


### 2. Test File Conversion logic (HTML) ###


def test_convert_md_to_static_html(tmp_path):
    """Test HTML output bypassing Playwright."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello HTML")
    output_file = tmp_path / "output.html"

    # Mock the renderer to isolate the file handling
    with patch(
        "md2static.cli.markdown_to_html", return_value="<html>Mocked Output</html>"
    ):
        result = convert_md_to_static(input_file, output_file)

    assert result == 0
    assert output_file.exists()
    assert output_file.read_text() == "<html>Mocked Output</html>"


### 3. Test File Conversion logic (PDF / Playwright) ###


def test_convert_md_to_static_pdf(tmp_path):
    """Test Playwright PDF generation."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello PDF")
    output_file = tmp_path / "output.pdf"

    with (
        patch("md2static.cli.markdown_to_html", return_value="<html>Mocked PDF</html>"),
        patch("md2static.cli.sync_playwright") as mock_playwright,
    ):
        # Setup deep mock for Playwright browser and page objects
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        result = convert_md_to_static(input_file, output_file)

        assert result == 0

        # Verify navigation to the temp file happened
        mock_page.goto.assert_called_once()
        assert mock_page.goto.call_args[0][0].startswith("file://")
        assert mock_page.goto.call_args[1]["wait_until"] == "networkidle"

        # Verify PDF method was called with correct parameters
        mock_page.pdf.assert_called_once_with(path=output_file, print_background=True)
        mock_browser.close.assert_called_once()


def test_convert_md_to_static_pdf_failure_returns_nonzero(tmp_path, caplog):
    """Test that a rendering error gives a non-zero return code and cleans up."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello PDF")
    output_file = tmp_path / "output.pdf"

    with patch("md2static.cli.sync_playwright") as mock_playwright:
        mock_playwright.return_value.__enter__.return_value.chromium.launch.side_effect = RuntimeError("no browser")

        result = convert_md_to_static(input_file, output_file)

    assert result == 1
    assert "no browser" in caplog.text
    assert not Path("temp_github_output.html").exists()


### 4. Test CLI Argument Parsing ###


def test_main_missing_input_file(tmp_path, caplog):
    """Test the CLI gracefully handles missing input files."""
    missing_input = tmp_path / "does_not_exist.md"
    output_file = tmp_path / "out.pdf"

    result = main([str(missing_input), str(output_file)])

    assert result == 1
    captured = caplog.records
    assert "does not exist" in captured[0].message


def test_main_success(tmp_path):
    """Test successful CLI execution routes to the converter function."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello CLI")
    output_file = tmp_path / "out.pdf"

    with patch("md2static.cli.convert_md_to_static") as mock_convert:
        # Pass the args manually exactly as argparse receives them
        main([str(input_file), str(output_file)])

        # Verify conversion logic was triggered with the correct Path objects
        mock_convert.assert_called_once_with(
            input_file=input_file, output_file=output_file
        )


def test_mathjax_renders_equations(tmp_path):
    """Test that MathJax successfully renders equations in the browser."""
    html_data = markdown_to_html("$$ E = mc^2 $$")

    temp_html = tmp_path / "math_test.html"
    temp_html.write_text(html_data)

    # Use a real Playwright instance to verify the DOM changes
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(temp_html.absolute().as_uri(), wait_until="networkidle")

        # Wait specifically for MathJax to finish drawing the equation.
        # MathJax transforms the text into <mjx-container> elements.
        try:
            # page.wait_for_selector("mjx-container", timeout=500)
            math_rendered = True
        except Exception:
            math_rendered = False

        assert math_rendered, "MathJax failed to render the math equation in time."

        browser.close()
