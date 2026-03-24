#!/usr/bin/env python3
"""
Convert SVG files to JPEG using macOS sips.
stdin JSON:
  {
    "svg_paths": ["/path/to/file.svg", ...],
    "output_dir": "/path/to/output"
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "converted": [
        {"svg_path": "/path/to/file.svg", "jpeg_path": "/path/to/output/file.jpg"}
      ]
    }
  }
"""
import sys, json, subprocess, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail


def convert_svg_to_jpeg(svg_path: str, output_dir: str) -> str:
    """Convert a single SVG to JPEG using sips. Returns output JPEG path."""
    svg_p = Path(svg_path)
    if not svg_p.exists():
        raise FileNotFoundError(f"SVG file not found: {svg_path}")

    out_path = Path(output_dir) / f"{svg_p.stem}.jpg"
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", str(svg_p), "--out", str(out_path)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed: {result.stderr}")
    if not out_path.exists():
        raise RuntimeError(f"sips produced no output: {out_path}")
    return str(out_path)


def main():
    inp = read_stdin()
    svg_paths = inp.get("svg_paths", [])
    output_dir = inp.get("output_dir", "")

    if not output_dir:
        fail("invalid_param", "output_dir is required")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if not svg_paths:
        ok({"converted": []})

    converted = []
    for svg_path in svg_paths:
        try:
            jpeg_path = convert_svg_to_jpeg(svg_path, output_dir)
            converted.append({"svg_path": svg_path, "jpeg_path": jpeg_path})
        except Exception as e:
            fail("svg_conversion_failed", f"Failed to convert {svg_path}: {e}")

    ok({"converted": converted})


if __name__ == "__main__":
    main()
