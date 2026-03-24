#!/usr/bin/env python3
"""
记录步骤完成（更新 task_steps）
stdin JSON:
  {
    "step_id": "step_...",
    "status": "success|retryable_error|fatal_error|skipped|cancelled",
    "output_snapshot": {},
    "error_snapshot": {}
  }
stdout JSON:
  {"success": true, "data": {}}
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc

VALID_STATUSES = {"success", "retryable_error", "fatal_error", "skipped", "cancelled"}

def main():
    inp = read_stdin()
    step_id = inp.get("step_id", "").strip()
    status  = inp.get("status", "").strip()

    if not step_id or not status:
        fail("invalid_param", "step_id and status are required")
    if status not in VALID_STATUSES:
        fail("invalid_param", f"status must be one of {VALID_STATUSES}")

    conn = get_db()
    try:
        conn.execute("""
            UPDATE task_steps
            SET status=?, output_snapshot_json=?, error_snapshot_json=?, finished_at=?
            WHERE id=?
        """, (
            status,
            json.dumps(inp.get("output_snapshot", {}), ensure_ascii=False),
            json.dumps(inp.get("error_snapshot", {}), ensure_ascii=False) if inp.get("error_snapshot") else None,
            now_utc(),
            step_id
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({})

if __name__ == "__main__":
    main()
