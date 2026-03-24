#!/usr/bin/env python3
"""
记录步骤开始（写入 task_steps，status=running）
stdin JSON:
  {"task_id": "wt_...", "step_name": "normalize", "input_snapshot": {}}
stdout JSON:
  {"success": true, "data": {"step_id": "step_..."}}
"""
import sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc
import json

def main():
    inp = read_stdin()
    task_id   = inp.get("task_id", "").strip()
    step_name = inp.get("step_name", "").strip()
    if not task_id or not step_name:
        fail("invalid_param", "task_id and step_name are required")

    # 统计该步骤的历史尝试次数
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM task_steps WHERE task_id=? AND step_name=?",
            (task_id, step_name)
        ).fetchone()
        attempt = (row["cnt"] or 0) + 1

        step_id = f"step_{uuid.uuid4().hex[:12]}"
        conn.execute("""
            INSERT INTO task_steps (id, task_id, step_name, status, attempt_count,
                input_snapshot_json, started_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            step_id, task_id, step_name, "running", attempt,
            json.dumps(inp.get("input_snapshot", {}), ensure_ascii=False),
            now_utc()
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"step_id": step_id, "attempt": attempt})

if __name__ == "__main__":
    main()
