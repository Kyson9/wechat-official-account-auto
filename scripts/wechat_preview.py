#!/usr/bin/env python3
"""
发送微信公众号文章预览到指定微信号
使用 message/mass/preview 接口，将草稿 media_id 的图文消息预览发送到指定微信号。

前提限制：
  1. 接收者微信号必须已关注该公众号
  2. 每日预览次数有限（约 100 次/天，与群发预览共享配额）
  3. towxname 是微信号（非昵称、非 openid）

stdin JSON:
  {
    "wechat_account_id": "wxoa_main",
    "media_id": "DRAFT_MEDIA_ID",
    "towxname": "YOUR_PREVIEW_WXNAME"           # 可选，省略则用 config.yml 中 preview.default_wxname
  }
stdout JSON:
  {"success": true, "data": {"msg_id": 123456, "towxname": "YOUR_PREVIEW_WXNAME"}}
"""
import sys, json, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, get_account_cfg


def get_token(account_id: str) -> str:
    import subprocess
    inp = json.dumps({"wechat_account_id": account_id})
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "wechat_token.py")],
        input=inp, capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    if not data.get("success"):
        raise RuntimeError(f"Token error: {data}")
    return data["data"]["access_token"]


def get_default_wxname(account_id: str) -> str:
    """从 config.yml 获取该账号的默认预览接收微信号"""
    acct = get_account_cfg(account_id)
    preview_cfg = acct.get("preview", {})
    wxname = preview_cfg.get("default_wxname", "")
    if not wxname:
        fail("no_default_wxname",
             f"No towxname provided and no preview.default_wxname configured for '{account_id}'")
    return wxname


def main():
    inp = read_stdin()

    account_id = inp.get("wechat_account_id", "").strip()
    if not account_id:
        fail("invalid_param", "'wechat_account_id' is required")

    media_id = inp.get("media_id", "").strip()
    if not media_id:
        fail("invalid_param", "'media_id' is required")

    towxname = inp.get("towxname", "").strip()
    if not towxname:
        towxname = get_default_wxname(account_id)

    try:
        token = get_token(account_id)
    except Exception as e:
        fail("wechat_auth_failed", str(e))

    # 构造 message/mass/preview 请求
    preview_payload = {
        "towxname": towxname,
        "mpnews": {"media_id": media_id},
        "msgtype": "mpnews"
    }
    payload_bytes = json.dumps(preview_payload, ensure_ascii=False).encode("utf-8")

    url = f"https://api.weixin.qq.com/cgi-bin/message/mass/preview?access_token={token}"
    req = urllib.request.Request(url, data=payload_bytes,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        fail("wechat_preview_failed", str(e))

    if result.get("errcode", 0) != 0:
        fail("wechat_preview_failed",
             f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}",
             result)

    msg_id = result.get("msg_id", 0)
    ok({"msg_id": msg_id, "towxname": towxname})


if __name__ == "__main__":
    main()
