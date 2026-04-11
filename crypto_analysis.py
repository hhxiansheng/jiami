#!/usr/bin/env python3
"""
币安永续合约技术分析 - 通用版
支持任意币种，输出完整8段式报告
用法: python3 crypto_analysis.py [SYMBOL]  (默认 BTCUSDT)
"""

import requests
import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor

PROXY = "http://172.28.192.1:7897"
P = {"https": PROXY, "http": PROXY}

def g(url, params=None, timeout=8):
    for i in range(3):
        try:
            r = requests.get(url, params=params, proxies=P, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except:
            time.sleep(0.5)
    return None

def ema(p, n):
    if not p or len(p) < n:
        return None
    m = 2 / (n + 1)
    e = sum(p[:n]) / n
    for v in p[n:]:
        e = v * m + e * (1 - m)
    return e

def rsi(p, n=14):
    if not p or len(p) < n + 1:
        return None
    g2, l2 = [], []
    for i in range(1, len(p)):
        d = p[i] - p[i - 1]
        g2.append(d if d > 0 else 0)
        l2.append(abs(d) if d < 0 else 0)
    ag, al = sum(g2[:n]) / n, sum(l2[:n]) / n
    for i in range(n, len(g2)):
        ag = (ag * (n - 1) + g2[i]) / n
        al = (al * (n - 1) + l2[i]) / n
    return 100 - 100 / (1 + ag / al) if al else 100

def volr(klines):
    if not klines:
        return "平量", 1.0
    v = [float(k[5]) for k in klines]
    r = v[-1] / (sum(v) / len(v)) if v else 1
    return "放量" if r > 1.5 else ("缩量" if r < 0.7 else "平量"), r

def analyze(klines):
    if not klines:
        return None
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    vr, vs_str = volr(klines)
    e7, e25, e99 = ema(closes, 7), ema(closes, 25), ema(closes, 99)
    rs = rsi(closes)
    if e7 and e25 and e99:
        trend = "🟢多头" if e7 > e25 > e99 else ("🔴空头" if e7 < e25 < e99 else "🟡震荡")
    else:
        trend = "🟡震荡"
    if rs and rs > 75:
        rsi_flag = "🔴"
    elif rs and rs > 65:
        rsi_flag = "⚠️"
    elif rs and rs < 35:
        rsi_flag = "✅"
    else:
        rsi_flag = "✅"
    r_highs = sorted(highs[-20:])[-3:]
    r_lows = sorted(lows[-20:])[:3]
    return {
        "price": closes[-1],
        "e7": e7, "e25": e25, "e99": e99,
        "rsi": rs, "rsi_flag": rsi_flag,
        "trend": trend,
        "vol": vs_str, "vr": vr,
        "r": r_highs, "s": r_lows
    }

def fetch_all(symbol):
    start = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_tick = ex.submit(g, f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}")
        f_fund = ex.submit(g, f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}")
        f_btc  = ex.submit(g, "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT")
        f_eth  = ex.submit(g, "https://fapi.binance.com/fapi/v1/ticker/price?symbol=ETHUSDT")
        f_k15  = ex.submit(g, "https://fapi.binance.com/fapi/v1/klines",
                            {"symbol": symbol, "interval": "15m", "limit": 100})
        f_k1h  = ex.submit(g, "https://fapi.binance.com/fapi/v1/klines",
                            {"symbol": symbol, "interval": "1h", "limit": 100})
        f_k4h  = ex.submit(g, "https://fapi.binance.com/fapi/v1/klines",
                            {"symbol": symbol, "interval": "4h", "limit": 100})

        tick = f_tick.result()
        fund = f_fund.result()
        btc  = f_btc.result()
        eth  = f_eth.result()
        k15  = f_k15.result()
        k1h  = f_k1h.result()
        k4h  = f_k4h.result()

    if not tick:
        return None

    a15 = analyze(k15)
    a1h = analyze(k1h)
    a4h = analyze(k4h)

    cur = float(tick["lastPrice"])
    chg = float(tick["priceChangePercent"])
    high = float(tick["highPrice"])
    low = float(tick["lowPrice"])
    vol = float(tick["quoteVolume"])
    fr = float(fund["lastFundingRate"]) * 100 if fund else 0
    btc_p = float(btc["price"]) if btc else 0
    eth_p = float(eth["price"]) if eth else 0

    avg_rsi = (a15["rsi"] + a1h["rsi"] + a4h["rsi"]) / 3
    score = 0
    for a in [a15, a1h, a4h]:
        if "多头" in a["trend"]:
            score += 1
        elif "空头" in a["trend"]:
            score -= 1
    direction = "看多" if score >= 2 else ("看空" if score <= -2 else "震荡")
    winrate = "65%" if direction == "看多" else ("60%" if direction == "看空" else "50%")

    return {
        "symbol": symbol,
        "cur": cur, "chg": chg, "high": high, "low": low, "vol": vol,
        "fr": fr, "btc_p": btc_p, "eth_p": eth_p,
        "a15": a15, "a1h": a1h, "a4h": a4h,
        "avg_rsi": round(avg_rsi, 1),
        "direction": direction, "winrate": winrate,
        "fetch_time": round(time.time() - start, 1)
    }

if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    result = fetch_all(symbol)
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ERROR: 无法获取 {symbol} 数据")
