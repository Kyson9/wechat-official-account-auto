#!/usr/bin/env python3
"""
查询任务详情（含最新内容版本、草稿、发布信息）
stdin JSON:
  {"task_id": "wt_..."}
stdout JSON:
  {"success": true, "data": { ...full task detail }}
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db

STABLE_NODES = ["normalized","research_done","draft_generated",
                "review_passed","draft_saved","human_review_approved","published"]

def main():
    inp = read_stdin()
    task_id = inp.get("task_id", "").strip()
    if not task_id:
        fail("invalid_param", "task_id is required")

    conn = get_db()
    try:
        task = conn.execute(
            "SELECT * FROM writing_tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not task:
            fail("task_not_found", f"task_id '{task_id}' not found")

        # 最新内容版本
        cv = conn.execute("""
            SELECT * FROM content_versions WHERE task_id=?
            ORDER BY version_no DESC LIMIT 1
        """, (task_id,)).fetchone()

        # 草稿
        draft = conn.execute("""
            SELECT * FROM wechat_drafts WHERE task_id=? AND status='saved'
            ORDER BY created_at DESC LIMIT 1
        """, (task_id,)).fetchone()

        # 发布任务
        pub = conn.execute("""
            SELECT * FROM wechat_publish_jobs WHERE task_id=?
            ORDER BY created_at DESC LIMIT 1
        """, (task_id,)).fetchone()

        # 可恢复节点
        resume_points = []
        for node in STABLE_NODES:
            row = conn.execute("""
                SELECT 1 FROM task_steps WHERE task_id=? AND step_name=? AND status='success'
                LIMIT 1
            """, (task_id, node)).fetchone()
            if row:
                resume_points.append(node)

        # 返工计数
        rework_row = conn.execute("""
            SELECT COUNT(*) as cnt FROM review_records
            WHERE task_id=? AND decision='revise'
        """, (task_id,)).fetchone()
        rework_count = rework_row["cnt"] if rework_row else 0

    except SystemExit:
        raise
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    def row_to_dict(row):
        return dict(row) if row else None

    ok({
        "task": row_to_dict(task),
        "latest_content_version": row_to_dict(cv),
        "wechat_draft": row_to_dict(draft),
        "publish_job": row_to_dict(pub),
        "resume_points": resume_points,
        "rework_count": rework_count,
    })

if __name__ == "__main__":
    main()
