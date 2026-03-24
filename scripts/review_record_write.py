#!/usr/bin/env python3
"""
写入审核记录（review_records）
stdin JSON:
  {
    "task_id": "wt_...",
    "content_version_id": "cv_...",
    "review_type": "auto|human",
    "reviewer_type": "review_agent|editor|...",
    "decision": "approved|revise|human_escalation",
    "comments": {
      "reason_codes": [],
      "items": [{"section": "title", "comment": "..."}]
    }
  }
stdout JSON:
  {"success": true, "data": {"review_record_id": "rv_..."}}
"""
import sys, json, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc

VALID_DECISIONS = {"approved", "revise", "human_escalation"}

def main():
    inp = read_stdin()
    for f in ["task_id", "review_type", "decision"]:
        if not inp.get(f):
            fail("invalid_param", f"'{f}' is required")

    decision = inp["decision"]
    if decision not in VALID_DECISIONS:
        fail("invalid_param", f"decision must be one of {VALID_DECISIONS}")

    rv_id = f"rv_{uuid.uuid4().hex[:12]}"
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO review_records
                (id, task_id, content_version_id, review_type,
                 reviewer_type, decision, comments_json, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            rv_id,
            inp["task_id"],
            inp.get("content_version_id"),
            inp["review_type"],
            inp.get("reviewer_type"),
            decision,
            json.dumps(inp.get("comments", {}), ensure_ascii=False),
            now_utc()
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"review_record_id": rv_id})

if __name__ == "__main__":
    main()
