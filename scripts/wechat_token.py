#!/usr/bin/env python3
"""
获取微信 access_token（含缓存，提前 5 分钟刷新）
stdin JSON:
  {"wechat_account_id": "wxoa_main"}
stdout JSON:
  {"success": true, "data": {"access_token": "TOKEN", "expires_at": "ISO8601"}}
"""
import sys, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, get_account_cfg, now_utc

REFRESH_BUFFER_SECONDS = 300  # 提前 5 分钟刷新

def fetch_new_token(app_id: str, app_secret: str) -> tuple[str, str]:
    url = (
        f"https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    if "errcode" in data and data["errcode"] != 0:
        raise RuntimeError(f"WeChat error {data['errcode']}: {data.get('errmsg')}")
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 7200))
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    return token, expires_at

def main():
    inp = read_stdin()
    account_id = inp.get("wechat_account_id", "").strip()
    if not account_id:
        fail("invalid_param", "wechat_account_id is required")

    acct = get_account_cfg(account_id)
    app_id     = acct["app_id"]
    app_secret = acct["app_secret"]

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT access_token, expires_at FROM wechat_tokens WHERE account_id=?",
            (account_id,)
        ).fetchone()

        if row:
            expires_at = datetime.fromisoformat(row["expires_at"])
            now = datetime.now(timezone.utc)
            if (expires_at - now).total_seconds() > REFRESH_BUFFER_SECONDS:
                ok({"access_token": row["access_token"], "expires_at": row["expires_at"]})

        # 需要刷新
        token, expires_at = fetch_new_token(app_id, app_secret)
        now = now_utc()
        conn.execute("""
            INSERT INTO wechat_tokens (account_id, access_token, expires_at, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(account_id) DO UPDATE SET
                access_token=excluded.access_token,
                expires_at=excluded.expires_at,
                updated_at=excluded.updated_at
        """, (account_id, token, expires_at, now))
        conn.commit()
        ok({"access_token": token, "expires_at": expires_at})
    except SystemExit:
        raise
    except Exception as e:
        fail("wechat_auth_failed", str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
