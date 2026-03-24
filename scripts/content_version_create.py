#!/usr/bin/env python3
"""
创建内容版本（content_versions）
stdin JSON:
  {
    "task_id": "wt_...",
    "title": "string",
    "summary": "string",
    "outline_json": {},
    "markdown_body": "string",
    "wechat_html": "string",
    "cover_plan_json": {},
    "evidence_pack_json": {},
    "created_by_agent": "writer_agent"
  }
stdout JSON:
  {"success": true, "data": {"content_version_id": "cv_...", "version_no": 2}}
"""
import sys, json, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc

def main():
    inp = read_stdin()
    task_id = inp.get("task_id", "").strip()
    if not task_id:
        fail("invalid_param", "task_id is required")

    conn = get_db()
    try:
        # 获取当前最大版本号
        row = conn.execute(
            "SELECT MAX(version_no) as max_v FROM content_versions WHERE task_id=?",
            (task_id,)
        ).fetchone()
        version_no = (row["max_v"] or 0) + 1

        cv_id = f"cv_{uuid.uuid4().hex[:12]}"
        now = now_utc()

        conn.execute("""
            INSERT INTO content_versions
                (id, task_id, version_no, title, subtitle, summary,
                 outline_json, markdown_body, wechat_html,
                 cover_plan_json, evidence_pack_json,
                 status, created_by_agent, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cv_id, task_id, version_no,
            inp.get("title"),
            inp.get("subtitle"),
            inp.get("summary"),
            json.dumps(inp.get("outline_json", {}), ensure_ascii=False),
            inp.get("markdown_body"),
            inp.get("wechat_html"),
            json.dumps(inp.get("cover_plan_json", {}), ensure_ascii=False),
            json.dumps(inp.get("evidence_pack_json", {}), ensure_ascii=False),
            "draft",
            inp.get("created_by_agent", "writer_agent"),
            now
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"content_version_id": cv_id, "version_no": version_no})

if __name__ == "__main__":
    main()
