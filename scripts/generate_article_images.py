#!/usr/bin/env python3
"""
Bridge script: generate article images via openai-image-gen skill.

Wraps the OpenAI image generation skill for the WeChat article workflow.
Generates images based on prompts from the article's cover_plan or
explicit image_prompts, outputs them to data/tmp/ for downstream
processing by prepare_article_images.py and wechat_upload_img.py.

Prerequisites:
  - OPENAI_API_KEY environment variable must be set
  - python3 must be available

stdin JSON:
  {
    "prompts": [
      {"id": "cover", "prompt": "描述封面图的生成提示词", "size": "1024x1024"},
      {"id": "img1",  "prompt": "描述配图1的生成提示词"},
      {"id": "img2",  "prompt": "描述配图2的生成提示词"}
    ],
    "model": "gpt-image-1",          // optional, default: gpt-image-1
    "quality": "high",               // optional, default: high
    "size": "1024x1024",             // optional, global default size
    "output_format": "jpeg",         // optional, default: jpeg (微信兼容)
    "out_dir": "./data/tmp"          // optional, default: ./data/tmp
  }

stdout JSON:
  {
    "success": true,
    "data": {
      "images": [
        {"id": "cover", "prompt": "...", "local_path": "/abs/path/cover.jpg"},
        {"id": "img1",  "prompt": "...", "local_path": "/abs/path/img1.jpg"},
        {"id": "img2",  "prompt": "...", "local_path": "/abs/path/img2.jpg"}
      ],
      "out_dir": "/abs/path/to/output"
    }
  }
"""
import sys
import json
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail

# Path to the openai-image-gen skill script
SKILL_SCRIPT = os.path.expanduser(
    "~/.npm-global/lib/node_modules/openclaw/skills/openai-image-gen/scripts/gen.py"
)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "tmp"


def main():
    inp = read_stdin()

    # Validate OPENAI_API_KEY
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        fail(
            "missing_api_key",
            "OPENAI_API_KEY environment variable is not set. "
            "Please set it before generating images. "
            "Get your key from https://platform.openai.com/api-keys",
        )

    # Validate skill script exists
    if not os.path.exists(SKILL_SCRIPT):
        fail(
            "skill_not_found",
            f"openai-image-gen skill script not found at {SKILL_SCRIPT}. "
            "Install it via: npx clawhub install openai-image-gen",
        )

    prompts = inp.get("prompts", [])
    if not prompts:
        fail("invalid_param", "prompts array is required and must not be empty")

    model = inp.get("model", "gpt-image-1")
    quality = inp.get("quality", "high")
    global_size = inp.get("size", "1024x1024")
    output_format = inp.get("output_format", "jpeg")
    out_dir = Path(inp.get("out_dir", str(DEFAULT_OUT_DIR)))
    out_dir.mkdir(parents=True, exist_ok=True)

    images = []

    for item in prompts:
        prompt_id = item.get("id", f"img{len(images)+1}")
        prompt_text = item.get("prompt", "")
        size = item.get("size", global_size)

        if not prompt_text:
            fail("invalid_param", f"Prompt text is empty for id={prompt_id}")

        # Build command
        out_file_stem = prompt_id
        item_out_dir = str(out_dir)

        cmd = [
            sys.executable,
            SKILL_SCRIPT,
            "--prompt", prompt_text,
            "--count", "1",
            "--model", model,
            "--size", size,
            "--quality", quality,
            "--out-dir", item_out_dir,
        ]

        if output_format and model.startswith("gpt-image"):
            cmd.extend(["--output-format", output_format])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "OPENAI_API_KEY": api_key},
            )
        except subprocess.TimeoutExpired:
            fail("timeout", f"Image generation timed out for prompt id={prompt_id}")
        except Exception as e:
            fail("exec_error", f"Failed to run gen.py for id={prompt_id}: {e}")

        if result.returncode != 0:
            fail(
                "generation_failed",
                f"Image generation failed for id={prompt_id}: {result.stderr}",
            )

        # Find the generated file (gen.py names it 001-<slug>.<ext>)
        ext = output_format if output_format else "png"
        generated_files = sorted(
            Path(item_out_dir).glob(f"001-*.{ext}"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not generated_files:
            # Try all image extensions as fallback
            for try_ext in ["jpeg", "jpg", "png", "webp"]:
                generated_files = sorted(
                    Path(item_out_dir).glob(f"001-*.{try_ext}"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                if generated_files:
                    ext = try_ext
                    break

        if not generated_files:
            fail(
                "output_not_found",
                f"Generated image file not found in {item_out_dir} for id={prompt_id}",
            )

        src_path = generated_files[0]
        # Rename to a clean name: <id>.<ext>
        dest_path = out_dir / f"{prompt_id}.{ext}"
        src_path.rename(dest_path)

        images.append({
            "id": prompt_id,
            "prompt": prompt_text,
            "local_path": str(dest_path.resolve()),
        })

    # Clean up gen.py artifacts (prompts.json, index.html) if present
    for artifact in ["prompts.json", "index.html"]:
        artifact_path = out_dir / artifact
        if artifact_path.exists():
            try:
                artifact_path.unlink()
            except OSError:
                pass

    ok({"images": images, "out_dir": str(out_dir.resolve())})


if __name__ == "__main__":
    main()
