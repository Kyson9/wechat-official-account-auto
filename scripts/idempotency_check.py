#!/usr/bin/env python3
"""
幂等键检查：草稿保存 / 发布提交
stdin JSON（草稿）:
  {
    "type": "draft",
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "wechat_account_id": "wxoa_main",
    "wechat_html_hash": "sha256_of_html",
    "thumb_media_id": "MEDIA_ID"
  }
stdin JSON（发布）:
  {
    "type": "publish",
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "media_id": "DRAFT_MEDIA_ID",
    "scheduled_at": "ISO8601|null"
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "exists": true|false,
      "idempotency_key": "sha256_...",
      "cached_result": {"media_id": "..."} | {"publish_id": "..."} | null
    }
  }
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, sha256

def main():
    inp = read_stdin()
    check_type = inp.get("type", "").strip()

    if check_type == "draft":
        key = sha256(
            inp.get("task_id", ""),
            inp.get("content_version_id", ""),
            inp.get("wechat_account_id", ""),
            inp.get("wechat_html_hash", ""),
            inp.get("thumb_media_id", ""),
        )
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT media_id FROM wechat_drafts WHERE payload_hash=? AND status='saved' LIMIT 1",
                (key,)
            ).fetchone()
        finally:
            conn.close()
        if row:
            ok({"exists": True, "idempotency_key": key,
                "cached_result": {"media_id": row["media_id"]}})
        else:
            ok({"exists": False, "idempotency_key": key, "cached_result": None})

    elif check_type == "publish":
        key = sha256(
            inp.get("task_id", ""),
            inp.get("content_version_id", ""),
            inp.get("media_id", ""),
            inp.get("scheduled_at", "") or "",
        )
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT publish_id, publish_status FROM wechat_publish_jobs WHERE idempotency_key=? LIMIT 1",
                (key,)
            ).fetchone()
        finally:
            conn.close()
        if row and row["publish_id"] and row["publish_status"] != "failed":
            ok({"exists": True, "idempotency_key": key,
                "cached_result": {"publish_id": row["publish_id"],
                                  "publish_status": row["publish_status"]}})
        else:
            ok({"exists": False, "idempotency_key": key, "cached_result": None})

    else:
        fail("invalid_param", "type must be 'draft' or 'publish'")

if __name__ == "__main__":
    main()
