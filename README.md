# md2static

A lightweight command-line tool that converts Markdown files into static PDFs, Images (PNG/JPEG), or HTML using the official GitHub Markdown API for pixel-perfect styling.

It leverages GitHub's API to parse the Markdown into HTML, wraps it in the official GitHub CSS, and uses a headless browser (Playwright) to capture the styled output.

It is very much inspired by [grip](https://github.com/joeyespo/grip).

## Install
Install with pip, `pipx` or `uv`, e.g
```bash
pip install md2static
```

Note that if you want to output to something different than HTML, then you would also need to install Playwright browser binaries (you only need to do this once), i.e
```bash
playwright install chromium
```

## Example usage
**HTML**
```bash
md2static doc.md output.html
```

**PDF**
```bash
md2static input.md output.pdf
```
**PNG**
```bash
md2static README.md screenshot.png
```

## License
MIT
