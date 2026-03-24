#!/usr/bin/env python3
"""
上传封面图为微信永久素材，获取 thumb_media_id
stdin JSON:
  {
    "wechat_account_id": "wxoa_main",
    "cover_image_source": "https://example.com/cover.jpg"
  }
stdout JSON:
  {"success": true, "data": {"thumb_media_id": "PERMANENT_MEDIA_ID"}}
"""
import sys, json, os, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, CFG
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

def download_image(url: str) -> str:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    local_path = TEMP_DIR / f"cover{ext}"
    urllib.request.urlretrieve(url, str(local_path))
    return str(local_path)

def upload_permanent_material(local_path: str, access_token: str) -> str:
    """上传永久素材（图片），返回 media_id"""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    filename = os.path.basename(local_path)

    with open(local_path, "rb") as f:
        file_data = f.read()

    boundary = "----FormBoundary7MA4YWxkCover"
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
        raise RuntimeError(f"add_material error {result['errcode']}: {result.get('errmsg')}")
    return result["media_id"]

def main():
    inp = read_stdin()
    account_id = inp.get("wechat_account_id", "").strip()
    cover_source = inp.get("cover_image_source", "").strip()

    if not account_id:
        fail("invalid_param", "wechat_account_id is required")
    if not cover_source:
        fail("invalid_param", "cover_image_source is required")

    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    try:
        if cover_source.startswith("http"):
            local_file = download_image(cover_source)
        else:
            local_file = cover_source  # 本地路径直接用

        media_id = upload_permanent_material(local_file, token)

        if cover_source.startswith("http"):
            try:
                os.remove(local_file)
            except Exception:
                pass
    except Exception as e:
        fail("wechat_upload_failed", str(e))

    ok({"thumb_media_id": media_id})

if __name__ == "__main__":
    main()
