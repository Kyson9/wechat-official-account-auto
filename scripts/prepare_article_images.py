#!/usr/bin/env python3
"""
Prepare article images for WeChat: resolve local image refs from markdown,
convert SVGs to JPEG, inject <img> tags into wechat_html.

stdin JSON:
  {
    "draft_markdown": "...",
    "wechat_html": "<html>...",
    "content_dir": "/path/to/sandbox"   # where assets/ lives
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "wechat_html": "<html>...<img src='file:///...'/>...",
      "image_map": [
        {"markdown_ref": "assets/diagram.svg", "local_path": "/abs/path/diagram.jpg"}
      ]
    }
  }
"""
import sys, json, re, os, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, CFG

TEMP_DIR = Path(__file__).parent.parent / CFG.get("paths", {}).get("temp_dir", "data/tmp")


def extract_markdown_images(markdown: str) -> list:
    """Extract image references from markdown: ![alt](path)
    Returns list of (alt, src) tuples."""
    return re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', markdown)


def convert_svg_to_jpeg(svg_path: str, output_dir: str) -> str:
    """Convert SVG to JPEG using sips."""
    out_path = os.path.join(output_dir, Path(svg_path).stem + ".jpg")
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", svg_path, "--out", out_path],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {svg_path}: {result.stderr}")
    return out_path


def build_img_tag(local_path: str, alt: str = "") -> str:
    """Build an <img> tag with inline styling for WeChat compatibility."""
    # Ensure correct file:// URL: file:///absolute/path (3 slashes total)
    if local_path.startswith("/"):
        file_url = f"file://{local_path}"
    else:
        file_url = f"file:///{local_path}"
    return (
        f'<img src="{file_url}" '
        f'alt="{alt}" '
        f'style="max-width:100%;height:auto;display:block;margin:20px auto;" />'
    )


def inject_images_into_html(wechat_html: str, images: list, markdown: str) -> str:
    """
    Inject <img> tags into wechat_html based on position context from markdown.

    images: list of (alt, src, local_path) tuples.

    Strategy: For each image in the markdown, find the text before and after it,
    then locate the corresponding position in HTML and insert the <img> tag.
    """
    if not images:
        return wechat_html

    result_html = wechat_html

    for alt, src, local_path in images:
        img_pattern = f'![{alt}]({src})'
        img_idx = markdown.find(img_pattern)
        if img_idx == -1:
            continue

        img_tag = build_img_tag(local_path, alt)

        # Get text before image (last non-empty line before the image)
        before_text = markdown[:img_idx].rstrip()
        before_lines = [l.strip() for l in before_text.split('\n') if l.strip()]

        # Get text after image (first non-empty line after the image)
        after_text = markdown[img_idx + len(img_pattern):].lstrip()
        after_lines = [l.strip() for l in after_text.split('\n') if l.strip()]

        inserted = False

        # Strategy 1: find HTML element containing "before" text, insert after it
        if before_lines and not inserted:
            search_text = re.sub(r'[#*_`\[\]()]', '', before_lines[-1]).strip()
            search_text = search_text[:50]

            if search_text and search_text in result_html:
                pos = result_html.find(search_text)
                close_match = re.search(r'</(?:p|h[1-6]|section|div)>', result_html[pos:])
                if close_match:
                    insert_pos = pos + close_match.end()
                    result_html = result_html[:insert_pos] + img_tag + result_html[insert_pos:]
                    inserted = True

        # Strategy 2: find HTML element containing "after" text, insert before it
        if after_lines and not inserted:
            search_text = re.sub(r'[#*_`\[\]()]', '', after_lines[0]).strip()
            search_text = search_text[:50]

            if search_text and search_text in result_html:
                pos = result_html.find(search_text)
                before_html = result_html[:pos]
                open_match = re.search(r'<(?:p|h[1-6]|section|div)[^>]*>(?=[^<]*$)', before_html)
                if open_match:
                    insert_pos = open_match.start()
                    result_html = result_html[:insert_pos] + img_tag + result_html[insert_pos:]
                    inserted = True

        # Fallback: append at end
        if not inserted:
            result_html += img_tag

    return result_html


def main():
    inp = read_stdin()
    draft_markdown = inp.get("draft_markdown", "")
    wechat_html = inp.get("wechat_html", "")
    content_dir = inp.get("content_dir", "")

    if not content_dir:
        fail("invalid_param", "content_dir is required")

    # Extract image references from markdown
    md_images = extract_markdown_images(draft_markdown)

    if not md_images:
        ok({"wechat_html": wechat_html, "image_map": []})

    # Filter to only local images (skip HTTP URLs)
    local_images = [(alt, src) for alt, src in md_images if not src.startswith("http")]

    if not local_images:
        ok({"wechat_html": wechat_html, "image_map": []})

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    image_map = []
    images_with_paths = []

    for alt, src in local_images:
        # Resolve local path
        local_path = os.path.join(content_dir, src)
        if not os.path.exists(local_path):
            fail("file_not_found", f"Image not found: {local_path}")

        # Convert SVG to JPEG
        if local_path.lower().endswith(".svg"):
            try:
                jpeg_path = convert_svg_to_jpeg(local_path, str(TEMP_DIR))
                image_map.append({"markdown_ref": src, "local_path": jpeg_path})
                images_with_paths.append((alt, src, jpeg_path))
            except Exception as e:
                fail("svg_conversion_failed", f"Failed to convert {src}: {e}")
        else:
            # Non-SVG local files: use absolute path directly
            abs_path = os.path.abspath(local_path)
            image_map.append({"markdown_ref": src, "local_path": abs_path})
            images_with_paths.append((alt, src, abs_path))

    # Inject images into HTML
    updated_html = inject_images_into_html(wechat_html, images_with_paths, draft_markdown)

    ok({"wechat_html": updated_html, "image_map": image_map})


if __name__ == "__main__":
    main()
