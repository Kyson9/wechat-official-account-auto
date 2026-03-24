"""
共享基础库：配置读取、数据库连接、日志、JSON I/O
所有脚本通过 from lib.common import * 引入
"""
import json
import sys
import os
import sqlite3
import hashlib
import logging
import yaml
from datetime import datetime, timezone
from pathlib import Path

# ── 路径解析 ────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).parent.parent
PROJECT_ROOT = SCRIPTS_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config.yml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CFG = load_config()


# ── 日志 ─────────────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    level = getattr(logging, CFG.get("logging", {}).get("level", "INFO"))
    log_file = CFG.get("logging", {}).get("log_file", "")
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    return logging.getLogger(name)


# ── JSON I/O ─────────────────────────────────────────────────────────────────
def read_stdin() -> dict:
    """从 stdin 读取 JSON 输入"""
    return json.loads(sys.stdin.read())


def ok(data: dict = None):
    """输出成功响应并退出"""
    print(json.dumps({"success": True, "data": data or {}}, ensure_ascii=False))
    sys.exit(0)


def fail(code: str, message: str, details: dict = None):
    """输出失败响应并退出"""
    print(json.dumps({
        "success": False,
        "error": {"code": code, "message": message, "details": details or {}}
    }, ensure_ascii=False))
    sys.exit(1)


# ── 数据库 ────────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    db_path = PROJECT_ROOT / CFG["database"]["path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_account_cfg(account_id: str) -> dict:
    accounts = CFG.get("wechat_accounts", {})
    if account_id not in accounts:
        fail("account_not_found", f"wechat_account_id '{account_id}' not in config.yml")
    return accounts[account_id]
