#!/usr/bin/env python3
"""
更新微信草稿（draft/update），用于返工后替换草稿内容
stdin JSON:
  {
    "wechat_account_id": "wxoa_main",
    "media_id": "DRAFT_MEDIA_ID",
    "index": 0,
    "title": "新标题",
    "author": "作者",
    "digest": "摘要",
    "content": "<html>...</html>",
    "content_source_url": "",
    "thumb_media_id": "NEW_MEDIA_ID"
  }
stdout JSON:
  {"success": true, "data": {}}
"""
import sys, json, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail
import subprocess

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

def main():
    inp = read_stdin()
    for f in ["wechat_account_id", "media_id", "content", "thumb_media_id"]:
        if not inp.get(f):
            fail("invalid_param", f"'{f}' is required")

    account_id = inp["wechat_account_id"]
    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    article = {
        "title":              inp.get("title", ""),
        "author":             inp.get("author", ""),
        "digest":             inp.get("digest", ""),
        "content":            inp["content"],
        "content_source_url": inp.get("content_source_url", ""),
        "thumb_media_id":     inp["thumb_media_id"],
    }
    payload = json.dumps({
        "media_id": inp["media_id"],
        "index":    inp.get("index", 0),
        "articles": article,
    }, ensure_ascii=False).encode("utf-8")

    url = f"https://api.weixin.qq.com/cgi-bin/draft/update?access_token={token}"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        fail("wechat_draft_update_failed", str(e))

    if result.get("errcode", 0) != 0:
        fail("wechat_draft_update_failed",
             f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}",
             result)

    ok({})

if __name__ == "__main__":
    main()
