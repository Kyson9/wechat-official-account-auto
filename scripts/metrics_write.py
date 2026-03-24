#!/usr/bin/env python3
"""
写入发布后数据指标（content_metrics）
stdin JSON:
  {
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "article_id": "ART_001",
    "view_count": 10000,
    "share_count": 100,
    "favorite_count": 50,
    "like_count": 80,
    "comment_count": 9
  }
stdout JSON:
  {"success": true, "data": {"metrics_id": "cm_..."}}
"""
import sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc

def main():
    inp = read_stdin()
    if not inp.get("task_id"):
        fail("invalid_param", "task_id is required")

    cm_id = f"cm_{uuid.uuid4().hex[:12]}"
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO content_metrics
                (id, task_id, content_version_id, article_id,
                 view_count, share_count, favorite_count,
                 like_count, comment_count, captured_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            cm_id,
            inp["task_id"],
            inp.get("content_version_id"),
            inp.get("article_id"),
            inp.get("view_count", 0),
            inp.get("share_count", 0),
            inp.get("favorite_count", 0),
            inp.get("like_count", 0),
            inp.get("comment_count", 0),
            now_utc()
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"metrics_id": cm_id})

if __name__ == "__main__":
    main()
