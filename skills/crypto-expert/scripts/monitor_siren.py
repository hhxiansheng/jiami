#!/usr/bin/env python3
"""
SIRENUSDT 永续合约做空信号监控
信号触发条件（满足任一）：
1. K线形态 = 射击之星/大阴线/三连阴
2. 价格跌破 EMA25
3. EMA7 下穿 EMA25（死叉）
有信号时通过飞书机器人推送通知
"""

import sys
import os
import time
import json
import urllib.request
import ssl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypto_analysis import fetch_binance_klines, calc_ema_latest, detect_kline_pattern

SYMBOL     = "SIRENUSDT"
STATE_FILE = os.path.expanduser("~/.openclaw/workspace/skills/crypto-expert/siren_last_alert.json")
PROXY      = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""

# 飞书 Bot 配置（从 openclaw.json 读取）
FEISHU_APP_ID     = "cli_a937ac761ab8dcd6"
FEISHU_APP_SECRET  = "la834hnAaN9kd6s8RXXG8eAHmvGZReXM"
FEISHU_CHAT_ID    = "ou_2c29a25f768db52fb0f68224ddc3ac63"  # 你的飞书 OpenID

def get_feishu_token():
    """获取飞书 tenant_access_token"""
    ctx = ssl._create_unverified_context()
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                return result.get("tenant_access_token")
    except Exception as e:
        print(f"获取飞书token失败: {e}")
    return None

def send_feishu_alert(message: str):
    """发送飞书机器人消息"""
    token = get_feishu_token()
    if not token:
        print("飞书通知发送失败：无token")
        return False

    ctx = ssl._create_unverified_context()
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    payload = {
        "receive_id": FEISHU_CHAT_ID,
        "msg_type": "text",
        "content": json.dumps({"text": message})
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                print(f"飞书通知发送成功")
                return True
            else:
                print(f"飞书通知发送失败: {result}")
    except Exception as e:
        print(f"飞书通知异常: {e}")
    return False

def load_last_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"last_price": None, "last_ema7": None, "last_ema25": None, "last_alert": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def check():
    from datetime import datetime
    state = load_last_state()
    klines = None
    for _ in range(3):
        klines = fetch_binance_klines(SYMBOL, interval="1h", limit=100, futures=True)
        if klines:
            break
        time.sleep(3)

    if not klines:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 无法获取数据")
        return False

    closes = [float(k[4]) for k in klines]
    price  = closes[-1]
    ema7   = calc_ema_latest(closes, 7)
    ema25  = calc_ema_latest(closes, 25)
    ema99  = calc_ema_latest(closes, 99)

    pattern_info = detect_kline_pattern(klines)
    alerts = []

    # 条件1：K线形态做空
    if pattern_info["signal"] == "bearish":
        alerts.append(f"【K线形态】{pattern_info['pattern']} — 看空信号")

    # 条件2：价格跌破 EMA25
    if state["last_price"] and price < state["last_price"] and price < ema25:
        alerts.append(f"【价格跌破EMA25】现价 {price:.6f} < EMA25 {ema25:.6f}")

    # 条件3：EMA7 下穿 EMA25（死叉）
    if state["last_ema7"] and state["last_ema25"]:
        if state["last_ema7"] > state["last_ema25"] and ema7 < ema25:
            alerts.append(f"【死叉】EMA7({ema7:.6f}) 下穿 EMA25({ema25:.6f})")

    new_state = {
        "last_price": price,
        "last_ema7": ema7,
        "last_ema25": ema25,
        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_alert": alerts[0] if alerts else state.get("last_alert")
    }
    save_state(new_state)

    if alerts:
        msg = f"🚨 SIRENUSDT 做空信号！\n\n" + "\n\n".join(alerts)
        msg += f"\n\n当前：价格={price:.6f} | EMA7={ema7:.6f} | EMA25={ema25:.6f} | EMA99={ema99:.6f}"
        print(msg)
        send_feishu_alert(msg)
        return True
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 无做空信号 | 价格={price:.6f} | EMA7={ema7:.6f} | EMA25={ema25:.6f}")
        return False

if __name__ == "__main__":
    check()
