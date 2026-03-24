#!/usr/bin/env python3
"""
上传正文图片到微信（uploadimg），替换 wechat_html 中所有外链图片 URL
stdin JSON:
  {
    "wechat_account_id": "wxoa_main",
    "wechat_html": "<p>...<img src='https://...'/>...</p>"
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "wechat_html_replaced": "<p>...<img src='https://mmbiz...'/>...</p>",
      "image_map": [{"original_url": "...", "wechat_url": "..."}]
    }
  }
"""
import sys, json, re, os, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_account_cfg, CFG
import subprocess

TEMP_DIR = Path(__file__).parent.parent / CFG.get("paths", {}).get("temp_dir", "data/tmp")

def get_token(account_id: str) -> str:
    inp = json.dumps({"wechat_account_id": account_id})
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "wechat_token.py")],
        input=inp, capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    if not data.get("success"):
        raise RuntimeError(f"Token error: {data}")
    return data["data"]["access_token"]

def download_image(url: str, dest_path: Path) -> str:
    """下载图片，返回本地路径"""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    local_path = dest_path.with_suffix(ext)
    urllib.request.urlretrieve(url, str(local_path))
    return str(local_path)

def upload_to_wechat(local_path: str, access_token: str) -> str:
    """上传图片到微信 uploadimg，返回微信图片 URL"""
    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    filename = os.path.basename(local_path)

    with open(local_path, "rb") as f:
        file_data = f.read()

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    if "errcode" in result and result["errcode"] != 0:
        raise RuntimeError(f"uploadimg error {result['errcode']}: {result.get('errmsg')}")
    return result["url"]

def main():
    inp = read_stdin()
    account_id = inp.get("wechat_account_id", "").strip()
    html = inp.get("wechat_html", "")

    if not account_id:
        fail("invalid_param", "wechat_account_id is required")

    # 提取所有图片 src
    img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)

    # 分类：外链 HTTP URL vs 本地文件路径
    external_urls = [u for u in img_urls if "mmbiz.qpic.cn" not in u and u.startswith("http")]
    local_urls = []
    for u in img_urls:
        if "mmbiz.qpic.cn" in u or u.startswith("http"):
            continue
        if u.startswith("file://") or u.startswith("/"):
            local_urls.append(u)

    if not external_urls and not local_urls:
        ok({"wechat_html_replaced": html, "image_map": []})

    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    image_map = []
    replaced_html = html

    # 上传外链图片
    for i, orig_url in enumerate(set(external_urls)):
        local_path = TEMP_DIR / f"body_img_{i}"
        try:
            local_file = download_image(orig_url, local_path)
            wechat_url = upload_to_wechat(local_file, token)
            image_map.append({"original_url": orig_url, "wechat_url": wechat_url})
            replaced_html = replaced_html.replace(orig_url, wechat_url)
            # 清理临时文件
            try:
                os.remove(local_file)
            except Exception:
                pass
        except Exception as e:
            fail("wechat_upload_failed", f"Failed to upload {orig_url}: {e}")

    # 上传本地文件
    for orig_ref in set(local_urls):
        local_file = orig_ref
        if local_file.startswith("file://"):
            # file:///path → /path (strip file://)
            local_file = local_file[7:]
            if not local_file.startswith("/"):
                local_file = "/" + local_file

        if not os.path.exists(local_file):
            fail("wechat_upload_failed", f"Local file not found: {local_file}")

        try:
            wechat_url = upload_to_wechat(local_file, token)
            image_map.append({"original_url": orig_ref, "wechat_url": wechat_url})
            replaced_html = replaced_html.replace(orig_ref, wechat_url)
        except Exception as e:
            fail("wechat_upload_failed", f"Failed to upload local file {orig_ref}: {e}")

    ok({"wechat_html_replaced": replaced_html, "image_map": image_map})

if __name__ == "__main__":
    main()
