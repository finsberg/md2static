import responses
from unittest.mock import patch, MagicMock

# Adjust this import based on your actual package structure
from md2static.cli import get_github_html, convert_md_to_static, main

### 1. Test the GitHub API Interaction ###


@responses.activate
def test_get_github_html():
    """Test that the GitHub API is called correctly and wraps the HTML."""
    markdown_input = "# Hello World"
    mock_html_response = "<h1>Hello World</h1>"

    # Mock the GitHub API response
    responses.add(
        responses.POST,
        "https://api.github.com/markdown",
        body=mock_html_response,
        status=200,
    )

    result = get_github_html(markdown_input)

    # Verify the API was called exactly once
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == "https://api.github.com/markdown"

    # Verify the wrapper template applied correctly
    assert mock_html_response in result
    assert "github-markdown-light.min.css" in result
    assert "<title>Markdown Export</title>" in result


### 2. Test File Conversion logic (HTML) ###


def test_convert_md_to_static_html(tmp_path):
    """Test HTML output bypassing Playwright."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello HTML")
    output_file = tmp_path / "output.html"

    # Mock the API fetcher to avoid real network requests
    with patch(
        "md2static.cli.get_github_html", return_value="<html>Mocked Output</html>"
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
        patch("md2static.cli.get_github_html", return_value="<html>Mocked PDF</html>"),
        patch("md2static.cli.sync_playwright") as mock_playwright,
    ):
        # Setup deep mock for Playwright browser and page objects
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        convert_md_to_static(input_file, output_file)

        # Verify navigation to the temp file happened
        mock_page.goto.assert_called_once()
        assert mock_page.goto.call_args[0][0].startswith("file://")
        assert mock_page.goto.call_args[1]["wait_until"] == "networkidle"

        # Verify PDF method was called with correct parameters
        mock_page.pdf.assert_called_once_with(path=output_file, print_background=True)
        mock_browser.close.assert_called_once()


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
