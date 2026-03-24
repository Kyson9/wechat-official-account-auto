#!/usr/bin/env python3
"""
状态机：验证并执行状态跳转
stdin JSON:
  {"task_id": "wt_...", "to_status": "normalized"}
stdout JSON:
  {"success": true, "data": {"task_id": "...", "from_status": "...", "to_status": "..."}}
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc

# 合法状态流转表（from -> [allowed_to...]）
TRANSITIONS = {
    "received":                ["normalized", "cancelled", "failed_input"],
    "normalized":              ["researching", "cancelled"],
    "researching":             ["research_done", "cancelled"],
    "research_done":           ["planning", "cancelled"],
    "planning":                ["drafting", "cancelled"],
    "drafting":                ["draft_generated", "cancelled"],
    "draft_generated":         ["reviewing", "cancelled"],
    "reviewing":               ["review_passed", "review_failed", "human_review_pending", "cancelled"],
    "review_failed":           ["researching", "planning", "drafting", "reviewing", "cancelled"],
    "review_passed":           ["assets_preparing", "cancelled"],
    "assets_preparing":        ["draft_saving", "cancelled"],
    "draft_saving":            ["draft_saved", "cancelled"],
    "draft_saved":             ["human_review_pending", "cancelled"],
    "human_review_pending":    ["human_review_approved", "human_review_rejected", "cancelled"],
    "human_review_rejected":   ["researching", "planning", "drafting", "reviewing", "cancelled"],
    "human_review_approved":   ["scheduled", "publishing", "cancelled"],
    "scheduled":               ["publishing", "cancelled"],
    "publishing":              ["publish_polling", "publish_failed", "cancelled"],
    "publish_polling":         ["published", "publish_failed"],
    "published":               ["archived"],
    "publish_failed":          ["publishing", "cancelled"],
    # 终态：不允许任何跳转
    "archived":  [],
    "cancelled": [],
    "failed_input": [],
}

def main():
    inp = read_stdin()
    task_id = inp.get("task_id", "").strip()
    to_status = inp.get("to_status", "").strip()

    if not task_id or not to_status:
        fail("invalid_param", "task_id and to_status are required")

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM writing_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            fail("task_not_found", f"task_id '{task_id}' not found")

        from_status = row["status"]

        allowed = TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            fail("invalid_status_transition",
                 f"Cannot transition from '{from_status}' to '{to_status}'",
                 {"from": from_status, "to": to_status, "allowed": allowed})

        now = now_utc()
        conn.execute(
            "UPDATE writing_tasks SET status=?, current_step=?, updated_at=? WHERE id=?",
            (to_status, to_status, now, task_id)
        )
        conn.commit()
    except SystemExit:
        raise
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"task_id": task_id, "from_status": from_status, "to_status": to_status})

if __name__ == "__main__":
    main()
