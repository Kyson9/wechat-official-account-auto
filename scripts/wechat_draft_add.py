#!/usr/bin/env python3
"""
新增微信草稿（draft/add），写入 wechat_drafts 表
stdin JSON:
  {
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "wechat_account_id": "wxoa_main",
    "payload_hash": "sha256_...",
    "title": "string",
    "author": "string",
    "digest": "string",
    "content": "<html>...</html>",
    "content_source_url": "string",
    "thumb_media_id": "PERMANENT_MEDIA_ID",
    "need_open_comment": 0,
    "only_fans_can_comment": 0
  }
stdout JSON:
  {"success": true, "data": {"media_id": "...", "payload_hash": "..."}}
"""
import sys, json, uuid, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc
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
    required = ["task_id", "content_version_id", "wechat_account_id",
                "payload_hash", "title", "thumb_media_id", "content"]
    for f in required:
        if not inp.get(f):
            fail("invalid_param", f"'{f}' is required")

    account_id = inp["wechat_account_id"]

    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    # 构造 draft/add 请求
    article = {
        "article_type": "news",
        "title":               inp["title"],
        "author":              inp.get("author", ""),
        "digest":              inp.get("digest", ""),
        "content":             inp["content"],
        "content_source_url":  inp.get("content_source_url", ""),
        "thumb_media_id":      inp["thumb_media_id"],
        "need_open_comment":   inp.get("need_open_comment", 0),
        "only_fans_can_comment": inp.get("only_fans_can_comment", 0),
    }
    payload = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")

    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        fail("wechat_draft_add_failed", str(e))

    if result.get("errcode", 0) != 0:
        fail("wechat_draft_add_failed",
             f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}",
             result)

    media_id = result.get("media_id", "")
    if not media_id:
        fail("wechat_draft_add_failed", "media_id not returned by WeChat API", result)

    # 写入 wechat_drafts
    now = now_utc()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO wechat_drafts
                (id, task_id, content_version_id, wechat_account_id,
                 media_id, request_payload_json, response_payload_json,
                 payload_hash, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            f"wd_{uuid.uuid4().hex[:12]}",
            inp["task_id"], inp["content_version_id"], account_id,
            media_id,
            json.dumps({"articles": [article]}, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            inp["payload_hash"],
            "saved", now, now
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"media_id": media_id, "payload_hash": inp["payload_hash"]})

if __name__ == "__main__":
    main()
