#!/usr/bin/env python3
"""
提交微信发布（freepublish/submit），写入 wechat_publish_jobs 表
stdin JSON:
  {
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "wechat_account_id": "wxoa_main",
    "media_id": "DRAFT_MEDIA_ID",
    "idempotency_key": "sha256_...",
    "scheduled_at": "ISO8601|null"
  }
stdout JSON:
  {"success": true, "data": {"publish_id": "PUBLISH_JOB_ID"}}
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
    for f in ["task_id", "content_version_id", "wechat_account_id", "media_id", "idempotency_key"]:
        if not inp.get(f):
            fail("invalid_param", f"'{f}' is required")

    account_id = inp["wechat_account_id"]
    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    submit_payload = {"media_id": inp["media_id"]}
    payload_bytes = json.dumps(submit_payload, ensure_ascii=False).encode("utf-8")

    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={token}"
    req = urllib.request.Request(url, data=payload_bytes,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        fail("wechat_publish_submit_failed", str(e))

    if result.get("errcode", 0) != 0:
        fail("wechat_publish_submit_failed",
             f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}",
             result)

    publish_id = result.get("publish_job_id", "")
    if not publish_id:
        fail("wechat_publish_submit_failed", "publish_job_id not returned", result)

    # 写入 wechat_publish_jobs
    now = now_utc()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO wechat_publish_jobs
                (id, task_id, content_version_id, media_id, publish_id,
                 scheduled_at, submit_payload_json, submit_response_json,
                 publish_status, idempotency_key, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            f"wp_{uuid.uuid4().hex[:12]}",
            inp["task_id"], inp["content_version_id"],
            inp["media_id"], publish_id,
            inp.get("scheduled_at"),
            json.dumps(submit_payload, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            "polling",
            inp["idempotency_key"],
            now, now
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"publish_id": publish_id})

if __name__ == "__main__":
    main()
