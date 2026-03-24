#!/usr/bin/env python3
"""
断点续跑：找到最后一个稳定节点，重建上下文快照
stdin JSON:
  {"task_id": "wt_..."}
stdout JSON:
  {
    "success": true,
    "data": {
      "task_id": "...",
      "current_status": "...",
      "stable_node": "draft_saved",
      "resume_from_step": "human_review_pending",
      "context": { ...上一稳定节点的 output_snapshot }
    }
  }
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db

# 稳定节点（可安全恢复的节点，按流程顺序排列）
STABLE_NODES = [
    "normalized",
    "research_done",
    "draft_generated",
    "review_passed",
    "draft_saved",
    "human_review_approved",
    "published",
]

# 稳定节点 -> 下一步应该执行的步骤
NEXT_STEP = {
    "normalized":             "researching",
    "research_done":          "planning",
    "draft_generated":        "reviewing",
    "review_passed":          "assets_preparing",
    "draft_saved":            "human_review_pending",
    "human_review_approved":  "publishing",
    "published":              "archived",
}

def main():
    inp = read_stdin()
    task_id = inp.get("task_id", "").strip()
    if not task_id:
        fail("invalid_param", "task_id is required")

    conn = get_db()
    try:
        task = conn.execute(
            "SELECT status FROM writing_tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not task:
            fail("task_not_found", f"task_id '{task_id}' not found")

        current_status = task["status"]

        # 找最后一个成功的稳定节点
        stable_node = None
        context = {}
        for node in reversed(STABLE_NODES):
            row = conn.execute("""
                SELECT output_snapshot_json FROM task_steps
                WHERE task_id=? AND step_name=? AND status='success'
                ORDER BY finished_at DESC LIMIT 1
            """, (task_id, node)).fetchone()
            if row:
                stable_node = node
                try:
                    context = json.loads(row["output_snapshot_json"] or "{}")
                except Exception:
                    context = {}
                break
    except SystemExit:
        raise
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    if not stable_node:
        ok({
            "task_id": task_id,
            "current_status": current_status,
            "stable_node": None,
            "resume_from_step": "normalize",
            "context": {}
        })
    else:
        ok({
            "task_id": task_id,
            "current_status": current_status,
            "stable_node": stable_node,
            "resume_from_step": NEXT_STEP.get(stable_node, stable_node),
            "context": context
        })

if __name__ == "__main__":
    main()
