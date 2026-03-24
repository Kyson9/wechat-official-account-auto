#!/usr/bin/env python3
"""
初始化数据库：创建所有核心表和索引
用法：python scripts/setup_db.py
输出：JSON 到 stdout
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import get_db, ok, fail, get_logger

log = get_logger("setup_db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS writing_tasks (
    id                    TEXT PRIMARY KEY,
    external_task_id      TEXT,
    source_type           TEXT NOT NULL DEFAULT 'api',
    source_payload_json   TEXT,
    topic                 TEXT NOT NULL,
    goal                  TEXT,
    audience              TEXT,
    brand_voice           TEXT,
    status                TEXT NOT NULL DEFAULT 'received',
    current_step          TEXT NOT NULL DEFAULT 'received',
    priority              INTEGER NOT NULL DEFAULT 50,
    wechat_account_id     TEXT NOT NULL,
    target_read_count     INTEGER NOT NULL DEFAULT 10000,
    publish_mode          TEXT NOT NULL DEFAULT 'manual',
    scheduled_publish_at  TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_steps (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    step_name             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'running',
    attempt_count         INTEGER NOT NULL DEFAULT 1,
    input_snapshot_json   TEXT,
    output_snapshot_json  TEXT,
    error_snapshot_json   TEXT,
    resume_token          TEXT,
    started_at            TEXT NOT NULL,
    finished_at           TEXT
);

CREATE TABLE IF NOT EXISTS content_versions (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    version_no            INTEGER NOT NULL,
    title                 TEXT,
    subtitle              TEXT,
    summary               TEXT,
    outline_json          TEXT,
    markdown_body         TEXT,
    wechat_html           TEXT,
    cover_plan_json       TEXT,
    evidence_pack_json    TEXT,
    status                TEXT NOT NULL DEFAULT 'draft',
    created_by_agent      TEXT,
    created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_records (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    content_version_id    TEXT REFERENCES content_versions(id),
    review_type           TEXT NOT NULL,
    reviewer_type         TEXT,
    decision              TEXT NOT NULL,
    comments_json         TEXT,
    created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wechat_tokens (
    account_id            TEXT PRIMARY KEY,
    access_token          TEXT NOT NULL,
    expires_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wechat_drafts (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    content_version_id    TEXT REFERENCES content_versions(id),
    wechat_account_id     TEXT NOT NULL,
    media_id              TEXT NOT NULL,
    request_payload_json  TEXT,
    response_payload_json TEXT,
    payload_hash          TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'saved',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wechat_publish_jobs (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    content_version_id    TEXT REFERENCES content_versions(id),
    media_id              TEXT NOT NULL,
    publish_id            TEXT,
    scheduled_at          TEXT,
    submit_payload_json   TEXT,
    submit_response_json  TEXT,
    publish_status        TEXT NOT NULL DEFAULT 'pending',
    published_article_id  TEXT,
    published_link        TEXT,
    idempotency_key       TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_metrics (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT NOT NULL REFERENCES writing_tasks(id),
    content_version_id    TEXT REFERENCES content_versions(id),
    article_id            TEXT,
    view_count            INTEGER DEFAULT 0,
    share_count           INTEGER DEFAULT 0,
    favorite_count        INTEGER DEFAULT 0,
    like_count            INTEGER DEFAULT 0,
    comment_count         INTEGER DEFAULT 0,
    captured_at           TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tasks_status          ON writing_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_account_status  ON writing_tasks(wechat_account_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_external_id     ON writing_tasks(external_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_scheduled_at    ON writing_tasks(scheduled_publish_at);
CREATE INDEX IF NOT EXISTS idx_steps_task_id         ON task_steps(task_id);
CREATE INDEX IF NOT EXISTS idx_steps_task_step       ON task_steps(task_id, step_name);
CREATE INDEX IF NOT EXISTS idx_versions_task_id      ON content_versions(task_id);
CREATE INDEX IF NOT EXISTS idx_reviews_task_id       ON review_records(task_id);
CREATE INDEX IF NOT EXISTS idx_drafts_task_id        ON wechat_drafts(task_id);
CREATE INDEX IF NOT EXISTS idx_drafts_payload_hash   ON wechat_drafts(payload_hash);
CREATE INDEX IF NOT EXISTS idx_publish_task_id       ON wechat_publish_jobs(task_id);
CREATE INDEX IF NOT EXISTS idx_publish_status        ON wechat_publish_jobs(publish_status);
CREATE INDEX IF NOT EXISTS idx_publish_idem_key      ON wechat_publish_jobs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_metrics_task_id       ON content_metrics(task_id);
"""

def main():
    try:
        conn = get_db()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()
        log.info("Database initialized successfully")
        ok({"message": "Database initialized", "tables": [
            "writing_tasks", "task_steps", "content_versions",
            "review_records", "wechat_tokens", "wechat_drafts",
            "wechat_publish_jobs", "content_metrics"
        ]})
    except Exception as e:
        fail("db_init_failed", str(e))

if __name__ == "__main__":
    main()
