#!/usr/bin/env python3
"""
Binance 永续合约深度技术分析 v3
- 多周期: 15分钟 / 1小时 / 4小时 / 日线
- 指标: EMA(7/25/99) + RSI(14) + 成交量 + 持仓量(OI)
- 新增: BTC联动分析 / 成交量结构深度 / OI六情况判定 / 仓位杠杆建议 / 最终结论
- 报告8段结构: 大级别趋势 / 多周期评估 / 成交量结构 / OI分析 / 资金费率 / 技术评级+止损止盈 / 狙击位+仓位建议 / 最终结论
"""

import sys
import os
import json
import argparse
import ssl
import time as _time
import urllib.request
from datetime import datetime

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""

def get_opener():
    if PROXY:
        ctx = ssl._create_unverified_context()
        handler = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
        return urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener()

def fetch_klines(symbol: str, interval: str, limit: int = 200):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    for attempt in range(4):
        try:
            with get_opener().open(url, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            _time.sleep(2)
    print(f"API请求失败 [{interval}]: 最终失败", file=sys.stderr)
    return []

def try_requests(url, params=None):
    """Fallback requests method for endpoints that urllib can't reach"""
    try:
        import warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        import requests
        proxies = {'https': PROXY, 'http': PROXY} if PROXY else None
        r = requests.get(url, params=params, proxies=proxies, timeout=15, verify=False)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def fetch_oi(symbol: str):
    """获取当前持仓量(Open Interest)"""
    url = f"https://fapi.binance.com/fapi/v1/openInterest"
    for attempt in range(3):
        try:
            with get_opener().open(f"{url}?symbol={symbol.upper()}", timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return int(data.get("openInterest", 0))
        except Exception:
            _time.sleep(2)
    # fallback via requests
    data = try_requests(url, {"symbol": symbol.upper()})
    if isinstance(data, dict) and "openInterest" in data:
        return int(float(data["openInterest"]))
    return None

def fetch_funding_rate(symbol: str) -> dict:
    """
    获取资金费率数据
    优先从 premiumIndex 取实时 lastFundingRate（最新预估费率）
    回退到 fundingRate 接口的历史结算费率
    返回: {"rate": float (如 -0.0193), "next_funding_ts": int, "mark_price": float, "countdown_minutes": float}
    """
    # 优先：从 premiumIndex 取最新预估费率
    url_pi = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol.upper()}"
    rate = None
    mark_price = None
    for attempt in range(3):
        try:
            with get_opener().open(url_pi, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                lfr = data.get("lastFundingRate", None)
                if lfr is not None:
                    rate = float(lfr)
                mark_price = float(data.get("markPrice", 0))
                break
        except Exception:
            _time.sleep(2)

    # 回退：从 fundingRate 取下次结算时间
    url_fr = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol.upper()}&limit=1"
    next_funding_ts = None
    for attempt in range(3):
        try:
            with get_opener().open(url_fr, timeout=15) as resp:
                fr_data = json.loads(resp.read().decode())
                if fr_data:
                    next_funding_ts = int(fr_data[0]["fundingTime"])
                break
        except Exception:
            _time.sleep(2)

    # 计算距下次结算时间
    now_url = "https://fapi.binance.com/fapi/v1/time"
    with get_opener().open(now_url, timeout=10) as nr:
        now_ts = json.loads(nr.read().decode())["serverTime"]

    countdown_min = None
    if next_funding_ts:
        if next_funding_ts < now_ts:
            next_funding_ts += 8 * 3600 * 1000
        countdown_ms = next_funding_ts - now_ts
        countdown_min = round(countdown_ms / 60000, 1)

    if rate is None:
        return None

    return {
        "rate": rate,
        "next_funding_ts": next_funding_ts,
        "mark_price": mark_price,
        "countdown_minutes": countdown_min,
        "funding_rate_pct": round(rate * 100, 4),  # 如 -2.00
    }

def analyze_funding_rate(symbol: str, price: float, price_change_pct: float) -> dict:
    """
    分析资金费率，给出大白话判定
    """
    fr = fetch_funding_rate(symbol)
    if not fr:
        return {
            "note": "**资金费率分析**\n费率数据暂不可用",
            "signal": "unknown",
            "label": "",
        }

    rate_pct = fr["funding_rate_pct"]
    countdown = fr["countdown_minutes"]
    mark_price = fr["mark_price"]
    rate = fr["rate"]

    # 判定逻辑
    signal = "neutral"
    label = ""
    alert = ""

    # 负费率 → 空头付钱给多头（持空仓的人每8小时倒贴）
    # rate 是小数，如 -0.0193 表示 -1.93%
    if rate < -0.001:   # < -0.1%
        signal = "short_squeeze"
        label = "🔴 空头挤压（Short Squeeze）预警！"
        alert = (
            f"资金费率 **{rate_pct:.2f}%**（每8小时空头倒贴多头）\n"
            f"当前距下次结算：约 {countdown:.0f} 分钟\n"
            f"  -> 空头正在付巨额利息！\n"
            f"  -> 费率如此极端，说明空头仓位极重。\n"
            f"  -> 每8小时，空头就要平白损失 **{abs(rate_pct):.2f}%** 的仓位价值。\n"
            f"  -> 这些空头随时可能被迫平仓（止损或主动砍），\n"
            f"     一旦集中平仓就会引发**暴力拉升逼空**！\n"
        )
        if rate < -0.005:   # < -0.5%
            alert += f"\n⚠️ **【极度极端】费率 {rate_pct:.2f}% 是我见过的最高级别空头挤压信号！**\n"
            alert += "这种费率意味着：空头要么被套得很深，要么在故意压价吸筹。无论哪种，向上爆发只是时间问题。\n"

    elif rate > 0.001:   # > 0.1%
        signal = "bull_trap"
        label = "⚠️ 多头头铁成本极高预警"
        alert = (
            f"资金费率 **{rate_pct:.2f}%**（每8小时多头倒贴空头）\n"
            f"当前距下次结算：约 {countdown:.0f} 分钟\n"
            f"  -> 多头仓位极重，每8小时多头就要付钱给空头。\n"
            f"  -> 这种情况下，多头一旦撑不住就会踩踏式平多，\n"
            f"     导致**快速闪崩**！\n"
        )

    else:
        signal = "neutral"
        label = "✅ 资金费率正常"
        alert = (
            f"资金费率 {rate_pct:.4f}%，正常区间。\n"
            f"多空双方成本均衡，无极端挤压风险。\n"
        )

    # 背离检测
    divergence_note = ""
    if signal == "short_squeeze" and price_change_pct > 5:
        divergence_note = (
            "\n⚠️ **【背离预警】**：价格已经涨了很多 + 负费率极高，"
            "这意味着空头在price大涨的情况下依然在死扛做空（或者被套牢）。"
            "一旦他们认输平仓，涨幅会非常凶猛。"
        )
    elif signal == "short_squeeze" and price_change_pct < -3:
        divergence_note = (
            "\n⚠️ **【背离预警】**：价格还在跌，但负费率极高——"
            "说明有人在逆势加空仓。这是庄家诱空或者在收集筹码。"
            "这种走势一旦反转，空头踩踏会非常惨烈。"
        )
    elif signal == "bull_trap" and price_change_pct > 5:
        divergence_note = (
            "\n⚠️ **【背离预警】**：价格涨 + 正费率极高 = 多头在强撑。 "
            "高费率让多头持仓成本越来越高，一旦撑不住就是踩踏式崩塌。"
        )

    return {
        "note": f"**资金费率分析**\n{alert}{divergence_note}",
        "signal": signal,
        "label": label,
        "rate_pct": rate_pct,
        "countdown_minutes": countdown,
        "mark_price": mark_price,
        "fr": fr,
    }

def calc_ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return [None] * len(prices)
    k = 2 / (period + 1)
    ema = [None] * (period - 1)
    ema.append(prices[period - 1])
    for i in range(period, len(prices)):
        ema.append(prices[i] * k + ema[-1] * (1 - k))
    return ema

def calc_ema_latest(prices: list, period: int) -> float:
    ema = calc_ema(prices, period)
    for v in reversed(ema):
        if v is not None:
            return round(v, 6)
    return 0.0

def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        gains.append(delta if delta > 0 else 0)
        losses.append(abs(delta) if delta < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calc_volume_profile(klines: list) -> str:
    if len(klines) < 6:
        return "数据不足"
    volumes = [float(k[5]) for k in klines[-6:]]
    recent_vol = sum(volumes[-3:])
    early_vol  = sum(volumes[:3])
    ratio = recent_vol / (early_vol + 1e-9)
    if ratio > 1.3:
        trend = "UP 放量"
    elif ratio < 0.7:
        trend = "DOWN 缩量"
    else:
        trend = "SIDE 量能平稳"
    return f"{trend} (ratio={ratio:.2f}x)"

def detect_volume_pattern(klines: list) -> dict:
    """
    成交量结构深度分析：分析最近5根K线逐根量能变化
    返回: {
        "逐根量能": [...],
        "总体判断": str,
        "滞涨/吸筹": str,
        "量价配合": str,
    }
    """
    if len(klines) < 5:
        return {"逐根量能": [], "总体判断": "数据不足", "滞涨/吸筹": "", "量价配合": ""}
    recent = klines[-5:]
    vol_list = [float(k[5]) for k in recent]
    close_list = [float(k[4]) for k in recent]
    open_list = [float(k[1]) for k in recent]
    high_list = [float(k[2]) for k in recent]
    low_list = [float(k[3]) for k in recent]

    # 计算逐根变化（对比20周期均量，禁止用"同比上一根增长XX%"）
    avg_vol = sum(vol_list) / len(vol_list)
    vol_changes = []
    for i in range(len(vol_list)):
        direction = "↑" if close_list[i] > open_list[i] else "↓"
        ratio_vs_avg = vol_list[i] / avg_vol
        vol_changes.append(f"第{i+1}根: {direction}量{vol_list[i]:.0f}(均量的{ratio_vs_avg:.2f}倍)")

    # 总体判断：放量推进 vs 缩量回调
    last_two_avg = sum(vol_list[-2:]) / 2
    vol_trending_up = last_two_avg > avg_vol * 1.15
    vol_trending_down = last_two_avg < avg_vol * 0.85

    price_trend = "涨" if close_list[-1] > close_list[0] else "跌"
    if vol_trending_up and price_trend == "涨":
        overall = "放量推进（资金推动上涨，健康）"
        vol_price = "量价配合良好，上涨有资金支撑"
    elif vol_trending_up and price_trend == "跌":
        overall = "放量砸盘（资金出逃，主动性抛售）"
        vol_price = "量价同跌，资金主动做空"
    elif vol_trending_down and price_trend == "涨":
        overall = "缩量上涨（虚涨，无量反弹不牢）"
        vol_price = "量价背离：涨了但没资金，不可靠"
    elif vol_trending_down and price_trend == "跌":
        overall = "缩量回调（健康回调，抛压不重）"
        vol_price = "缩量跌：主力未出货，回调后易反弹"
    else:
        overall = "量能平稳（震荡结构）"
        vol_price = "多空均衡，等待方向突破"

    # 滞涨/吸筹识别（看最后1-2根）
    last_vol = vol_list[-1]
    prev_vol = vol_list[-2]
    last_price_chg = (close_list[-1] - close_list[-2]) / close_list[-2] * 100
    prev_price_chg = (close_list[-2] - close_list[-3]) / close_list[-3] * 100 if len(close_list) >= 3 else 0

    if last_vol > avg_vol * 1.3 and last_price_chg < 0.3 and close_list[-1] < high_list[-1] * 0.99:
        stagnation = "⚠️ 高位滞涨：价格涨不动但量还很大，可能是主力在出货"
    elif last_vol > avg_vol * 1.3 and last_price_chg > 1 and close_list[-1] > low_list[-1] * 1.01:
        stagnation = "✅ 放量拉升：价格涨伴随大量，上涨动力充足"
    elif last_vol < avg_vol * 0.6 and abs(last_price_chg) < 0.5:
        stagnation = "⚠️ 低位吸筹嫌疑：价格横盘+量能极低，可能是主力压价吸筹"
    elif prev_vol > avg_vol * 1.2 and last_vol < avg_vol * 0.7 and last_price_chg < 0:
        stagnation = "🔴 拉高出货后缩量：前一根放量阳线后缩量下跌，需警惕"
    else:
        stagnation = "未发现明显高位滞涨/低位吸筹信号"

    return {
        "逐根量能": vol_changes,
        "总体判断": overall,
        "滞涨/吸筹": stagnation,
        "量价配合": vol_price,
    }

def detect_kline_pattern(klines: list) -> dict:
    if len(klines) < 5:
        return {"pattern": "neutral", "signal": "neutral"}
    closes = [float(k[4]) for k in klines[-5:]]
    opens  = [float(k[1]) for k in klines[-5:]]
    highs  = [float(k[2]) for k in klines[-5:]]
    lows   = [float(k[3]) for k in klines[-5:]]
    body_ratio   = (max(opens[-1], closes[-1]) - min(opens[-1], closes[-1])) / (highs[-1] - lows[-1] + 1e-9)
    lower_shadow = min(opens[-1], closes[-1]) - lows[-1]
    upper_shadow = highs[-1] - max(opens[-1], closes[-1])
    body         = abs(opens[-1] - closes[-1])
    up_count     = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
    pattern, signal = "neutral", "neutral"
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        pattern, signal = "hammer", "bullish"
    elif upper_shadow > body * 2 and lower_shadow < body * 0.5:
        pattern, signal = "shooting_star", "bearish"
    elif closes[-1] > closes[-2] > closes[-3] and up_count >= 3:
        pattern, signal = "three_up", "bullish"
    elif closes[-1] < closes[-2] < closes[-3] and up_count <= 2:
        pattern, signal = "three_down", "bearish"
    elif body_ratio < 0.1:
        pattern, signal = "doji", "neutral"
    elif closes[-1] > opens[-1] and body_ratio > 0.7:
        pattern, signal = "big_up", "bullish"
    elif closes[-1] < opens[-1] and body_ratio > 0.7:
        pattern, signal = "big_down", "bearish"
    return {"pattern": pattern, "signal": signal}

PATTERN_NAMES = {
    "hammer": "锤子线", "shooting_star": "射击之星",
    "three_up": "三连阳", "three_down": "三连阴",
    "doji": "十字星", "big_up": "大阳线",
    "big_down": "大阴线", "neutral": "中性",
}

def detect_sr_levels(klines: list, lookback: int = 50) -> dict:
    if len(klines) < lookback:
        lookback = len(klines)
    highs  = [float(k[2]) for k in klines[-lookback:]]
    lows   = [float(k[3]) for k in klines[-lookback:]]
    current = float(klines[-1][4])
    recent_high = max(highs[-20:])
    recent_low  = min(lows[-20:])
    return {
        "recent_high": round(recent_high, 6),
        "recent_low":  round(recent_low, 6),
        "breakout_up":   current > recent_high,
        "breakout_down": current < recent_low,
    }

def calc_stop_loss_take_profit(sr_main: dict, price: float, bull_pct: float) -> dict:
    """
    计算止损和止盈位（实用比例版）
    - 止损：从入场价回撤 2%（做多）或上涨 2%（做空）
    - 止盈：向阻力方向 3%（做多）或向支撑方向 3%（做空）
    """
    resistance = sr_main.get("recent_high", price * 1.03)
    support    = sr_main.get("recent_low",  price * 0.97)

    if bull_pct >= 50:
        direction   = "LONG"
        stop_loss   = round(price * 0.98, 6)
        take_profit = round(min(resistance, price * 1.05), 6)
    else:
        direction   = "SHORT"
        stop_loss   = round(price * 1.02, 6)
        take_profit = round(max(support, price * 0.95), 6)

    return {
        "direction": direction,
        "entry":     round(price, 6),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "sl_pct":    round(abs(stop_loss - price) / price * 100, 2),
        "tp_pct":    round(abs(take_profit - price) / price * 100, 2),
    }

def fetch_24h_ticker(symbol: str) -> dict:
    """获取24h行情（含成交量）"""
    url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
    for attempt in range(3):
        try:
            with get_opener().open(url, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            import time as _time
            _time.sleep(2)
    return {}

def fetch_btc_comparison(symbol: str) -> dict:
    """
    获取BTC联动分析：
    - 获取BTCUSDT 4H+1H K线，计算EMA7/EMA25趋势
    - 判断该币与BTC是否同向/独立/反向
    返回 dict
    """
    result = {
        "btc_trend_4h": "unknown",
        "btc_trend_1h": "unknown",
        "correlation": "独立行情",
        "note": "",
        "signal": "neutral",
    }
    try:
        # BTC 4H
        btc_klines_4h = fetch_klines("BTCUSDT", "4h", limit=50)
        if btc_klines_4h:
            btc_closes_4h = [float(k[4]) for k in btc_klines_4h]
            btc_ema7_4h = calc_ema_latest(btc_closes_4h, 7)
            btc_ema25_4h = calc_ema_latest(btc_closes_4h, 25)
            btc_price_4h = btc_closes_4h[-1]
            if btc_price_4h > btc_ema7_4h > btc_ema25_4h:
                result["btc_trend_4h"] = "BULL 多头"
            elif btc_price_4h < btc_ema7_4h < btc_ema25_4h:
                result["btc_trend_4h"] = "BEAR 空头"
            else:
                result["btc_trend_4h"] = "SIDE 震荡"
        # BTC 1H
        btc_klines_1h = fetch_klines("BTCUSDT", "1h", limit=50)
        if btc_klines_1h:
            btc_closes_1h = [float(k[4]) for k in btc_klines_1h]
            btc_ema7_1h = calc_ema_latest(btc_closes_1h, 7)
            btc_ema25_1h = calc_ema_latest(btc_closes_1h, 25)
            btc_price_1h = btc_closes_1h[-1]
            if btc_price_1h > btc_ema7_1h > btc_ema25_1h:
                result["btc_trend_1h"] = "BULL 多头"
            elif btc_price_1h < btc_ema7_1h < btc_ema25_1h:
                result["btc_trend_1h"] = "BEAR 空头"
            else:
                result["btc_trend_1h"] = "SIDE 震荡"
        result["note"] = (
            f"BTC 4H趋势: {result['btc_trend_4h']} | "
            f"BTC 1H趋势: {result['btc_trend_1h']}"
        )
    except Exception as e:
        result["note"] = f"BTC联动数据获取失败: {e}"
    return result

def analyze_oi(symbol: str, price: float) -> dict:
    """
    分析持仓量(Open Interest) + 成交量辅助验证
    改进：
    1. 优先对比1小时前的OI数据（时间加权）
    2. 无OI历史时，用成交量辅助判断
    3. 同时获取BTC大盘OI作为背景参考
    """
    state_file = os.path.expanduser(f"~/.openclaw/workspace/skills/crypto-expert/oi_state_{symbol.upper()}.json")

    # 获取当前OI和成交量
    current_oi = fetch_oi(symbol)
    ticker = fetch_24h_ticker(symbol)
    current_vol = float(ticker.get("volume", 0))  # 基础资产成交量（如BULLA数量）
    current_quote_vol = float(ticker.get("quoteVolume", 0))  # USDT成交量

    prev_state = {}
    try:
        with open(state_file) as f:
            prev_state = json.load(f)
    except:
        pass

    prev_oi    = prev_state.get("oi")
    prev_price = prev_state.get("price")
    prev_vol   = prev_state.get("volume")
    prev_time_str = prev_state.get("time")
    prev_time = None
    if prev_time_str:
        from datetime import datetime as dt
        try:
            prev_time = dt.fromisoformat(prev_time_str)
        except:
            pass

    now = datetime.now()
    # 保存当前状态
    try:
        with open(state_file, "w") as f:
            json.dump({
                "oi": current_oi,
                "price": price,
                "volume": current_vol,
                "time": now.isoformat()
            }, f)
    except:
        pass

    if not current_oi:
        # OI完全不可用，改用成交量分析
        vol_change_pct = None
        if prev_vol and prev_vol > 0:
            vol_change_pct = round((current_vol - prev_vol) / prev_vol * 100, 2)
        vol_signal = None
        if vol_change_pct is not None:
            if price < (prev_state.get("price") or price) and vol_change_pct > 5:
                vol_signal = "bearish"   # 价格跌 + 成交量放大 = 资金离场
                vol_note = (f"成交量变化 +{vol_change_pct}% | 价格 {'跌' if price < (prev_state.get('price') or price) else '涨'}\n"
                            f"  -> 量价背离：下跌中成交量放大，资金立场迹象")
            elif price < (prev_state.get("price") or price) and vol_change_pct < -5:
                vol_signal = "bullish"   # 价格跌 + 成交量萎缩 = 抛压不重
                vol_note = (f"成交量变化 {vol_change_pct}% | 价格跌\n"
                            f"  -> 缩量下跌：抛压不重，可能是盘整而非真跌")
            elif price > (prev_state.get("price") or price) and vol_change_pct > 5:
                vol_signal = "bullish"
                vol_note = (f"成交量变化 +{vol_change_pct}% | 价格涨\n"
                            f"  -> 放量上涨：资金配合，上涨健康")
            else:
                vol_signal = "neutral"
                vol_note = f"成交量变化 {vol_change_pct}% | 信号不明确"
        else:
            vol_note = f"成交量(24h): {current_vol:,.0f} {symbol.upper().replace('USDT','')} | {current_quote_vol:,.0f} USDT\n(暂无历史对比，成交量数据仅供参考)"

        # 尝试获取BTC大盘OI作为背景参考
        btc_note = ""
        btc_signal = None
        try:
            btc_ticker = fetch_24h_ticker("BTCUSDT")
            btc_prev_vol = prev_state.get("btc_volume")
            btc_prev_price = prev_state.get("btc_price")
            if btc_prev_vol and btc_prev_price:
                btc_vol_chg = (float(btc_ticker.get("volume",0)) - btc_prev_vol) / btc_prev_vol * 100
                if btc_vol_chg < -5:
                    btc_signal = "bearish"
                    btc_note = f"\n大盘(BTC)缩量{btc_vol_chg:.1f}%：整体市场资金萎缩，该币缩量属于正常现象"
                elif btc_vol_chg > 5:
                    btc_signal = "bullish"
                    btc_note = f"\n大盘(BTC)放量{btc_vol_chg:.1f}%：市场整体活跃，可参考性增强"
        except:
            pass

        return {
            "note": f"**持仓量(OI)分析**\nOI数据暂不可用\n{vol_note}{btc_note}",
            "direction": vol_signal or "unknown",
            "signal": vol_signal or "unknown",
            "current_oi": None,
            "oi_change_pct": 0,
            "price_change_pct": round((price - prev_price) / prev_price * 100, 2) if prev_price else 0,
            "volume_change_pct": vol_change_pct,
            "volume_signal": vol_signal,
            "btc_note": btc_note,
        }

    # ========== 有OI数据时的完整分析 ==========
    # 计算时间加权变化率（1小时基准）
    time_diff_hours = 1.0
    if prev_time:
        time_diff_hours = max(0.25, (now - prev_time).total_seconds() / 3600)

    oi_change_pct = round((current_oi - prev_oi) / prev_oi * 100, 2) if prev_oi else 0
    price_change_pct = round((price - prev_price) / prev_price * 100, 2) if prev_price else 0
    vol_change_pct = round((current_vol - prev_vol) / prev_vol * 100, 2) if prev_vol else None

    oi_up    = oi_change_pct > 5 / time_diff_hours   # 1小时基准5%
    oi_down  = oi_change_pct < -5 / time_diff_hours
    price_up  = price_change_pct > 0

    # 大盘OI背景
    btc_note = ""
    btc_signal = None
    try:
        btc_ticker = fetch_24h_ticker("BTCUSDT")
        btc_prev = prev_state.get("btc_price")
        if btc_prev:
            btc_chg = (float(btc_ticker.get("volume",0)) - prev_state.get("btc_volume",0)) / max(1, prev_state.get("btc_volume",1)) * 100
            if btc_chg < -5:
                btc_signal = "bearish"
                btc_note = f"\n大盘(BTC)缩量{btc_chg:.1f}%：整体市场资金萎缩，该币缩量属于正常现象"
            elif btc_chg > 5:
                btc_note = f"\n大盘(BTC)放量{btc_chg:.1f}%：市场整体活跃"
    except:
        pass

    # 核心判断（6种情况）
    if oi_up and price_up:
        oi_direction = "BULL 多头加仓"
        oi_signal = "bullish"
        situation = "情况①：价格上涨 + OI增加 → 资金真实入场"
        oi_note = (f"持仓量(OI) +{oi_change_pct}%({time_diff_hours:.1f}h) | 价格 +{price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> 多头在发力：价格与持仓同涨，资金持续入场看多，这是最健康的上涨结构。\n"
                    f"  -> 后市延续上涨概率高，回调就是加仓机会。")
    elif oi_up and not price_up:
        oi_direction = "BEAR 空头增仓"
        oi_signal = "bearish"
        situation = "情况④：价格下跌 + OI增加 → 空头主动加仓"
        oi_note = (f"持仓量(OI) +{oi_change_pct}%({time_diff_hours:.1f}h) | 价格 {price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> 空头猛力增仓：价格跌但空头仓位大幅增加，这是空头主动进攻。\n"
                    f"  -> 下跌动力强，严禁逆势抄底，等空头获利平仓再说。")
    elif not oi_up and price_up:
        oi_direction = "BULL 多头减空（Short Squeeze）"
        oi_signal = "bullish"
        situation = "情况②：价格上涨 + OI减少 → 空头回补（Short Squeeze）"
        oi_note = (f"持仓量(OI) {oi_change_pct}%({time_diff_hours:.1f}h) | 价格 +{price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> 价格涨但持仓减少 = 空头被迫平仓！这叫Short Squeeze（空头踩踏）。\n"
                    f"  -> 涨得很凶但没新资金进来，属于「虚涨」。随时可能反转！")
    elif oi_down and not price_up:
        oi_direction = "BEAR 多头踩踏离场"
        oi_signal = "bearish"
        situation = "情况③：价格下跌 + OI减少 → 多头踩踏离场"
        oi_note = (f"持仓量(OI) {oi_change_pct}%({time_diff_hours:.1f}h) | 价格 {price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> 多头在割肉！价格跌+持仓萎缩=多头踩踏离场。\n"
                    f"  -> 跌势未止，禁止逆势抄底。等待缩量止跌再考虑入场。")
    elif abs(oi_change_pct) > 15 / time_diff_hours and abs(price_change_pct) < 1:
        oi_direction = "NEUTRAL 横盘蓄势"
        oi_signal = "neutral"
        situation = "情况⑤：价格横盘 + OI暴涨 → 横盘蓄势即将爆发"
        oi_note = (f"持仓量(OI) {oi_change_pct}%({time_diff_hours:.1f}h) | 价格 {price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> 横盘震荡但OI暴增！多空在当前位置激烈博弈。\n"
                    f"  -> 横盘蓄势结束后必有突破，可能是大涨也可能是大跌。\n"
                    f"  -> 建议等突破确认后再顺势进场，不要在突破前猜方向。")
    elif (oi_up and abs(oi_change_pct) > 20) or (oi_down and abs(oi_change_pct) > 20):
        oi_direction = "⚠️ OI一边倒"
        oi_signal = "neutral"
        situation = "情况⑥：OI一边倒 → 容易被插针清算"
        oi_note = (f"持仓量(OI) {oi_change_pct}%({time_diff_hours:.1f}h) | 价格 {price_change_pct}%\n"
                    f"  -> 【{situation}】\n"
                    f"  -> OI极端偏向某一方，持仓高度集中！\n"
                    f"  -> 这种结构极易被主力插针扫止损/爆合约。\n"
                    f"  -> 建议降低仓位、扩大止损距离，避免成为被收割的对象。")
    else:
        # OI变化 < 5%，属于横盘
        oi_direction = "NEUTRAL 观望"
        oi_signal = "neutral"
        oi_note = (f"持仓量(OI) {oi_change_pct}%({time_diff_hours:.1f}h) | 价格 {price_change_pct}%\n"
                    f"  -> OI变化微弱（{'OI稳定' if abs(oi_change_pct) < 1 else '略有增减'}），资金无明显方向")

    return {
        "note": f"**持仓量(OI)分析**\n{oi_note}{btc_note}",
        "direction": oi_direction,
        "signal": oi_signal,
        "current_oi": current_oi,
        "oi_change_pct": oi_change_pct,
        "price_change_pct": price_change_pct,
        "volume_change_pct": vol_change_pct,
        "time_diff_hours": time_diff_hours,
    }

def build_snipe_levels(results: dict, recommendation: str, price: float) -> dict:
    """
    生成狙击位布局模块。
    SHORT → 两个反弹沽空位
    LONG → 两个回踩买入位
    观望 → 给出双向参考
    返回 dict，包含表格文字 + 文字解说
    """
    tf_15m = results.get("15m", {})
    tf_1h  = results.get("1h", {})
    tf_4h  = results.get("4h", {})
    tf_labels = {"15m": "短线", "1h": "中线", "4h": "中长线"}

    # 收集各级 EMA 和 SR
    levels = []
    for tf_key, tf_data in [("15m", tf_15m), ("1h", tf_1h), ("4h", tf_4h)]:
        if not tf_data:
            continue
        label = tf_labels.get(tf_key, tf_key)
        p = tf_data.get("price", 0)
        ema7  = tf_data.get("ema7", 0)
        ema25 = tf_data.get("ema25", 0)
        ema99 = tf_data.get("ema99", 0)
        sr    = tf_data.get("sr", {})
        r_sup = sr.get("recent_low", 0)
        r_res = sr.get("recent_high", 0)
        levels.append({
            "tf": label,
            "price": p,
            "ema7": ema7, "ema25": ema25, "ema99": ema99,
            "sup": r_sup, "res": r_res,
        })

    def rr(entry, sl, tp):
        """计算盈亏比"""
        risk   = abs(sl - entry)
        reward = abs(tp - entry)
        if risk == 0:
            return "N/A"
        ratio = reward / risk
        return f"1:{ratio:.1f}"

    lines = []

    if "看多" in recommendation or "LONG" in recommendation:
        # ===== 做多：两个回踩买入点 =====
        # Level 1：最近支撑（EMA7 或 短线支撑）
        l1_entry  = None
        l1_label  = ""
        l1_reason = ""
        l1_sl     = None
        l1_tp     = None
        l1_tp_label = ""

        # 找最近支撑：在现价下方最近的EMA或SR
        candidates = []
        for l in levels:
            for val, name in [(l["ema7"], "EMA7"), (l["ema25"], "EMA25"), (l["sup"], "近撑")]:
                if 0 < val < price:
                    candidates.append((val, f"{l['tf']}{name}"))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            l1_entry, l1_label = candidates[0]
            l1_sl = round(l1_entry * 0.98, 6)
            l1_tp = round(l1_entry * 1.05, 6)
            l1_reason = f"回踩{l1_label}"

        # Level 2：更深支撑（EMA25 或 中线支撑）
        l2_entry  = None
        l2_label  = ""
        l2_reason = ""
        l2_sl     = None
        l2_tp     = None
        if len(candidates) > 1:
            l2_entry, l2_label = candidates[1]
            l2_sl = round(l2_entry * 0.98, 6)
            l2_tp = round(l2_entry * 1.05, 6)
            l2_reason = f"回踩{l2_label}"

        lines.append("### 六、多头狙击位布局（回踩买入）\n")
        lines.append("| 层级 | 入场价 | 止损价 | 止盈价 | 盈亏比 | 理由 |\n")
        lines.append("|------|-------|-------|-------|-------|------|\n")
        if l1_entry:
            r = rr(l1_entry, l1_sl, l1_tp)
            lines.append(f"| 第一狙击位 | ${l1_entry:.6f} | ${l1_sl:.6f} | ${l1_tp:.6f} | {r} | {l1_reason} |\n")
        if l2_entry:
            r = rr(l2_entry, l2_sl, l2_tp)
            lines.append(f"| 第二狙击位 | ${l2_entry:.6f} | ${l2_sl:.6f} | ${l2_tp:.6f} | {r} | {l2_reason} |\n")
        if not l1_entry:
            lines.append("| — | 暂无明确支撑位 | — | — | — | 等待价格止跌 |\n")

        # 生成大白话解说
        expl_parts = []
        if l1_entry:
            dist_pct = round((price - l1_entry) / price * 100, 2)
            r1 = rr(l1_entry, l1_sl, l1_tp)
            expl_parts.append(
                f"**第一狙击位 ${l1_entry:.6f}（距现价 {dist_pct}%）**：\n"
                f"选择理由：价格回踩 {l1_label} 时入场，这是短线/中线的天然支撑带。"
                f"止损设在 ${l1_sl:.6f}（-2%），止盈目标 ${l1_tp:.6f}（+5%），"
                f"盈亏比 {r1}，风险可控、赔率划算。\n"
            )
        if l2_entry:
            r2 = rr(l2_entry, l2_sl, l2_tp)
            dist2_pct = round((price - l2_entry) / price * 100, 2)
            expl_parts.append(
                f"**第二狙击位 ${l2_entry:.6f}（距现价 {dist2_pct}%）**：\n"
                f"选择理由：更深回踩 {l2_label}，是日线级别强支撑区域。"
                f"止损 ${l2_sl:.6f}（-2%），止盈 ${l2_tp:.6f}（+5%），"
                f"盈亏比 {r2}，适合轻仓试多。\n"
            )
        explanation = "".join(expl_parts) if expl_parts else "暂无明确狙击位，建议等待价格止跌。\n"
        return {"table": "".join(lines), "explanation": explanation}

    elif "看空" in recommendation or "SHORT" in recommendation:
        # ===== 做空：两个反弹沽空位 =====
        # Level 1：最近阻力（EMA7 或 短线阻力）
        l1_entry  = None
        l1_label  = ""
        l1_reason = ""
        l1_sl     = None
        l1_tp     = None

        candidates = []
        for l in levels:
            for val, name in [(l["ema7"], "EMA7"), (l["ema25"], "EMA25"), (l["ema99"], "EMA99"), (l["res"], "近阻")]:
                if val > price:
                    candidates.append((val, f"{l['tf']}{name}"))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            l1_entry, l1_label = candidates[0]
            l1_sl = round(l1_entry * 1.02, 6)
            l1_tp = round(l1_entry * 0.97, 6)
            l1_reason = f"反弹{l1_label}"

        # Level 2：更强阻力（EMA25 或 中线阻力）
        l2_entry  = None
        l2_label  = ""
        l2_reason = ""
        l2_sl     = None
        l2_tp     = None
        if len(candidates) > 1:
            l2_entry, l2_label = candidates[1]
            l2_sl = round(l2_entry * 1.02, 6)
            l2_tp = round(l2_entry * 0.97, 6)
            l2_reason = f"反弹{l2_label}"

        lines.append("### 六、空头狙击位布局（反弹沽空）\n")
        lines.append("| 层级 | 入场价 | 止损价 | 止盈价 | 盈亏比 | 理由 |\n")
        lines.append("|------|-------|-------|-------|-------|------|\n")
        if l1_entry:
            r = rr(l1_entry, l1_sl, l1_tp)
            lines.append(f"| 第一狙击位 | ${l1_entry:.6f} | ${l1_sl:.6f} | ${l1_tp:.6f} | {r} | {l1_reason} |\n")
        if l2_entry:
            r = rr(l2_entry, l2_sl, l2_tp)
            lines.append(f"| 第二狙击位 | ${l2_entry:.6f} | ${l2_sl:.6f} | ${l2_tp:.6f} | {r} | {l2_reason} |\n")
        if not l1_entry:
            lines.append("| — | 暂无明确阻力位 | — | — | — | 等待价格反弹至EMA阻力 |\n")

        expl_parts = []
        if l1_entry:
            dist_pct = round((l1_entry - price) / price * 100, 2)
            r1 = rr(l1_entry, l1_sl, l1_tp)
            expl_parts.append(
                f"**第一狙击位 ${l1_entry:.6f}（距现价 +{dist_pct}%）**：\n"
                f"选择理由：价格反弹至 {l1_label} 时，是空头二次发力的理想位置。"
                f"止损设在 ${l1_sl:.6f}（+2%），止盈目标 ${l1_tp:.6f}（-3%），"
                f"盈亏比 {r1}，宁可追空被止损也要死在阻力位，不侥幸。\n"
            )
        if l2_entry:
            r2 = rr(l2_entry, l2_sl, l2_tp)
            dist2_pct = round((l2_entry - price) / price * 100, 2)
            expl_parts.append(
                f"**第二狙击位 ${l2_entry:.6f}（距现价 +{dist2_pct}%）**：\n"
                f"选择理由：更强阻力 {l2_label}，是日线级别强压区。"
                f"止损 ${l2_sl:.6f}（+2%），止盈 ${l2_tp:.6f}（-3%），"
                f"盈亏比 {r2}，适合确认破位失败后顺势做空。\n"
            )
        explanation = "".join(expl_parts) if expl_parts else "暂无明确狙击位，建议等待价格反弹至阻力位。\n"
        return {"table": "".join(lines), "explanation": explanation}

    else:
        # ===== 观望：双向参考 =====
        # 做空阻力
        short_candidates = []
        for l in levels:
            for val, name in [(l["ema7"], "EMA7"), (l["ema25"], "EMA25"), (l["ema99"], "EMA99"), (l["res"], "近阻")]:
                if val > price:
                    short_candidates.append((val, f"{l['tf']}{name}"))
        # 做多支撑
        long_candidates = []
        for l in levels:
            for val, name in [(l["ema7"], "EMA7"), (l["ema25"], "EMA25"), (l["sup"], "近撑")]:
                if 0 < val < price:
                    long_candidates.append((val, f"{l['tf']}{name}"))

        short_candidates.sort()
        long_candidates.sort(key=lambda x: x[0], reverse=True)

        lines.append("### 六、多空狙击位参考（观望中）\n\n")
        if short_candidates:
            s1_e, s1_l = short_candidates[0]
            s1_sl = round(s1_e * 1.02, 6)
            s1_tp = round(s1_e * 0.97, 6)
            r1 = rr(s1_e, s1_sl, s1_tp)
            dist_s = round((s1_e - price) / price * 100, 2)
            lines.append(f"**做空参考（反弹至）：** ${s1_e:.6f}（+{dist_s}%）| SL ${s1_sl:.6f} | TP ${s1_tp:.6f} | {r1} | 理由：{s1_l}\n\n")
        if long_candidates:
            b1_e, b1_l = long_candidates[0]
            b1_sl = round(b1_e * 0.98, 6)
            b1_tp = round(b1_e * 1.05, 6)
            r2 = rr(b1_e, b1_sl, b1_tp)
            dist_b = round((price - b1_e) / price * 100, 2)
            lines.append(f"**做多参考（回踩至）：** ${b1_e:.6f}（-{dist_b}%）| SL ${b1_sl:.6f} | TP ${b1_tp:.6f} | {r2} | 理由：{b1_l}\n\n")
        if not short_candidates and not long_candidates:
            lines.append("暂无明确参考位，建议继续等待\n")

        # 观望大白话
        exp_parts = []
        if short_candidates and long_candidates:
            exp_parts.append(
                f"**当前方向不明，建议等待。**\n"
                f"多空都有参考位，但信号矛盾：反弹至 ${short_candidates[0][0]:.6f} 可试空（止损{short_candidates[0][0]*0.02:.6f}）"
                f"，回踩至 ${long_candidates[0][0]:.6f} 可试多（止损{long_candidates[0][0]*0.02:.6f}）。\n"
                f"**建议等其中一侧信号确认后再动手，不要在震荡中间猜方向。**\n"
            )
        elif short_candidates:
            exp_parts.append(f"**暂无做多信号。** 等待价格反弹至 ${short_candidates[0][0]:.6f} 再考虑做空。\n")
        elif long_candidates:
            exp_parts.append(f"**暂无做空信号。** 等待价格回踩至 ${long_candidates[0][0]:.6f} 再考虑做多。\n")
        else:
            exp_parts.append("当前无明确参考位，建议空仓等待。\n")
        explanation = "".join(exp_parts)
        return {"table": "".join(lines), "explanation": explanation}

def build_position_advice(symbol: str, price: float, recommendation: str, sltp: dict, bull_pct: float, avg_rsi: float) -> str:
    """
    生成仓位杠杆建议模块
    返回大白话文字
    """
    direction = sltp.get("direction", "LONG")
    sl = sltp.get("stop_loss", 0)
    tp = sltp.get("take_profit", 0)
    sl_pct = sltp.get("sl_pct", 2.0)
    tp_pct = sltp.get("tp_pct", 5.0)

    # 盈亏比
    if sl > 0 and tp > 0:
        risk = abs(sl - price)
        reward = abs(tp - price)
        rr_ratio = reward / risk if risk > 0 else 0
        rr_str = f"1:{rr_ratio:.1f}"
    else:
        rr_ratio = 0
        rr_str = "N/A"

    # 爆仓价估算（假设全仓模式，止损后剩余仓位被强平）
    if direction == "LONG":
        liq_price = round(price * (1 - sl_pct / 100 * 1.5), 6)
    else:
        liq_price = round(price * (1 + sl_pct / 100 * 1.5), 6)

    # 建议杠杆（根据止损%反推，安全杠杆 = 1/止损%）
    safe_leverage = min(20, max(2, int(1 / (sl_pct / 100))))
    recommended_leverage = max(3, min(safe_leverage - 2, 10))  # 比安全杠杆保守一点

    # 建议仓位
    if bull_pct >= 65:
        total_risk_pct = 8.0
        first_entry = 3.0
        second_entry = 5.0
        risk_level = "积极"
    elif bull_pct >= 55:
        total_risk_pct = 5.0
        first_entry = 2.0
        second_entry = 3.0
        risk_level = "适中"
    else:
        total_risk_pct = 3.0
        first_entry = 1.5
        second_entry = 1.5
        risk_level = "保守"

    # RSI叮嘱
    if avg_rsi >= 65:
        wait_note = "⚠️ RSI偏高，不建议此时追入，等回调再补第二笔"
        wait_for_confirm = True
    elif avg_rsi <= 35:
        wait_note = "⚠️ RSI偏低，若要做多建议轻仓试单，等止跌信号再补仓"
        wait_for_confirm = True
    else:
        wait_note = "✅ RSI正常，可以按计划分批建仓"
        wait_for_confirm = False

    if "观望" in recommendation or "看空" in recommendation and "看多" not in recommendation:
        if "看空" in recommendation:
            action = "建议做空" if "SHORT" in recommendation or "看空" in recommendation else "建议观望"
            return (
                f"**仓位杠杆建议（做空方向）**\n\n"
                f"- 做空方向：入场价约 ${price:.6f}，止损 ${sl:.6f}（+{sl_pct:.2f}%），止盈 ${tp:.6f}（-{tp_pct:.2f}%）\n"
                f"- 盈亏比：{rr_str}\n"
                f"- 建议总仓位：{total_risk_pct}% 资金\n"
                f"- 建议杠杆：{recommended_leverage}x（保守）\n"
                f"- 爆仓风险位置：${liq_price:.6f}\n"
                f"- {wait_note}\n"
            )
        else:
            return f"**仓位杠杆建议**：当前建议观望，无需制定具体仓位计划。\n"

    dir_emoji = "🟢" if direction == "LONG" else "🔴"
    action_word = "做多" if direction == "LONG" else "做空"

    return (
        f"**仓位杠杆建议**\n\n"
        f"**方向：** {dir_emoji} {action_word}\n"
        f"- 建议总仓位占资金：{total_risk_pct}%（{risk_level}型）\n"
        f"  - 第一笔建仓：{first_entry}% 资金（试单，确认后进）\n"
        f"  - 第二笔补仓：{second_entry}% 资金（回调确认后加码）\n"
        f"- 建议杠杆：{recommended_leverage}x（安全杠杆{safe_leverage}x，打8折留buffer）\n"
        f"- 止损设置：${sl:.6f}（-{sl_pct:.2f}%）\n"
        f"- 第一目标：${tp:.6f}（+{tp_pct:.2f}%）\n"
        f"- 爆仓风险位置：${liq_price:.6f}（距现价 {abs((liq_price-price)/price*100):.2f}%）\n"
        f"- 整体盈亏比：{rr_str}\n"
        f"- {wait_note}\n"
        f"- {'适合轻仓试单，不建议重仓' if wait_for_confirm else '可按计划分批建仓'}\n"
    )

def build_final_conclusion(symbol: str, price: float, recommendation: str, bull_pct: float,
                           avg_rsi: float, oi_info: dict, btc_corr: dict,
                           sltp: dict, divergence: bool, divergence_label: str) -> str:
    """
    生成最终结论模块
    输出：胜率评估 / 最大风险点 / 最佳入场方式 / 是否值得参与 / 短线or波段 / 最可能错在哪里
    """
    # 胜率评估
    if bull_pct >= 70:
        win_rate = "65-75%"
        win_note = "技术面+资金流双共振，多头信号强"
    elif bull_pct >= 60:
        win_rate = "55-65%"
        win_note = "偏多，但需注意RSI和OI的边际变化"
    elif bull_pct >= 45:
        win_rate = "40-55%"
        win_note = "方向不明确，属于高难度行情"
    elif bull_pct <= 30:
        win_rate = "35-50%"
        win_note = "偏空为主，不建议逆势抄底"
    else:
        win_rate = "50%左右"
        win_note = "多空均衡，等待突破确认"

    # 最大风险点
    risk_points = []
    if avg_rsi >= 65:
        risk_points.append(f"RSI超买({avg_rsi})：追多随时被埋")
    if avg_rsi <= 30:
        risk_points.append(f"RSI超卖({avg_rsi})：可能是下跌中继，抄底抄到半山腰")
    if oi_info.get("oi_change_pct", 0) > 10:
        risk_points.append(f"OI急剧增加{oi_info['oi_change_pct']:.1f}%：多空博弈极端，易被插针")
    if oi_info.get("oi_change_pct", 0) < -10:
        risk_points.append(f"OI急剧萎缩{abs(oi_info['oi_change_pct']):.1f}%：资金撤离，上涨缺乏动力")
    if btc_corr.get("correlation") == "反向":
        risk_points.append("BTC反向走势：大盘跌时该币可能逆势，走势独立难判断")
    if divergence:
        risk_points.append("量价背离：当前价格走势与资金流不一致，可能出现假突破")
    if not risk_points:
        risk_points.append("暂时无明显极端风险点，但仍需带止损操作")

    # 最佳入场方式
    if avg_rsi <= 35 or avg_rsi >= 65:
        entry = "等RSI回归正常区间（40-60）后再入场，避免在极端区域操作"
    elif oi_info.get("oi_change_pct", 0) > 10:
        entry = "等OI稳定（不再暴增）后再入场，避免在OI峰值被插针"
    else:
        entry = "建议分批建仓：第一笔{2-3%资金}轻仓试单，止损后不再补仓；等走出3根以上同向K线再加第二笔"

    # 是否值得参与
    if bull_pct >= 60 and not divergence and avg_rsi < 65:
        worth = "值得参与 ✅"
        worth_reason = (
            f"偏多({bull_pct}%)+无背离+RSI正常区间，"
            f"盈亏比合理，是近期较好的交易机会"
        )
    elif bull_pct >= 55 and avg_rsi < 60:
        worth = "可轻仓参与 ⚠️"
        worth_reason = (
            f"有方向但信号不够强，建议仓位控制在5%以内，"
            f"严格止损，不宜重仓博"
        )
    elif divergence or avg_rsi >= 70 or avg_rsi <= 25:
        worth = "不建议参与 ❌"
        worth_reason = (
            f"出现{'背离' if divergence else 'RSI极端区域'}，"
            f"风险大于机会，强行操作大概率亏损"
        )
    else:
        worth = "观望为主 😐"
        worth_reason = "信号模糊，等局势明朗再动手，不要在震荡中猜方向"

    # 更适合短线还是波段
    if avg_rsi <= 35:
        horizon = "短线超跌反弹（RSI超卖，反弹后及时止盈，不恋战）"
    elif avg_rsi >= 65:
        horizon = "短线偏空（RSI超买，上方空间有限，快进快出）"
    elif "BULL排列" in str([r.get("trend") for r in {}]):
        horizon = "波段持有（多周期共振，趋势延续性强）"
    else:
        horizon = "短线为主（震荡结构明显，不适合长拿）"

    # 最可能错在哪里
    mistake = ""
    if avg_rsi <= 35:
        mistake = "抄底抄在半山腰：RSI超卖后可能继续跌，不要觉得跌多了就能买"
    elif avg_rsi >= 65:
        mistake = "追多被回调埋：RSI超买后一根阴线就能吃掉所有利润"
    elif oi_info.get("oi_change_pct", 0) > 10:
        mistake = "在OI峰值入场被插针：OI暴涨后极易出现瞬时插针，止损要留足空间"
    elif btc_corr.get("correlation") == "反向":
        mistake = "误判该币独立走势：以为跟BTC但实际反向，独立币操作难度更大"
    elif divergence:
        mistake = f"假突破：{divergence_label or '量价背离时方向极易反复'}，突破后很快反转"
    else:
        mistake = "止损被扫：支撑/阻力判断不够精准，震荡行情中容易被反复扫止损"

    rec_emoji = "📈" if "看多" in recommendation else ("📉" if "看空" in recommendation else "⏸️")
    return (
        f"**最终结论**\n\n"
        f"**综合评级：** {rec_emoji} {recommendation}\n\n"
        f"**胜率评估：** {win_rate}（{win_note}）\n\n"
        f"**最大风险点：**\n"
        + "\n".join(f"- {r}" for r in risk_points) + f"\n\n"
        f"**最佳入场方式：** {entry}\n\n"
        f"**是否值得参与：** {worth} | {worth_reason}\n\n"
        f"**更适合做：** {horizon}\n\n"
        f"**最可能错在哪里：** {mistake}\n"
    )

def analyze_timeframe(symbol: str, interval: str, label: str) -> dict:
    klines = fetch_klines(symbol, interval, limit=200)
    if not klines:
        return None
    closes   = [float(k[4]) for k in klines]
    price    = closes[-1]
    ema7     = calc_ema_latest(closes, 7)
    ema25    = calc_ema_latest(closes, 25)
    ema99    = calc_ema_latest(closes, 99)
    rsi      = calc_rsi(closes, 14)
    pattern  = detect_kline_pattern(klines)
    sr        = detect_sr_levels(klines)
    vol_prof  = calc_volume_profile(klines[-20:])

    if price > ema7 > ema25 > ema99:
        trend = "BULL排列"
    elif price < ema7 < ema25 < ema99:
        trend = "BEAR排列"
    elif price > ema99 and ema7 > ema25:
        trend = "BULL偏多"
    elif price < ema99 and ema7 < ema25:
        trend = "BEAR偏空"
    else:
        trend = "SIDE震荡"

    if rsi >= 70:       zone = "OVERBOUGHT"
    elif rsi <= 30:     zone = "OVERSOLD"
    elif rsi >= 60:     zone = "STRONG"
    elif rsi <= 40:     zone = "WEAK"
    else:               zone = "NORMAL"

    return {
        "label": label,
        "price": round(price, 6),
        "ema7": ema7, "ema25": ema25, "ema99": ema99,
        "rsi": rsi,
        "trend": trend,
        "zone": zone,
        "pattern": pattern["pattern"],
        "pattern_signal": pattern["signal"],
        "volume_profile": vol_prof,
        "sr": sr,
        "price_change_pct": round((price - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else 0
    }

TREND_EMOJI = {
    "BULL排列": "🟢 多头排列", "BEAR排列": "🔴 空头排列",
    "BULL偏多": "🟢 偏多",     "BEAR偏空": "🔴 偏空",
    "SIDE震荡": "🟡 震荡",
}
ZONE_EMOJI = {
    "OVERBOUGHT": "⚠️ 超买区", "OVERSOLD": "⚠️ 超卖区",
    "STRONG": "🟡 偏强",       "WEAK": "🟡 偏弱",
    "NORMAL": "✅ 正常区间",
}

def analyze(symbol: str):
    intervals = [
        ("15m", "15分钟（短线）"),
        ("1h",  "1小时（中线）"),
        ("4h",  "4小时（中长线）"),
        ("1d",  "日线（波段/大级别）"),
    ]

    results = {}
    for interval, label in intervals:
        r = analyze_timeframe(symbol, interval, label)
        if r:
            results[interval] = r

    if not results:
        return {"error": f"无法获取 {symbol} 数据"}

    rsi_values = [r["rsi"] for r in results.values()]
    avg_rsi    = round(sum(rsi_values) / len(rsi_values), 2) if rsi_values else 50

    main_tf   = results.get("4h") or results.get("1h")
    short_tf  = results.get("15m")
    price     = short_tf["price"] if short_tf else main_tf["price"]
    sr_main   = main_tf["sr"] if main_tf else {}
    sr_4h     = results.get("4h", {}).get("sr", {}) if "4h" in results else sr_main

    # ========== 第一步：技术面评分（EMA + 形态 + 突破）==========
    tech_bullish = tech_bearish = 0
    for d in results.values():
        if d["pattern_signal"] == "bullish":   tech_bullish += 2
        elif d["pattern_signal"] == "bearish":  tech_bearish += 2
        # RSI 不再直接加分：超卖是反弹预警，不是看多理由
        if d["rsi"] > 70:     tech_bearish += 1
        if "BULL" in d["trend"]: tech_bullish += 2
        elif "BEAR" in d["trend"]: tech_bearish += 2
        if d["price"] > d["ema99"]: tech_bullish += 1
        else: tech_bearish += 1
    if sr_main.get("breakout_up"):   tech_bullish += 3
    if sr_main.get("breakout_down"): tech_bearish += 3

    tech_total = tech_bullish + tech_bearish
    tech_bull_pct = round(tech_bullish / tech_total * 100, 1) if tech_total > 0 else 50

    # ========== 第二步：OI 资金流评分 ==========
    oi_info = analyze_oi(symbol, price)
    oi_signal = oi_info.get("signal", "unknown")
    oi_direction = oi_info.get("direction", "unknown")

    # OI 信号权重：强于技术指标
    # 规则：价格跌 + OI跌 = 多头踩踏离场 → 强制看空（不看技术分）
    price_change = oi_info.get("price_change_pct", 0)
    oi_change = oi_info.get("oi_change_pct", 0)
    volume_signal = oi_info.get("volume_signal", None)

    divergence = False
    force_bearish = False
    force_bullish = False
    bear_smash_active = False

    # ========== 检测空头砸盘（强看空）==========
    # 条件：中线以上周期跌幅 > 4% 且成交量放大
    for tf_key in ["1h", "4h"]:
        if tf_key in results:
            tf = results[tf_key]
            tf_price_chg = tf.get("price_change_pct", 0)
            vol_up = "放" in tf.get("volume_profile", "") or "UP" in tf.get("volume_profile", "")
            if tf_price_chg < -4 and vol_up:
                force_bearish = True
                divergence = True
                bear_smash_active = True
                break

    # ========== 背离检测：虚假拉升 & 空头压盘 ==========
    fake_move = False   # 价格涨 + OI跌
    bear_squeeze = False  # 价格跌 + OI涨
    divergence_label = ""

    if price_change > 0 and oi_change < -3 and oi_signal != "bullish":
        fake_move = True
        divergence_label = "⚠️ **虚假拉升**：价格往上走，但持仓量在萎缩，这是多头诱多、随时可能崩"
    elif price_change < 0 and oi_change > 3 and oi_signal == "bearish":
        bear_squeeze = True
        divergence_label = "🔴 **空头强势压盘**：价格下跌+持仓量飙升，空头在猛力加仓，跌势未止"

    # 强制看空：价格跌 + OI跌（多头踩踏）
    if not force_bearish and price_change < 0 and oi_change < 0 and oi_signal == "bearish":
        force_bearish = True
        divergence = True
    # 强制看空：价格跌 + OI涨（空头主动进攻）
    elif not force_bearish and price_change < 0 and oi_change > 0 and oi_signal == "bearish":
        force_bearish = True
        divergence = True
    # 价格跌 + 成交量放大（无OI时）：资金离场
    elif not force_bearish and price_change < 0 and volume_signal == "bearish":
        force_bearish = True
        divergence = True
    # RSI 超卖反弹预警：只有当 RSI < 30 且 OI 稳住或缩量时才给多头加分
    elif avg_rsi < 30 and oi_change > -1:
        force_bullish = True
    # RSI < 30 但成交量萎缩（无OI时）：缩量跌，不盲目看多
    elif avg_rsi < 30 and volume_signal == "neutral":
        divergence = True  # 仅提示，不强制

    # ========== 第三步：综合建议 ==========
    if force_bearish:
        recommendation = "📉 看空"
        if bear_smash_active:
            reason = "空头砸盘：价格急跌+成交量放大，趋势向下动能强。严禁逆势抄底"
        elif oi_signal == "bearish":
            reason = "资金流强偏空：价格与持仓量同跌，多头踩踏离场。趋势未止，不宜逆势抄底"
        else:
            reason = "量价背离：价格跌但成交量放大，资金离场迹象明显"
        final_bull_pct = 15.0
        divergence = True
    elif force_bullish:
        recommendation = "📈 看多"
        reason = "RSI 超卖预警，且 OI 变化率收窄，存在反弹机会"
        final_bull_pct = 70.0
    elif tech_bull_pct >= 65 and oi_signal == "bullish":
        recommendation = "📈 看多"
        reason = f"技术指标偏多({tech_bull_pct}%)，且资金流同步看多"
        final_bull_pct = tech_bull_pct
    elif tech_bull_pct <= 35 and oi_signal == "bearish":
        recommendation = "📉 看空"
        reason = f"技术指标偏空({round(100-tech_bull_pct,1)}%)，且资金流同步看空"
        final_bull_pct = tech_bull_pct
    elif tech_bull_pct >= 65 and oi_signal == "unknown" and volume_signal == "bearish":
        recommendation = "⏸️ 观望（量价背离）"
        reason = f"技术指标偏多({tech_bull_pct}%)，但量价分析显示资金离场，建议等待验证"
        final_bull_pct = tech_bull_pct
        divergence = True
    elif tech_bull_pct >= 65 and oi_signal == "unknown" and volume_signal == "bullish":
        recommendation = "📈 看多（成交量验证）"
        reason = f"技术指标偏多({tech_bull_pct}%)，成交量配合上涨，资金流入信号积极"
        final_bull_pct = tech_bull_pct
    elif tech_bull_pct >= 55 and oi_signal == "unknown" and volume_signal is None:
        recommendation = "📈 看多（OI数据暂缺）"
        reason = f"技术指标偏多({tech_bull_pct}%)，但缺少资金流验证（首次分析OI数据待积累）"
        final_bull_pct = tech_bull_pct
        divergence = True
    elif tech_bull_pct <= 45 and oi_signal == "unknown" and volume_signal == "bearish":
        recommendation = "📉 看空（成交量验证）"
        reason = f"技术指标偏空({round(100-tech_bull_pct,1)}%)，成交量放大确认资金流出"
        final_bull_pct = tech_bull_pct
    elif tech_bull_pct <= 45 and oi_signal == "unknown":
        recommendation = "📉 看空（OI数据暂缺）"
        reason = f"技术指标偏空({round(100-tech_bull_pct,1)}%)，但缺少资金流验证"
        final_bull_pct = tech_bull_pct
        divergence = True
    elif divergence:
        recommendation = "⏸️ 观望"
        reason = f"技术指标({tech_bull_pct}%偏多)与资金流背离，等待方向确认"
        final_bull_pct = tech_bull_pct
    else:
        recommendation = "⏸️ 观望"
        reason = f"技术指标与资金流分歧，多空信号不明确"
        final_bull_pct = tech_bull_pct
        divergence = True

    bear_pct = round(100 - final_bull_pct, 1)

    # 止损止盈（基于综合评分）
    sr_ref = (results.get("1h") or main_tf or {}).get("sr", sr_4h)
    sltp = calc_stop_loss_take_profit(sr_ref, price, final_bull_pct)

    if sr_main.get("breakout_up"):
        reason += "；价格突破近期阻力位"
    elif sr_main.get("breakout_down"):
        reason += "；价格跌破近期支撑位"

    # ========== BTC联动分析 ==========
    btc_corr = fetch_btc_comparison(symbol)

    # 融合BTC联动到推荐逻辑
    btc_trend_4h = btc_corr.get("btc_trend_4h", "unknown")
    btc_trend_1h = btc_corr.get("btc_trend_1h", "unknown")
    if btc_trend_4h == "BULL 多头" and "看空" in recommendation:
        btc_corr["correlation"] = "反向"
    elif btc_trend_4h == "BEAR 空头" and "看多" in recommendation:
        btc_corr["correlation"] = "反向"
    elif btc_trend_4h == "BULL 多头" and "看多" in recommendation:
        btc_corr["correlation"] = "同向"
    elif btc_trend_4h == "BEAR 空头" and "看空" in recommendation:
        btc_corr["correlation"] = "同向"
    elif btc_trend_4h == "SIDE 震荡":
        btc_corr["correlation"] = "独立行情"
    else:
        btc_corr["correlation"] = "独立行情"

    # ========== 成交量结构深度分析 ==========
    vol_klines = fetch_klines(symbol, "4h", limit=20)
    vol_pattern = detect_volume_pattern(vol_klines) if vol_klines else {}

    # 构报告
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    report = f"## {symbol.upper()} 实时技术分析报告\n\n"
    report += f"**分析时间：** {now_str} | **当前价格：** ${price:.6f}\n\n---\n\n"

    # ========== 第一节：大级别趋势（日线方向）==========
    report += "### 一、大级别趋势（每日/波段方向）\n\n"
    tf_1d = results.get("1d")
    if tf_1d:
        d1 = tf_1d
        pat_name = PATTERN_NAMES.get(d1["pattern"], d1["pattern"])
        report += f"**日线（波段方向）**\n"
        report += f"- 价格：${d1['price']:.6f} ({d1['price_change_pct']:+.2f}%) | {TREND_EMOJI.get(d1['trend'], d1['trend'])}\n"
        report += f"- EMA(7/25/99)：${d1['ema7']:.4f} / ${d1['ema25']:.4f} / ${d1['ema99']:.4f}\n"
        report += f"- RSI(14)：{d1['rsi']} — {ZONE_EMOJI.get(d1['zone'], d1['zone'])}\n"
        report += f"- K线形态：{pat_name}\n\n"
        if "BULL排列" in d1["trend"] or "BULL偏多" in d1["trend"]:
            report += "**大级别判断：** 日线偏多格局，趋势向上，中长线做多为主。\n\n"
        elif "BEAR排列" in d1["trend"] or "BEAR偏空" in d1["trend"]:
            report += "**大级别判断：** 日线偏空格局，趋势向下，逢高做空为主。\n\n"
        else:
            report += "**大级别判断：** 日线震荡结构，无明显趋势，等待突破后再跟进。\n\n"
    else:
        report += "日线数据暂不可用，跳过\n\n"

    # BTC联动
    report += f"**BTC联动：** {btc_corr.get('correlation', '独立行情')}（BTC 4H: {btc_corr.get('btc_trend_4h', 'N/A')} | BTC 1H: {btc_corr.get('btc_trend_1h', 'N/A')}）\n\n"
    corr_note = ""
    if btc_corr.get("correlation") == "同向":
        corr_note = f"BTC趋势一致（{btc_corr.get('btc_trend_4h', '')}），该币跟涨跟跌，可参考BTC顺势操作"
    elif btc_corr.get("correlation") == "反向":
        corr_note = "⚠️ BTC趋势相反，该币走独立行情，需单独判断，不能盲目跟BTC操作"
    else:
        corr_note = "BTC无明确方向（震荡），该币走出独立行情概率大，需等待方向明确"
    report += f"- {corr_note}\n\n"

    # ========== 第二节：多周期趋势评估 ==========
    report += "---\n\n### 二、多周期趋势评估（15分钟/1小时/4小时/日线）\n\n"
    tf_order = ["15m", "1h", "4h", "1d"]
    tf_labels = {"15m": "短线", "1h": "中线", "4h": "中长线", "1d": "日线"}
    tf_emoji  = {"15m": "🔹", "1h": "📍", "4h": "🔸", "1d": "🗓️"}

    for tf in tf_order:
        if tf not in results or tf == "1d":
            continue
        d = results[tf]
        pat_name = PATTERN_NAMES.get(d["pattern"], d["pattern"])
        report += f"**{tf_emoji.get(tf,'*')} {d['label']}**\n"
        report += f"- 价格：${d['price']:.6f} ({d['price_change_pct']:+.2f}%) | {TREND_EMOJI.get(d['trend'], d['trend'])}\n"
        report += f"- EMA(7/25/99)：${d['ema7']:.4f} / ${d['ema25']:.4f} / ${d['ema99']:.4f}\n"
        report += f"- RSI(14)：{d['rsi']} — {ZONE_EMOJI.get(d['zone'], d['zone'])}\n"
        report += f"- K线形态：{pat_name}\n"
        report += f"- 成交量：{d['volume_profile']}\n\n"

    # 支撑阻力汇总表
    report += "| 周期 | 近期阻力 | 近期支撑 | 是否突破 |\n"
    report += "|------|---------|---------|----------|\n"
    for tf in ["15m", "1h", "4h"]:
        if tf not in results:
            continue
        d = results[tf]
        sr = d["sr"]
        if sr.get("breakout_up"):
            breakout = "✅ 突破阻力"
        elif sr.get("breakout_down"):
            breakout = "❌ 跌破支撑"
        else:
            breakout = "-"
        report += f"| {tf_labels[tf]} | ${sr['recent_high']:.4f} | ${sr['recent_low']:.4f} | {breakout} |\n"
    report += "\n"

    if avg_rsi > 65:
        rsi_note = "⚠️ 超买区域，注意回调风险"
    elif avg_rsi < 30:
        rsi_note = "⚠️ 超卖区域（反弹预警，非做多信号）"
    elif avg_rsi < 40:
        rsi_note = "⚠️ 超卖区域，存在反弹机会"
    else:
        rsi_note = "✅ 正常区间"
    report += f"**平均RSI(14)：** {avg_rsi} — {rsi_note}\n\n"

    # ========== 第三节：成交量结构深度分析 ==========
    report += "---\n\n### 三、成交量结构深度分析\n\n"
    if vol_pattern:
        report += "**最近5根K线逐根量能：**\n"
        for item in vol_pattern.get("逐根量能", []):
            report += f"- {item}\n"
        report += f"\n**总体判断：** {vol_pattern.get('总体判断', 'N/A')}\n"
        report += f"**量价配合：** {vol_pattern.get('量价配合', 'N/A')}\n"
        report += f"**滞涨/吸筹识别：** {vol_pattern.get('滞涨/吸筹', 'N/A')}\n\n"
    else:
        report += "成交量结构数据暂不可用\n\n"

    # ========== 第四节：持仓量(OI)深度分析 ==========
    report += "---\n\n### 四、持仓量(OI)深度分析\n\n"
    report += oi_info["note"] + "\n\n"
    if divergence_label:
        report += f"{divergence_label}\n\n"

    # ========== 第五节：资金费率深度分析 ==========
    report += "---\n\n### 五、资金费率(Funding Rate)深度分析\n\n"
    funding_info = analyze_funding_rate(symbol, price, price_change)
    fr_label = funding_info.get("label", "")
    if fr_label:
        report += f"**{fr_label}**\n\n"
        report += funding_info["note"] + "\n\n"
    else:
        report += "资金费率数据暂不可用\n\n"

    # ========== 第六节：综合技术评级 + 止损止盈 ==========
    dir_emoji = "🟢" if sltp["direction"] == "LONG" else "🔴"

    # 技术评级
    tech_rating = ""
    if tech_bull_pct >= 65:
        tech_rating = "A（偏多）"
    elif tech_bull_pct >= 55:
        tech_rating = "B（轻微偏多）"
    elif tech_bull_pct >= 45:
        tech_rating = "C（中性）"
    elif tech_bull_pct >= 35:
        tech_rating = "D（轻微偏空）"
    else:
        tech_rating = "F（偏空）"

    report += "---\n\n### 六、综合技术评级 + 止损止盈建议\n\n"
    report += f"**技术评级：** {tech_rating}（综合得分：{tech_bull_pct}% 偏多）\n"
    report += f"**综合建议：** {recommendation} — {reason}\n\n"

    report += f"| 方向 | 入场价 | 止损价 | 止损% | 第一目标 | 第二目标 | 止盈% | 盈亏比 |\n"
    report += f"|------|-------|-------|--------|---------|---------|-------|-------|\n"

    # 第二目标（基于2倍第一目标的空间）
    tp1_pct = sltp["tp_pct"]
    tp2_pct = round(tp1_pct * 1.5, 2)
    if sltp["direction"] == "LONG":
        tp1 = round(price * (1 + tp1_pct / 100), 6)
        tp2 = round(price * (1 + tp2_pct / 100), 6)
    else:
        tp1 = round(price * (1 - tp1_pct / 100), 6)
        tp2 = round(price * (1 - tp2_pct / 100), 6)

    # 整体盈亏比
    risk = abs(sltp["stop_loss"] - price)
    reward1 = abs(tp1 - price)
    reward2 = abs(tp2 - price)
    rr1 = f"1:{reward1/risk:.1f}" if risk > 0 else "N/A"
    rr2 = f"1:{reward2/risk:.1f}" if risk > 0 else "N/A"

    report += f"| {dir_emoji} {sltp['direction']} | ${sltp['entry']:.6f} | ${sltp['stop_loss']:.6f} | -{sltp['sl_pct']:.2f}% | ${tp1:.6f} | ${tp2:.6f} | +{tp2_pct:.2f}% | {rr1} |\n\n"
    report += f"*注：止损参考近期{'支撑' if sltp['direction']=='LONG' else '阻力'}位；第一目标参考近期{'阻力' if sltp['direction']=='LONG' else '支撑'}位；整体盈亏比 {rr2}\n\n"

    # RSI叮嘱
    if avg_rsi >= 65:
        report += "⚠️ **【RSI叮嘱】**：当前RSI偏高，继续追多风险极大！不要追高，等价格回调到狙击位再进场。\n\n"
    elif avg_rsi >= 55:
        report += "⚠️ **【RSI叮嘱】**：RSI已进入偏强区域，上方空间有限，不鼓励追多。\n\n"
    elif avg_rsi <= 30:
        report += "⚠️ **【RSI叮嘱】**：RSI超卖，反弹预警但不可盲目抄底，等止跌信号确认。\n\n"

    # ========== 第七节：狙击位布局 + 仓位杠杆建议 ==========
    report += "---\n\n### 七、狙击位布局 + 仓位杠杆建议\n\n"

    sniper = build_snipe_levels(results, recommendation, price)
    # 去掉"### 六、"的标题前缀，因为已经是第七节
    sniper_table = sniper["table"]
    if "### 六、" in sniper_table:
        sniper_table = sniper_table.replace("### 六、", "#### 狙击位\n", 1)
    report += sniper_table + "\n"
    if sniper["explanation"]:
        report += f"**狙击位解说：**\n{sniper['explanation']}\n\n"
    report += "---\n\n"
    report += build_position_advice(symbol, price, recommendation, sltp, final_bull_pct, avg_rsi) + "\n"

    # ========== 第八节：最终结论 ==========
    report += "---\n\n### 八、最终结论\n\n"
    report += build_final_conclusion(
        symbol, price, recommendation, final_bull_pct,
        avg_rsi, oi_info, btc_corr, sltp, divergence, divergence_label
    ) + "\n"

    return {
        "report": report,
        "bull_pct": final_bull_pct,
        "avg_rsi": avg_rsi,
        "oi_info": oi_info,
        "sltp": sltp,
        "recommendation": recommendation,
        "divergence": divergence,
        "divergence_label": divergence_label,
        "btc_corr": btc_corr,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance 深度技术分析 v3")
    parser.add_argument("symbol", help="交易对，如 BTCUSDT")
    args = parser.parse_args()
    result = analyze(args.symbol)
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["report"])
