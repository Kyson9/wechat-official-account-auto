#!/usr/bin/env python3
"""
轮询微信发布状态（freepublish/get），更新 wechat_publish_jobs 表
stdin JSON:
  {
    "wechat_account_id": "wxoa_main",
    "publish_id": "PUBLISH_JOB_ID",
    "task_id": "wt_..."
  }
stdout JSON:
  {
    "success": true,
    "data": {
      "publish_status": "polling|published|failed",
      "article_id": "ART_001|null",
      "article_link": "https://...|null",
      "wechat_errcode": 0
    }
  }
"""
import sys, json, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_db, now_utc
import subprocess

# 微信发布状态码映射
# publish_status: 0=成功, 1=发布中, 2=原创失败, 3=常规失败, 4=平台审核不通过, 5=成功(灰度)
WECHAT_STATUS_MAP = {
    0: "published",
    1: "polling",
    2: "failed",
    3: "failed",
    4: "failed",
    5: "published",
}

def get_token(account_id: str) -> str:
    inp = json.dumps({"wechat_account_id": account_id})
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "wechat_token.py")],
        input=inp, capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    if not data.get("success"):
        raise RuntimeError(f"Token error: {data}")
    return data["data"]["access_token"]

def main():
    inp = read_stdin()
    for f in ["wechat_account_id", "publish_id", "task_id"]:
        if not inp.get(f):
            fail("invalid_param", f"'{f}' is required")

    account_id = inp["wechat_account_id"]
    publish_id  = inp["publish_id"]
    task_id     = inp["task_id"]

    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    payload = json.dumps({"publish_id": publish_id}, ensure_ascii=False).encode("utf-8")
    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/get?access_token={token}"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        fail("wechat_publish_poll_timeout", str(e))

    if result.get("errcode", 0) != 0:
        fail("wechat_publish_poll_timeout",
             f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}",
             result)

    publish_info = result.get("publish_info", {})
    wx_status_code = publish_info.get("publish_status", 1)
    our_status = WECHAT_STATUS_MAP.get(wx_status_code, "polling")

    article_id   = None
    article_link = None

    if our_status == "published":
        articles = publish_info.get("article_detail", {}).get("item", [])
        if articles:
            article_id   = str(articles[0].get("article_id", ""))
            article_link = articles[0].get("article_url", "")

    # 更新数据库
    now = now_utc()
    conn = get_db()
    try:
        conn.execute("""
            UPDATE wechat_publish_jobs
            SET publish_status=?, published_article_id=?, published_link=?, updated_at=?
            WHERE task_id=? AND publish_id=?
        """, (our_status, article_id, article_link, now, task_id, publish_id))
        conn.commit()
    except Exception as e:
        fail("db_error", str(e))
    finally:
        conn.close()

    ok({
        "publish_status": our_status,
        "article_id": article_id,
        "article_link": article_link,
        "wechat_status_code": wx_status_code,
    })

if __name__ == "__main__":
    main()
