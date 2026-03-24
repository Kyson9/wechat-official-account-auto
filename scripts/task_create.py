#!/usr/bin/env python3
"""
创建写作任务
stdin JSON:
  {
    "topic": "string（必填）",
    "external_task_id": "string（选填）",
    "goal": "string", "audience": "string", "brand_voice": "string",
    "must_include": [], "must_avoid": [],
    "reference_materials": [],
    "publish_preference": {"mode": "manual|scheduled|auto_best_time", "scheduled_at": null},
    "kpi_target": {"read_target": 10000},
    "wechat_account_id": "string（选填，默认用 config 中的）"
  }
stdout JSON:
  {"success": true, "data": {"task_id": "wt_...", "status": "received"}}
"""
import sys, json, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc, CFG

def main():
    inp = read_stdin()

    topic = inp.get("topic", "").strip()
    if not topic:
        fail("invalid_param", "topic is required")

    cfg_defaults = CFG.get("task_defaults", {})
    account_id = inp.get("wechat_account_id") or cfg_defaults.get("wechat_account_id", "wxoa_main")

    # 验证账号存在
    if account_id not in CFG.get("wechat_accounts", {}):
        fail("invalid_param", f"wechat_account_id '{account_id}' not configured in config.yml")

    pub_pref = inp.get("publish_preference", {})
    publish_mode = pub_pref.get("mode") or cfg_defaults.get("publish_mode", "manual")
    scheduled_at = pub_pref.get("scheduled_at")
    read_target = inp.get("kpi_target", {}).get("read_target") or cfg_defaults.get("kpi_read_target", 10000)
    brand_voice = inp.get("brand_voice") or cfg_defaults.get("brand_voice", "")

    # 生成 task_id
    ts = now_utc().replace("-", "").replace(":", "").replace("T", "")[:12]
    uid = uuid.uuid4().hex[:6]
    task_id = f"wt_{ts}_{uid}"

    now = now_utc()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO writing_tasks (
                id, external_task_id, source_type, source_payload_json,
                topic, goal, audience, brand_voice,
                status, current_step, priority,
                wechat_account_id, target_read_count,
                publish_mode, scheduled_publish_at,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            task_id,
            inp.get("external_task_id"),
            "api",
            json.dumps(inp, ensure_ascii=False),
            topic,
            inp.get("goal"),
            inp.get("audience"),
            brand_voice,
            "received",
            "received",
            50,
            account_id,
            read_target,
            publish_mode,
            scheduled_at,
            now, now
        ))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({"task_id": task_id, "status": "received"})

if __name__ == "__main__":
    main()
