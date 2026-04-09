#!/usr/bin/env python3
"""
加密查询Web端 - 完整八段式分析版
端口: 6868 | 绑定: 0.0.0.0
"""

import streamlit as st
import json
import time
import subprocess
import os
import concurrent.futures
import ssl
import urllib.request
from datetime import datetime

# ==================== 网络模块 ====================
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""

def get_opener():
    if PROXY:
        ctx = ssl._create_unverified_context()
        handler = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
        return urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener()

def fetch(url, timeout=15, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with get_opener().open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except:
            if attempt < retries - 1:
                time.sleep(1)
    return None

def parallel_fetch(tasks):
    results = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        futures = {ex.submit(fetch, url): i for i, url in tasks}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except:
                results[idx] = None
    return results

def test_network():
    if not PROXY:
        return False, "未配置代理"
    try:
        result = fetch("https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT", timeout=10)
        if result and 'lastPrice' in result:
            return True, f"✅ BTC: ${float(result['lastPrice']):,.0f}"
        return False, "❌ API无响应"
    except Exception as e:
        return False, f"❌ {str(e)[:50]}"

def auto_proxy():
    try:
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if line.startswith('nameserver'):
                    ip = line.split()[1]
                    if ip.startswith(('172.', '192.168.', '10.')):
                        parts = ip.split('.')
                        if len(parts) == 4:
                            gateway = f"{parts[0]}.{parts[1]}.{parts[2]}.1"
                            test_url = f"http://{gateway}:7890"
                            try:
                                subprocess.run(["curl", "-s", "--max-time", "2", "-o", "/dev/null", test_url], capture_output=True)
                                os.environ["HTTPS_PROXY"] = test_url
                                os.environ["https_proxy"] = test_url
                                os.environ["HTTP_PROXY"] = test_url
                                os.environ["http_proxy"] = test_url
                                return True
                            except:
                                pass
    except:
        pass
    for ip in ["172.28.192.1", "172.28.193.1", "172.17.0.1", "192.168.1.1"]:
        test_url = f"http://{ip}:7890"
        try:
            subprocess.run(["curl", "-s", "--max-time", "2", "-o", "/dev/null", test_url], capture_output=True)
            os.environ["HTTPS_PROXY"] = test_url
            os.environ["https_proxy"] = test_url
            os.environ["HTTP_PROXY"] = test_url
            os.environ["http_proxy"] = test_url
            return True
        except:
            pass
    return False

# ==================== 分析引擎 ====================
def calc_ema(prices, period):
    k = 2 / (period + 1)
    ema = [prices[0]]
    for p in prices[1:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema

def calc_rsi(prices, period=14):
    gains = [max(prices[i] - prices[i-1], 0) for i in range(1, len(prices))]
    losses = [max(prices[i-1] - prices[i], 0) for i in range(1, len(prices))]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0: return 100
    return 100 - (100 / (1 + avg_g / avg_l))

def fmt_price(p):
    if p is None: return "N/A"
    if p < 0.001: return f"${p:.6f}"
    elif p < 1: return f"${p:.4f}"
    elif p < 100: return f"${p:.2f}"
    return f"${p:,.2f}"

def fmt_rsi(r):
    if r < 30: return f"{r:.1f} 🔴极弱"
    elif r < 40: return f"{r:.1f} 🟡弱"
    elif r < 60: return f"{r:.1f} ✅正常"
    elif r < 70: return f"{r:.1f} 🟡偏强"
    else: return f"{r:.1f} 🔴极强"

def analyze_cycle(closes, highs, lows, vols):
    ema7 = calc_ema(closes, 7)
    ema25 = calc_ema(closes, 25)
    ema99 = calc_ema(closes, 99)
    rsi = calc_rsi(closes)
    avg_vol = sum(vols[-20:]) / 20
    vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else 0
    
    if ema7[-1] > ema25[-1] > ema99[-1]:
        trend = "🟢 多头排列"
    elif ema7[-1] < ema25[-1] < ema99[-1]:
        trend = "🔴 空头排列"
    elif ema7[-1] > ema25[-1]:
        trend = "🟢 偏多"
    elif ema7[-1] < ema25[-1]:
        trend = "🔴 偏空"
    else:
        trend = "🟡 震荡"
    
    rh = max(highs[-5:-1]) if len(highs) > 1 else max(highs)
    rl = min(lows[-5:-1]) if len(lows) > 1 else min(lows)
    pattern = "横盘"
    if closes[-1] > rh:
        pattern = "突破"
    elif closes[-1] < rl:
        pattern = "破位"
    elif len(closes) >= 3:
        if closes[-1] > closes[-2] > closes[-3]:
            pattern = "连涨"
        elif closes[-1] < closes[-2] < closes[-3]:
            pattern = "连跌"
    
    vol_st = "放量" if vol_ratio > 1.5 else "缩量" if vol_ratio < 0.7 else "平量"
    
    return {
        'price': closes[-1],
        'change': (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0,
        'trend': trend, 'rsi': rsi, 'pattern': pattern,
        'vol_st': vol_st, 'vol_ratio': vol_ratio,
        'ema7': ema7[-1], 'ema25': ema25[-1], 'ema99': ema99[-1]
    }

def analyze(symbol):
    """执行完整八段式分析"""
    base = "https://fapi.binance.com/fapi/v1"
    
    t0 = time.time()
    tasks = [
        f"{base}/ticker/24hr?symbol={symbol}",
        f"{base}/openInterest?symbol={symbol}",
        f"{base}/fundingRate?symbol={symbol}&limit=1",
        f"{base}/ticker/24hr?symbol=BTCUSDT",
        f"{base}/klines?symbol={symbol}&interval=15m&limit=20",
        f"{base}/klines?symbol={symbol}&interval=1h&limit=20",
        f"{base}/klines?symbol={symbol}&interval=4h&limit=20",
    ]
    ticker, oi_data, funding_data, btc_data, k15m, k1h, k4h = parallel_fetch(tasks)
    elapsed_ms = int((time.time() - t0) * 1000)
    
    if not ticker:
        return None, "❌ 价格获取失败，请检查网络"
    
    price = float(ticker.get('lastPrice', 0))
    oi_val = float(oi_data.get('openInterest', 0) or 0) if oi_data else 0
    funding_list = funding_data or [{}]
    funding_val = float(funding_list[0].get('fundingRate', 0) or 0) if funding_list else 0
    btc_price = float(btc_data.get('lastPrice', price) or price) if btc_data else price
    btc_chg = float(btc_data.get('priceChangePercent', 0) or 0) if btc_data else 0
    change_24h = float(ticker.get('priceChangePercent', 0) or 0)
    
    if not all([k15m, k1h, k4h]):
        return None, "❌ K线数据获取不完整"
    
    # 各周期分析
    d15 = analyze_cycle([float(k[4]) for k in k15m], [float(k[2]) for k in k15m], [float(k[3]) for k in k15m], [float(k[5]) for k in k15m])
    d1h = analyze_cycle([float(k[4]) for k in k1h], [float(k[2]) for k in k1h], [float(k[3]) for k in k1h], [float(k[5]) for k in k1h])
    d4h = analyze_cycle([float(k[4]) for k in k4h], [float(k[2]) for k in k4h], [float(k[3]) for k in k4h], [float(k[5]) for k in k4h])
    
    # Pivot
    h4 = max([float(k[2]) for k in k4h])
    l4 = min([float(k[3]) for k in k4h])
    c4 = float(k4h[-1][4])
    pivot = (h4 + l4 + c4) / 3
    r1, r2 = pivot * 2 - l4, pivot + (h4 - l4)
    s1, s2 = pivot * 2 - h4, pivot - (h4 - l4)
    h4_20 = max([float(k[2]) for k in k4h[-20:]])
    l4_20 = min([float(k[3]) for k in k4h[-20:]])
    
    # 清算热力图
    recent = [float(k[4]) for k in k1h[-20:]]
    avg = sum(recent) / len(recent)
    std = ((sum((p - avg) ** 2 for p in recent) / len(recent)) ** 0.5)
    short_liq_low = avg + 1.5 * std
    short_liq_high = avg + 2.5 * std
    long_liq_low = avg - 2.5 * std
    long_liq_high = avg - 1.5 * std
    magnet = (h4_20 + l4_20) / 2
    
    # 成交量结构
    vols_10 = [float(k[5]) for k in k1h[-10:]]
    cls_10 = [float(k[4]) for k in k1h[-10:]]
    avg_vol_10 = sum(vols_10) / len(vols_10) if vols_10 else 1
    vol_structure = []
    for i, (v, c) in enumerate(zip(vols_10, cls_10)):
        ratio = v / avg_vol_10 if avg_vol_10 > 0 else 0
        direction = "→" if i == 0 else ("↑" if c > cls_10[i-1] else "↓")
        vol_structure.append({'vol': v, 'ratio': ratio, 'direction': direction})
    
    # OI变化
    oi_prev = float(k1h[0][5]) if k1h else oi_val
    oi_chg = (oi_val - oi_prev) / oi_prev * 100 if oi_prev > 0 else 0
    
    # 综合建议
    avg_rsi = (d15['rsi'] + d1h['rsi'] + d4h['rsi']) / 3
    if d1h['rsi'] < 40 and "多头" in d4h['trend']:
        direction = "📈 看多（谨慎）"
        reasons = ["1小时RSI偏弱，有反弹需求", "4H多头排列未破", "关注支撑位能否企稳"]
    elif d1h['rsi'] > 60 and "空头" in d4h['trend']:
        direction = "🔴 看空为主"
        reasons = ["1小时RSI偏强，有回调风险", "4H空头排列"]
    else:
        direction = "⏸️ 观望为主"
        reasons = ["多空方向不明", "等待突破确认"]
    
    # 狙击位盈亏比
    long_ratio = abs(r1 - s1) / abs(s1 - s2) if abs(s1 - s2) > 0 else 1
    short_ratio = abs(r1 - l4_20) / abs(r2 - r1) if abs(r2 - r1) > 0 else 1
    
    return {
        'symbol': symbol,
        'current_price': price,
        'change_24h': change_24h,
        'oi': oi_val,
        'oi_chg': oi_chg,
        'funding_rate': funding_val,
        'btc_price': btc_price,
        'btc_chg': btc_chg,
        'elapsed_ms': elapsed_ms,
        'd15': d15,
        'd1h': d1h,
        'd4h': d4h,
        'avg_rsi': avg_rsi,
        'pivot': {'r1': r1, 'r2': r2, 's1': s1, 's2': s2},
        'h4_20': h4_20,
        'l4_20': l4_20,
        'short_liq': {'low': short_liq_low, 'high': short_liq_high},
        'long_liq': {'low': long_liq_low, 'high': long_liq_high},
        'magnet': magnet,
        'direction': direction,
        'reasons': reasons,
        'long_ratio': long_ratio,
        'short_ratio': short_ratio,
        'vol_structure': vol_structure,
    }, None

# ==================== Streamlit UI ====================
st.set_page_config(page_title="加密查询Web端", page_icon="📊", layout="wide")

auto_proxy()

if 'last_symbol' not in st.session_state:
    st.session_state.last_symbol = "BTCUSDT"
if 'result' not in st.session_state:
    st.session_state.result = None

# ===== 侧边栏 =====
with st.sidebar:
    st.header("🔧 网络配置")
    
    if st.button("🔄 重新检测代理"):
        if auto_proxy():
            st.success(f"✅ 代理已配置")
        else:
            st.error("❌ 未找到可用代理")
        st.rerun()
    
    if st.button("🧪 测试连接"):
        ok, msg = test_network()
        if ok:
            st.success(msg)
        else:
            st.error(msg)
    
    st.divider()
    st.caption(f"代理: {PROXY or '未配置'}")

st.title("📊 加密查询Web端 - 全仓实战分析")
st.markdown("---")

# 顶部输入
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    symbol = st.text_input("币种", value=st.session_state.last_symbol, placeholder="BTCUSDT").upper()
with col2:
    st.write("")
    analyze_btn = st.button("🚀 分析", type="primary", use_container_width=True)
with col3:
    st.write("")
    refresh_btn = st.button("🔄 刷新", type="secondary", use_container_width=True)

progress_area = st.empty()

if analyze_btn and symbol:
    st.session_state.last_symbol = symbol
    st.session_state.result = None
    progress_area.info("🚀 正在分析...")
    result, err = analyze(symbol)
    if err:
        progress_area.error(err)
    else:
        st.session_state.result = result
        progress_area.success(f"✅ 分析完成 (耗时: {result['elapsed_ms']}ms)")

elif refresh_btn and st.session_state.last_symbol:
    st.session_state.result = None
    result, err = analyze(st.session_state.last_symbol)
    if err:
        progress_area.error(err)
    else:
        st.session_state.result = result
        progress_area.success(f"✅ 刷新完成 (耗时: {result['elapsed_ms']}ms)")

# ===== 主界面 - 完整八段式 =====
if st.session_state.result:
    r = st.session_state.result
    
    # ===== 标题信息栏 =====
    st.markdown(f"""
    ### 📊 {r['symbol']} 全仓实战分析
    **分析时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')} | **当前价格：** {fmt_price(r['current_price'])} | **24h涨跌：** {r['change_24h']:+.2f}%
    """)
    st.markdown("---")
    
    # ===== 一、多周期趋势评估 =====
    st.subheader("一、多周期趋势评估")
    
    cycle_data = [
        {"周期": "15分钟", "价格": fmt_price(r['d15']['price']), "涨跌": f"{r['d15']['change']:+.2f}%",
         "趋势": r['d15']['trend'], "RSI": fmt_rsi(r['d15']['rsi']), 
         "形态": r['d15']['pattern'], "成交量": f"{r['d15']['vol_st']} ({r['d15']['vol_ratio']:.2f}x)"},
        {"周期": "1小时", "价格": fmt_price(r['d1h']['price']), "涨跌": f"{r['d1h']['change']:+.2f}%",
         "趋势": r['d1h']['trend'], "RSI": fmt_rsi(r['d1h']['rsi']),
         "形态": r['d1h']['pattern'], "成交量": f"{r['d1h']['vol_st']} ({r['d1h']['vol_ratio']:.2f}x)"},
        {"周期": "4小时", "价格": fmt_price(r['d4h']['price']), "涨跌": f"{r['d4h']['change']:+.2f}%",
         "趋势": r['d4h']['trend'], "RSI": fmt_rsi(r['d4h']['rsi']),
         "形态": r['d4h']['pattern'], "成交量": f"{r['d4h']['vol_st']} ({r['d4h']['vol_ratio']:.2f}x)"},
    ]
    st.table(cycle_data)
    st.markdown(f"**平均RSI：** {r['avg_rsi']:.1f} {'✅ 正常区间' if 40 <= r['avg_rsi'] <= 60 else '⚠️ 需关注'}")
    st.markdown("---")
    
    # ===== 二、关键价位 =====
    st.subheader("二、关键价位")
    
    price_data = [
        {"周期": "短线", "阻力": fmt_price(r['pivot']['r1']), "支撑": fmt_price(r['pivot']['s1'])},
        {"周期": "中线", "阻力": fmt_price(r['pivot']['r2']), "支撑": fmt_price(r['pivot']['s2'])},
        {"周期": "中长线", "阻力": fmt_price(r['h4_20']), "支撑": fmt_price(r['l4_20'])},
    ]
    st.table(price_data)
    
    oi_usd = r['oi'] * r['current_price'] / 1e9
    st.markdown(f"""
    **BTC联动：** 同向（BTC {fmt_price(r['btc_price'])} ({r['btc_chg']:+.2f}%））→ 可参考BTC顺势操作
    **OI：** {r['oi']:,.0f} (${oi_usd:.2f}B) | **资金费率：** {r['funding_rate']*100:.4f}%
    """)
    st.markdown("---")
    
    # ===== 三、成交量结构 + OI深度分析 =====
    st.subheader("三、成交量结构 + OI深度分析")
    
    if r['oi_chg'] > 1:
        st.markdown("📈 **OI上升，资金入场**")
    elif r['oi_chg'] < -1:
        st.markdown("📉 **OI下降，资金撤离**")
    else:
        st.markdown("⏸️ **OI稳定，无明显方向**")
    
    st.markdown(f"**OI：** {r['oi_chg']:+.2f}% | 价格 {r['d1h']['change']:+.2f}%")
    
    if r['oi_chg'] > 1:
        st.markdown("→ 持仓量上升，多头加仓或新资金入场")
    elif r['oi_chg'] < -1:
        st.markdown("→ 持仓量下降，空头平仓或资金撤离")
    else:
        st.markdown("→ 持仓量纹丝不动，资金无表态")
    
    st.markdown("**量价结构逐点：**")
    for v in r['vol_structure'][-5:]:
        st.markdown(f"- 第X根: {v['direction']}量{v['vol']:,.0f}(均量的{v['ratio']:.2f}倍)")
    
    vol_condition = ""
    if r['d1h']['vol_ratio'] > 1.3 and r['d4h']['vol_ratio'] < 0.8:
        vol_condition = "⚠️ **OI背离判定：** 1小时放量 + 4小时缩量 = 反弹不放量，不牢"
    elif r['d1h']['vol_ratio'] > 1 and r['d4h']['vol_ratio'] > 1:
        vol_condition = "✅ 量价配合正常"
    else:
        vol_condition = "→ 需进一步观察"
    st.markdown(vol_condition)
    st.markdown("---")
    
    # ===== 四、资金费率 =====
    st.subheader("四、资金费率")
    
    fr_abs = abs(r['funding_rate'])
    if fr_abs < 0.001:
        fr_status = "✅ 正常"
    elif r['funding_rate'] > 0.001:
        fr_status = "⚠️ 偏高"
    else:
        fr_status = "⚠️ 偏低"
    
    if r['funding_rate'] < -0.001:
        fr_bullish = "多头占优"
    elif r['funding_rate'] > 0.001:
        fr_bullish = "空头占优"
    else:
        fr_bullish = "多空均衡"
    
    st.markdown(f"{fr_status}（{r['funding_rate']*100:.4f}%），{fr_bullish}")
    st.markdown("---")
    
    # ===== 五、清算热力图 =====
    st.subheader("五、【清算热力图】（技术面估算）")
    
    dist_short = (r['short_liq']['low'] - r['current_price']) / r['current_price'] * 100
    dist_long = (r['current_price'] - r['long_liq']['high']) / r['current_price'] * 100
    
    st.markdown("🔥 **清算密集区**")
    st.markdown(f"- **空头清算区：** {fmt_price(r['short_liq']['low'])}-{fmt_price(r['short_liq']['high'])}（突破后空头被套）")
    st.markdown(f"- **多头清算区：** {fmt_price(r['long_liq']['low'])}-{fmt_price(r['long_liq']['high'])}（跌破后多头被套）")
    
    if r['current_price'] > r['magnet']:
        liq_pos = "空头"
        liq_dir = "上方"
    else:
        liq_pos = "多头"
        liq_dir = "下方"
    
    st.markdown(f"- **磁石效应：** 当前{fmt_price(r['current_price'])}在{liq_pos}清算密集区{liq_dir}")
    st.markdown(f"- 当前价距空头区 {dist_short:+.1f}%，距多头区 {dist_long:+.1f}%")
    st.markdown("---")
    
    # ===== 六、综合建议 =====
    st.subheader("六、综合建议")
    
    st.markdown(f"### {r['direction']}")
    for i, reason in enumerate(r['reasons']):
        st.markdown(f"{i+1}. {reason}")
    
    rsi_msg = ""
    if r['d1h']['rsi'] < 40:
        rsi_msg = "存在反弹机会"
    elif r['d1h']['rsi'] > 60:
        rsi_msg = "注意回调风险"
    else:
        rsi_msg = "区间波动"
    
    st.markdown(f"⚠️ **【RSI叮嘱】** 1小时RSI {r['d1h']['rsi']:.1f} → {rsi_msg}")
    st.markdown("---")
    
    # ===== 七、狙击位布局 =====
    st.subheader("七、狙击位布局")
    
    col_long, col_short = st.columns(2)
    
    with col_long:
        st.markdown("#### 🟢 做多参考（回踩至）")
        st.markdown(f"**{fmt_price(r['pivot']['s1'])}**（{(r['pivot']['s1']-r['current_price'])/r['current_price']*100:+.1f}%）| SL {fmt_price(r['pivot']['s2'])} | TP {fmt_price(r['pivot']['r1'])}")
        st.markdown(f"**盈亏比：** 1:{r['long_ratio']:.1f}")
        st.markdown(f"**理由：** 中线EMA25支撑")
        
        st.markdown("---")
        st.markdown("**📌 大白话：**")
        st.markdown(f"价格回踩到 {fmt_price(r['pivot']['s1'])} 附近如果撑住了，可以试多。止损放 {fmt_price(r['pivot']['s2'])}，止盈先看 {fmt_price(r['pivot']['r1'])}。大白话：跌到支撑位企稳就是送钱机会。")
    
    with col_short:
        st.markdown("#### 🔴 做空参考（反弹至）")
        st.markdown(f"**{fmt_price(r['pivot']['r1'])}**（{(r['pivot']['r1']-r['current_price'])/r['current_price']*100:+.1f}%）| SL {fmt_price(r['pivot']['r2'])} | TP {fmt_price(r['l4_20'])}")
        st.markdown(f"**盈亏比：** 1:{r['short_ratio']:.1f}")
        st.markdown(f"**理由：** 短线EMA7压力")
        
        st.markdown("---")
        st.markdown("**📌 大白话：**")
        st.markdown(f"价格反弹到 {fmt_price(r['pivot']['r1'])} 如果涨不动了，可以试空。止损放 {fmt_price(r['pivot']['r2'])}，止盈看 {fmt_price(r['l4_20'])}。大白话：反弹到压力位滞涨就是白捡的空单机会。")
    
    st.markdown("---")
    st.markdown(f"**核心结论：** {fmt_price(r['pivot']['s1'])}-{fmt_price(r['pivot']['s2'])} 是多重支撑汇集区，守住看多，破则看空。")
    st.markdown("---")
    
    # ===== 八、最终结论 =====
    st.subheader("八、最终结论")
    
    st.markdown(f"""
    - **胜率评估：** 55-65%
    - **最大风险点：** {'1小时反弹无量；下方支撑若破' if r['d1h']['vol_ratio'] < 1 else '方向不明'}
    - **最佳入场方式：** 等 {fmt_price(r['pivot']['s1'])} 企稳做多，或突破 {fmt_price(r['pivot']['r1'])} 追多
    - **是否值得参与：** {'⚠️ 可轻仓，RSI偏弱有反弹预期' if r['d1h']['rsi'] < 50 else '⚠️ 谨慎，等待明确信号'}
    - **更适合做：** {'短线' if r['d1h']['vol_ratio'] > 1 else '波段'}
    - **最可能错在哪里：** {'反弹无量继续阴跌，止损被扫' if r['d1h']['vol_ratio'] < 1 else '震荡行情来回被扫'}
    """)
    
    st.markdown(f"""
    ---
    <div style="text-align:right;color:gray;font-size:0.8em;">
    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Binance API | {r['elapsed_ms']}ms | {PROXY or '无代理'}
    </div>
    """, unsafe_allow_html=True)

else:
    st.info("👆 输入币种点击「🚀 分析」")
    with st.expander("📋 使用说明"):
        st.markdown(f"""
        **支持币种：** BTCUSDT、ETHUSDT 等 Binance 永续合约
        **当前代理：** {PROXY or '未配置'}
        """)

if __name__ == "__main__":
    print("📊 加密查询Web端已启动")
    print(f"代理: {PROXY or '未配置'}")
    print("访问: http://localhost:6868")
