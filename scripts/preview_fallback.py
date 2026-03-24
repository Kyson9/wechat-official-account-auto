#!/usr/bin/env python3
"""
Generate a local HTML preview file for WeChat article.
Wraps the wechat_html in a phone-viewport template for preview.
Produces a static file only — does NOT start any HTTP server.

stdin JSON:
  {
    "wechat_html": "<html>...",
    "title": "Article Title"
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "preview_path": "/abs/path/to/preview.html"
    }
  }
"""
import sys, json, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, CFG

PREVIEW_DIR = Path(__file__).parent.parent / CFG.get("paths", {}).get("temp_dir", "data/tmp")

PREVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - 微信预览</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #f5f5f5;
    display: flex;
    justify-content: center;
    padding: 20px 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }}
  .phone-frame {{
    width: 375px;
    max-width: 100%;
    min-height: 667px;
    background: #fff;
    box-shadow: 0 2px 20px rgba(0,0,0,0.1);
    border-radius: 12px;
    overflow: hidden;
  }}
  .phone-header {{
    background: #333;
    color: #fff;
    padding: 12px 16px;
    font-size: 14px;
    text-align: center;
  }}
  .article-content {{
    padding: 16px;
    font-size: 16px;
    line-height: 1.8;
    color: #333;
    word-wrap: break-word;
  }}
  .article-content img {{
    max-width: 100% !important;
    height: auto !important;
    display: block;
    margin: 12px auto;
  }}
  .preview-banner {{
    background: #07c160;
    color: #fff;
    text-align: center;
    padding: 8px;
    font-size: 12px;
  }}
</style>
</head>
<body>
<div class="phone-frame">
  <div class="preview-banner">📱 微信公众号预览 — 仅供排版检查</div>
  <div class="phone-header">{title}</div>
  <div class="article-content">
    {content}
  </div>
</div>
</body>
</html>"""


def main():
    inp = read_stdin()
    wechat_html = inp.get("wechat_html", "").strip()
    title = inp.get("title", "预览文章")

    if not wechat_html:
        fail("invalid_param", "wechat_html is required")

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # Convert file:// URLs to relative paths for local viewing
    import re
    preview_dir_str = str(PREVIEW_DIR.resolve())
    served_html = wechat_html
    # Replace file:///abs/path/to/data/tmp/foo.jpg → foo.jpg (relative)
    served_html = re.sub(
        r'file://' + re.escape(preview_dir_str) + r'/([^"\'>\s]+)',
        r'\1',
        served_html
    )

    preview_html = PREVIEW_TEMPLATE.format(
        title=title,
        content=served_html
    )

    preview_path = PREVIEW_DIR / "preview.html"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview_html)

    ok({
        "preview_path": str(preview_path.resolve())
    })


if __name__ == "__main__":
    main()
