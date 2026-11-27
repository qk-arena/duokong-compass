#!/usr/bin/env python3
"""多空罗盘计算引擎：只用已收盘 K 线，动量与趋势分开，无合成概率，无 IC 加权。

数据源：主源 Gate.io 现货公开接口；兜底 Binance Vision（仅在 Gate 失败时，
且兜底数据会在输出里标 source）。周线由日线按周一对齐重采样，月线按
UTC 自然月重采样，只保留已结束的周/月。
"""
import json, math, urllib.request, datetime as dt

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "LTC"]
# 美股币股（Binance bStocks）：交易对 = 代码 + B + USDT（如 NVDABUSDT）。
# 2026-11-27 经 exchangeInfo 核查 9 个目标对全部 TRADING；日线历史自 2026-06 起
# 仅 120-170 根，只够 4h/日线，周线/月线根数不足自动缺席，不硬凑。
BSTOCKS = ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY", "TSLA"]
GATE = "https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={s}_USDT&interval={i}&limit={n}"
BINANCE = "https://data-api.binance.vision/api/v3/klines?symbol={s}USDT&interval={i}&limit={n}"
GATE_TICKER = "https://api.gateio.ws/api/v4/spot/tickers?currency_pair={s}_USDT"
BINANCE_TICKER = "https://data-api.binance.vision/api/v3/ticker/price?symbol={s}USDT"

def fetch_snapshot_price(symbol):
    """生成时刻的现货现价（spot ticker）。
    字段含义：snapshot_price = 本次快照生成那一刻的交易所现价，仅供页面在
    浏览器端实时价拉取失败时兜底展示；它不是任何一根 K 线的收盘价。
    信号计算与台账发出价仍只用已收盘 K 线收盘价（见 analyze/last_close），与此无关。
    主源 Gate ticker，失败换 Binance Vision ticker；都失败返回 (None, "")。"""
    for _try in range(2):  # Gate 偶发超时，ticker 轻量，重试一次
        try:
            with urllib.request.urlopen(GATE_TICKER.format(s=symbol), timeout=15) as r:
                data = json.load(r)
            if data and data[0].get("last"):
                return float(data[0]["last"]), "Gate.io ticker（生成时刻现价）"
        except Exception:
            pass
    for _try in range(2):
        try:
            with urllib.request.urlopen(BINANCE_TICKER.format(s=symbol), timeout=15) as r:
                data = json.load(r)
            if data.get("price"):
                return float(data["price"]), "Binance Vision ticker（生成时刻现价）"
        except Exception:
            pass
    return None, ""

def fetch_gate(symbol, interval, limit):
    url = GATE.format(s=symbol, i=interval, n=limit)
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    out = []
    for c in data:  # [t, quote_vol, close, high, low, open, base_vol, finished]
        out.append({"t": int(c[0]), "o": float(c[5]), "h": float(c[3]),
                    "l": float(c[4]), "c": float(c[2]), "v": float(c[6]),
                    "finished": str(c[7]).lower() == "true"})
    out.sort(key=lambda x: x["t"])
    return out

def fetch_binance(symbol, interval, limit):
    url = BINANCE.format(s=symbol, i=interval, n=limit)
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    span = {"4h": 14400, "1d": 86400}[interval]
    out = []
    for c in data:  # [openTime, open, high, low, close, volume, closeTime, ...]
        t = int(c[0]) // 1000
        if t + span <= now:  # only closed
            out.append({"t": t, "o": float(c[1]), "h": float(c[2]),
                        "l": float(c[3]), "c": float(c[4]), "v": float(c[5]),
                        "finished": True})
    return out

def fetch(symbol, interval, limit):
    try:
        rows = fetch_gate(symbol, interval, limit)
        closed = [r for r in rows if r["finished"]]
        if len(closed) >= 60:
            return closed, "Gate.io"
    except Exception:
        pass
    rows = fetch_binance(symbol, interval, limit)
    return rows, "Binance Vision（兜底）"

def _binance_daily_before(symbol, end_ms, limit=1000):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}USDT&interval=1d&limit={limit}&endTime={end_ms}"
    with urllib.request.urlopen(url, timeout=45) as r:
        data = json.load(r)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    out = []
    for c in data:
        t = int(c[0]) // 1000
        if t + 86400 <= now:
            out.append({"t": t, "o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
                        "c": float(c[4]), "v": float(c[5]), "finished": True})
    return out

def fetch_daily_long(symbol, total=2000):
    """Gate single request caps at 1000 bars; page backwards with `to` for ~2000 daily bars.
    If Gate paging fails/short, fill the older segment from Binance Vision daily klines
    (labelled honestly in the source string)."""
    src = "Gate.io"
    rows = []
    try:
        rows = fetch_gate(symbol, "1d", 1000)
        if rows:
            to = rows[0]["t"] - 1
            url = f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={symbol}_USDT&interval=1d&limit=1000&to={to}"
            older = None
            for _try in range(2):
                try:
                    with urllib.request.urlopen(url, timeout=45) as r:
                        older = json.load(r)
                    break
                except Exception:
                    older = None
            if older:
                orows = [{"t": int(c[0]), "o": float(c[5]), "h": float(c[3]), "l": float(c[4]),
                          "c": float(c[2]), "v": float(c[6]), "finished": str(c[7]).lower() == "true"} for c in older]
                rows = orows + rows
    except Exception:
        rows = rows or []
    closed = [r for r in rows if r["finished"]]
    if len(closed) < 1800:
        try:
            first_t = closed[0]["t"] if closed else int(dt.datetime.now(dt.timezone.utc).timestamp())
            older_b = _binance_daily_before(symbol, first_t * 1000 - 1)
            seen = {r["t"] for r in closed}
            add = [r for r in older_b if r["t"] not in seen]
            if add:
                closed = add + closed
                src = "Gate.io（长历史段由 Binance Vision 补全）"
        except Exception:
            pass
    if len(closed) >= 60:
        closed.sort(key=lambda x: x["t"])
        return closed[-total:], src
    return fetch(symbol, "1d", 1000)

def resample_weekly(daily):
    weeks = {}
    for r in daily:
        d = dt.datetime.fromtimestamp(r["t"], dt.timezone.utc).date()
        monday = d - dt.timedelta(days=d.weekday())
        weeks.setdefault(monday, []).append(r)
    now = dt.datetime.now(dt.timezone.utc).date()
    out = []
    for monday in sorted(weeks):
        if monday + dt.timedelta(days=7) <= now:  # week fully ended
            rows = weeks[monday]
            out.append({"t": int(dt.datetime(monday.year, monday.month, monday.day, tzinfo=dt.timezone.utc).timestamp()),
                        "o": rows[0]["o"], "h": max(x["h"] for x in rows), "l": min(x["l"] for x in rows),
                        "c": rows[-1]["c"], "v": sum(x["v"] for x in rows), "finished": True})
    return out

def resample_monthly(daily):
    months = {}
    for r in daily:
        d = dt.datetime.fromtimestamp(r["t"], dt.timezone.utc).date()
        months.setdefault((d.year, d.month), []).append(r)
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for (y, m) in sorted(months):
        nxt = dt.date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        if nxt <= now.date():
            rows = months[(y, m)]
            out.append({"t": int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp()),
                        "o": rows[0]["o"], "h": max(x["h"] for x in rows), "l": min(x["l"] for x in rows),
                        "c": rows[-1]["c"], "v": sum(x["v"] for x in rows), "finished": True})
    return out

# ---------- indicators (all computed on closed candles only) ----------
def sma(vals, n, off=0):
    seg = vals[:len(vals)-off] if off else vals
    if len(seg) < n: return None
    return sum(seg[-n:]) / n

def ema_series(vals, n):
    if len(vals) < n: return []
    k = 2 / (n + 1)
    out = [sum(vals[:n]) / n]  # SMA seed
    for v in vals[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out  # aligned to vals[n-1:]

def macd(closes):
    if len(closes) < 35: return None
    e12 = ema_series(closes, 12); e26 = ema_series(closes, 26)
    dif = [a - b for a, b in zip(e12[-(len(e26)):], e26)] if len(e12) >= len(e26) else []
    # align: e12 starts at idx11, e26 at idx25 -> dif starts idx25
    e12a = ema_series(closes, 12)[-len(e26):]
    dif = [a - b for a, b in zip(e12a, e26)]
    dea = ema_series(dif, 9)
    if not dea: return None
    hist = [2 * (d - e) for d, e in zip(dif[-len(dea):], dea)]
    return {"dif": dif[-1], "dea": dea[-1], "hist": hist[-1],
            "hist5": hist[-5:], "cross_bars_ago": _cross_bars_ago(dif[-len(dea):], dea)}

def _cross_bars_ago(dif, dea):
    for i in range(len(dif) - 1, 0, -1):
        if (dif[i-1] - dea[i-1]) * (dif[i] - dea[i]) < 0:
            return len(dif) - 1 - i, ("金叉" if dif[i] > dea[i] else "死叉")
    return None, None

def rsi(closes, n=14):
    if len(closes) < n + 1: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0)); losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n; al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0 and ag == 0: return 50.0  # flat series: neutral (old code wrongly returned 100)
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def atr(candles, n=14):
    if len(candles) < n + 1: return None
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        trs.append(max(c["h"] - c["l"], abs(c["h"] - candles[i-1]["c"]), abs(c["l"] - candles[i-1]["c"])))
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a

def stdev(vals, n):
    if len(vals) < n: return None
    seg = vals[-n:]; m = sum(seg) / n
    return math.sqrt(sum((x - m) ** 2 for x in seg) / n)

def returns(closes):
    return [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]

# ---------- factors: each returns (vote -1/0/1 or None, detail str) ----------
def f_macd(cs):
    m = macd([c["c"] for c in cs])
    if not m: return None, ""
    v = 1 if m["hist"] > 0 else (-1 if m["hist"] < 0 else 0)
    return v, f"MACD DIF {m['dif']:.2f} / DEA {m['dea']:.2f} / 柱 {m['hist']:+.2f}"

def f_rsi(cs):
    r = rsi([c["c"] for c in cs])
    if r is None: return None, ""
    return (1 if r > 55 else (-1 if r < 45 else 0)), f"RSI14 {r:.1f}"

def _roc(cs, n):
    closes = [c["c"] for c in cs]
    if len(closes) < n + 20: return None, ""
    roc = closes[-1] / closes[-1-n] - 1
    vol = stdev(returns(closes), 20) or 0
    z = roc / (vol * math.sqrt(n)) if vol > 0 else 0
    return (1 if z > 0.5 else (-1 if z < -0.5 else 0)), f"ROC{n} {roc*100:+.2f}%"

def f_stoch(cs, n=14):
    if len(cs) < n + 3: return None, ""
    ks = []
    for i in range(n - 1, len(cs)):
        seg = cs[i-n+1:i+1]
        hh, ll = max(x["h"] for x in seg), min(x["l"] for x in seg)
        ks.append(100 * (cs[i]["c"] - ll) / (hh - ll) if hh > ll else 50.0)
    k, d = ks[-1], sum(ks[-3:]) / 3
    v = 1 if (k > d and k > 50) else (-1 if (k < d and k < 50) else 0)
    return v, f"随机 %K {k:.0f} / %D {d:.0f}"

def f_cci(cs, n=20):
    if len(cs) < n: return None, ""
    tps = [(c["h"] + c["l"] + c["c"]) / 3 for c in cs]
    seg = tps[-n:]; m = sum(seg) / n
    md = sum(abs(x - m) for x in seg) / n
    if md == 0: return 0, "CCI 0"
    cci = (tps[-1] - m) / (0.015 * md)
    return (1 if cci > 100 else (-1 if cci < -100 else 0)), f"CCI20 {cci:.0f}"

def f_aroon(cs, n=25):
    # FIXED window: exactly the last n candles (old code scanned n+1)
    if len(cs) < n: return None, ""
    seg = cs[-n:]
    hi_i = max(range(n), key=lambda i: seg[i]["h"])
    lo_i = min(range(n), key=lambda i: seg[i]["l"])
    # canonical Aroon: ((n - days_since_extreme) / n) * 100, days counted back from last bar
    days_hi = (n - 1) - hi_i; days_lo = (n - 1) - lo_i
    up = (n - days_hi) / n * 100
    down = (n - days_lo) / n * 100
    diff = up - down
    return (1 if diff > 20 else (-1 if diff < -20 else 0)), f"Aroon 上 {up:.0f} / 下 {down:.0f}"

def f_adx(cs, n=14):
    if len(cs) < 2 * n + 1: return None, ""
    trs, pdm, mdm = [], [], []
    for i in range(1, len(cs)):
        up = cs[i]["h"] - cs[i-1]["h"]; dn = cs[i-1]["l"] - cs[i]["l"]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trs.append(max(cs[i]["h"] - cs[i]["l"], abs(cs[i]["h"] - cs[i-1]["c"]), abs(cs[i]["l"] - cs[i-1]["c"])))
    def wilder(x):
        s = sum(x[:n])
        out = [s]
        for v in x[n:]:
            s = s - s / n + v; out.append(s)
        return out
    tr_s, p_s, m_s = wilder(trs), wilder(pdm), wilder(mdm)
    pdi = [100 * p / t if t else 0 for p, t in zip(p_s, tr_s)]
    mdi = [100 * m / t if t else 0 for m, t in zip(m_s, tr_s)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0 for p, m in zip(pdi, mdi)]
    if len(dx) < n: return None, ""
    adx = sum(dx[-n:]) / n
    v = 0
    if adx > 20:
        v = 1 if pdi[-1] > mdi[-1] else -1
    return v, f"ADX {adx:.0f} / +DI {pdi[-1]:.0f} / -DI {mdi[-1]:.0f}"

def f_obv(cs, n=20):
    if len(cs) < n + 1: return None, ""
    obv = [0.0]
    for i in range(1, len(cs)):
        obv.append(obv[-1] + (cs[i]["v"] if cs[i]["c"] > cs[i-1]["c"] else (-cs[i]["v"] if cs[i]["c"] < cs[i-1]["c"] else 0.0)))
    cur, prev = sum(obv[-5:]) / 5, sum(obv[-5-n:-n] if len(obv) >= 5 + n else obv[:5]) / 5
    return (1 if cur > prev else (-1 if cur < prev else 0)), "OBV 20期均值方向"

def _cross_factor(cs, fast, slow, kind="SMA"):
    closes = [c["c"] for c in cs]
    if kind == "SMA":
        f, s = sma(closes, fast), sma(closes, slow)
    else:
        ef, es = ema_series(closes, fast), ema_series(closes, slow)
        f, s = (ef[-1] if ef else None), (es[-1] if es else None)
    if f is None or s is None: return None, ""
    return (1 if f > s else (-1 if f < s else 0)), f"{kind}{fast} {f:.2f} / {kind}{slow} {s:.2f}"

def f_ewmac(cs):
    closes = [c["c"] for c in cs]
    ef, es = ema_series(closes, 16), ema_series(closes, 64)
    if not ef or not es: return None, ""
    diff = ef[-1] - es[-1]
    vol = stdev(returns(closes), 25)
    price_vol = (vol * closes[-1]) if vol else 0
    z = diff / price_vol if price_vol else 0
    return (1 if z > 0.25 else (-1 if z < -0.25 else 0)), f"EWMAC16/64 标准化 {z:+.2f}"

def f_donchian(cs, n=20):
    if len(cs) < n + 1: return None, ""
    seg = cs[-n-1:-1]
    hh, ll = max(x["h"] for x in seg), min(x["l"] for x in seg)
    mid = (hh + ll) / 2; c = cs[-1]["c"]
    return (1 if c > mid else (-1 if c < mid else 0)), f"唐奇安20 中轨 {mid:.2f}"

def f_supertrend(cs, n=10, mult=3.0):
    a = atr(cs, n)
    if a is None: return None, ""
    c = cs[-1]
    mid = (c["h"] + c["l"]) / 2
    # simplified last-bar supertrend vs previous close direction using ATR bands trend state
    closes = [x["c"] for x in cs]
    up_band = mid - mult * a; dn_band = mid + mult * a
    v = 1 if closes[-1] > dn_band else (-1 if closes[-1] < up_band else (1 if closes[-1] >= closes[-2] else -1))
    return v, f"Supertrend ATR带 {up_band:.2f}~{dn_band:.2f}"

def f_psar(cs, af_step=0.02, af_max=0.2):
    if len(cs) < 10: return None, ""
    # compact PSAR over the series
    bull = cs[1]["c"] >= cs[0]["c"]
    sar = cs[0]["l"] if bull else cs[0]["h"]
    ep = cs[0]["h"] if bull else cs[0]["l"]
    af = af_step
    for i in range(1, len(cs)):
        sar = sar + af * (ep - sar)
        if bull:
            sar = min(sar, cs[i-1]["l"], cs[i-2]["l"] if i >= 2 else cs[i-1]["l"])
            if cs[i]["l"] < sar:
                bull = False; sar = ep; ep = cs[i]["l"]; af = af_step; continue
            if cs[i]["h"] > ep: ep = cs[i]["h"]; af = min(af + af_step, af_max)
        else:
            sar = max(sar, cs[i-1]["h"], cs[i-2]["h"] if i >= 2 else cs[i-1]["h"])
            if cs[i]["h"] > sar:
                bull = True; sar = ep; ep = cs[i]["h"]; af = af_step; continue
            if cs[i]["l"] < ep: ep = cs[i]["l"]; af = min(af + af_step, af_max)
    return (1 if bull else -1), f"PSAR {'多头侧' if bull else '空头侧'} {sar:.2f}"

def f_ichimoku(cs):
    if len(cs) < 52: return None, ""
    def hl(seg): return (max(x["h"] for x in seg) + min(x["l"] for x in seg)) / 2
    tenkan = hl(cs[-9:]); kijun = hl(cs[-26:])
    span_a = (tenkan + kijun) / 2
    span_b = hl(cs[-52:])
    c = cs[-1]["c"]
    top, bot = max(span_a, span_b), min(span_a, span_b)
    v = 1 if c > top else (-1 if c < bot else 0)
    return v, f"一目 云顶 {top:.2f} / 云底 {bot:.2f}"

def f_linreg(cs, n=50):
    closes = [c["c"] for c in cs]
    if len(closes) < n: return None, ""
    seg = closes[-n:]; m = sum(seg) / n
    num = sum((i - (n - 1) / 2) * (seg[i] - m) for i in range(n))
    den = sum((i - (n - 1) / 2) ** 2 for i in range(n))
    slope = num / den
    vol = stdev(returns(closes), 20) or 0
    z = slope * n / (vol * closes[-1]) if vol else 0
    return (1 if z > 0.5 else (-1 if z < -0.5 else 0)), f"线性回归50 标准化斜率 {z:+.2f}"

def f_price_vs_sma(cs, n):
    closes = [c["c"] for c in cs]
    s = sma(closes, n)
    if s is None: return None, ""
    return (1 if closes[-1] > s else (-1 if closes[-1] < s else 0)), f"价 / SMA{n} {s:.2f}"

def f_tsmom(cs, n=120):
    closes = [c["c"] for c in cs]
    if len(closes) < n + 20: return None, ""
    r = closes[-1] / closes[-1-n] - 1
    vol = stdev(returns(closes), 20) or 0
    z = r / (vol * math.sqrt(n)) if vol else 0
    return (1 if z > 0.5 else (-1 if z < -0.5 else 0)), f"TSMOM{n} {r*100:+.1f}%"

def f_boll_mid(cs, n=20):
    closes = [c["c"] for c in cs]
    s = sma(closes, n)
    if s is None: return None, ""
    return (1 if closes[-1] > s else (-1 if closes[-1] < s else 0)), f"布林中轨 {s:.2f}"

# ---------- revived factors (2026-11-27 second audit round) ----------
# 旧看板 57 因子首轮被「高度重复」一刀切掉的独立指标，本轮按权威定义重新实现，
# 投票阈值见 FACTOR_AUDIT.md，经 tools/verify2.py 两套独立实现 + 两家数据源交叉验证。

def _wma_series(vals, n):
    out = [None] * len(vals)
    w = list(range(1, n + 1)); den = sum(w)
    for i in range(n - 1, len(vals)):
        out[i] = sum(a * b for a, b in zip(vals[i - n + 1:i + 1], w)) / den
    return out

def f_hull(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 70: return None, ""
    wh = _wma_series(closes, 27); wf = _wma_series(closes, 55)
    raw = [2 * a - b for a, b in zip(wh, wf) if a is not None and b is not None]
    hma = [x for x in _wma_series(raw, 7) if x is not None]
    a = atr(cs)
    if len(hma) < 4 or not a: return None, ""
    slope = (hma[-1] - hma[-4]) / a
    return (1 if slope > 0.05 else (-1 if slope < -0.05 else 0)), f"HMA55 3根斜率 {slope:.2f} ATR"

def f_kama(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 60: return None, ""
    kama = closes[10]
    for i in range(11, len(closes)):
        change = abs(closes[i] - closes[i - 10])
        vol = sum(abs(closes[j] - closes[j - 1]) for j in range(i - 9, i + 1))
        er = change / vol if vol > 0 else 0
        sc = (er * (2 / 3 - 2 / 31) + 2 / 31) ** 2
        kama += sc * (closes[i] - kama)
    a = atr(cs)
    if not a: return None, ""
    gap = (closes[-1] - kama) / a
    return (1 if gap > 0.25 else (-1 if gap < -0.25 else 0)), f"收盘距 KAMA30 {gap:.2f} ATR"

def f_vortex(cs, n=14):
    if len(cs) < n + 2: return None, ""
    seg = cs[-(n + 1):]
    vp = sum(abs(seg[i]["h"] - seg[i - 1]["l"]) for i in range(1, len(seg)))
    vm = sum(abs(seg[i]["l"] - seg[i - 1]["h"]) for i in range(1, len(seg)))
    tr = sum(max(seg[i]["h"] - seg[i]["l"], abs(seg[i]["h"] - seg[i - 1]["c"]),
                 abs(seg[i]["l"] - seg[i - 1]["c"])) for i in range(1, len(seg)))
    if tr <= 0: return None, ""
    vip, vim = vp / tr, vm / tr
    return (1 if vip > vim else (-1 if vip < vim else 0)), f"VI+ {vip:.2f} / VI- {vim:.2f}"

def f_kst(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 130: return None, ""
    def roc(n):
        return [None] * n + [(closes[i] / closes[i - n] - 1) * 100 for i in range(n, len(closes))]
    def sma_of(vals, n):
        out = [None] * len(vals)
        for i in range(n - 1, len(vals)):
            seg = vals[i - n + 1:i + 1]
            if all(v is not None for v in seg): out[i] = sum(seg) / n
        return out
    r1 = sma_of(roc(10), 10); r2 = sma_of(roc(15), 10)
    r3 = sma_of(roc(20), 10); r4 = sma_of(roc(30), 15)
    kst = [None] * len(closes)
    for i in range(len(closes)):
        if None not in (r1[i], r2[i], r3[i], r4[i]):
            kst[i] = r1[i] + 2 * r2[i] + 3 * r3[i] + 4 * r4[i]
    sig = sma_of(kst, 9)
    if kst[-1] is None or sig[-1] is None: return None, ""
    return (1 if kst[-1] > sig[-1] else (-1 if kst[-1] < sig[-1] else 0)), f"KST {kst[-1]:.2f} / 信号 {sig[-1]:.2f}"

def f_dist_high(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 120: return None, ""
    win = 250 if len(closes) >= 260 else 120
    hh = max(x["h"] for x in cs[-win:])
    if hh <= 0: return None, ""
    dd = (hh - closes[-1]) / hh * 100
    return (1 if dd <= 6 else (-1 if dd >= 15 else 0)), f"距 {win} 根新高回撤 {dd:.1f}%"

def _last20_stats(closes):
    seg = closes[-20:]; m = sum(seg) / 20
    sd = math.sqrt(sum((x - m) ** 2 for x in seg) / 20)
    return m, sd

def f_pctb_rev(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 25: return None, ""
    m, sd = _last20_stats(closes)
    if sd <= 0: return None, ""
    pb = (closes[-1] - (m - 2 * sd)) / (4 * sd)
    return (-1 if pb >= 0.9 else (1 if pb <= 0.1 else 0)), f"%B {pb:.2f}（反向）"

def f_zscore_rev(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 25: return None, ""
    m, sd = _last20_stats(closes)
    if sd <= 0: return None, ""
    z = (closes[-1] - m) / sd
    return (-1 if z >= 2 else (1 if z <= -2 else 0)), f"Z {z:.2f}（反向）"

def f_rsi_rev(cs):
    r = rsi([c["c"] for c in cs])
    if r is None: return None, ""
    return (-1 if r >= 70 else (1 if r <= 30 else 0)), f"RSI {r:.0f} 极端反转读法"

def f_keltner(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 40: return None, ""
    mid = ema_series(closes, 20)[-1]
    a = atr(cs, 10)
    if mid is None or not a: return None, ""
    up, lo = mid + 2 * a, mid - 2 * a
    pos = "上轨外" if closes[-1] > up else ("下轨外" if closes[-1] < lo else "带内")
    return (1 if closes[-1] > up else (-1 if closes[-1] < lo else 0)), f"收盘 Keltner {pos}"

def f_skew_rev(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 70: return None, ""
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 60, len(closes))]
    m = sum(rets) / len(rets)
    m2 = sum((r - m) ** 2 for r in rets) / len(rets)
    m3 = sum((r - m) ** 3 for r in rets) / len(rets)
    if m2 <= 0: return None, ""
    sk = m3 / (m2 ** 1.5)
    return (-1 if sk > 0.5 else (1 if sk < -0.5 else 0)), f"60根收益偏度 {sk:.2f}（反向）"

def f_downside(cs):
    closes = [c["c"] for c in cs]
    if len(closes) < 50: return None, ""
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 40, len(closes))]
    tot = sum(r * r for r in rets)
    if tot <= 0: return None, ""
    share = sum(r * r for r in rets if r < 0) / tot * 100
    return (-1 if share > 55 else (1 if share < 45 else 0)), f"下行波动占比 {share:.0f}%"

def f_pvcorr(cs):
    if len(cs) < 30: return None, ""
    seg = cs[-21:]
    dp = [math.log(seg[i]["c"] / seg[i - 1]["c"]) for i in range(1, len(seg))]
    dv = [math.log(seg[i]["v"] / seg[i - 1]["v"]) if seg[i]["v"] > 0 and seg[i - 1]["v"] > 0 else 0.0
          for i in range(1, len(seg))]
    ma, mb = sum(dp) / len(dp), sum(dv) / len(dv)
    cov = sum((a - ma) * (b - mb) for a, b in zip(dp, dv))
    va = math.sqrt(sum((a - ma) ** 2 for a in dp)); vb = math.sqrt(sum((b - mb) ** 2 for b in dv))
    if va <= 0 or vb <= 0: return None, ""
    corr = cov / (va * vb)
    return (1 if corr > 0.3 else (-1 if corr < -0.3 else 0)), f"价量相关 {corr:.2f}"

def f_vwap_pos(cs):
    if len(cs) < 30: return None, ""
    seg = cs[-20:]
    tv = sum(x["v"] for x in seg)
    if tv <= 0: return None, ""
    vwap = sum(((x["h"] + x["l"] + x["c"]) / 3) * x["v"] for x in seg) / tv
    a = atr(cs)
    if not a: return None, ""
    gap = (cs[-1]["c"] - vwap) / a
    return (1 if gap > 0.5 else (-1 if gap < -0.5 else 0)), f"收盘距 VWAP20 {gap:.2f} ATR"

def _mfv(x):
    rng = x["h"] - x["l"]
    if rng <= 0: return 0.0
    return ((x["c"] - x["l"]) - (x["h"] - x["c"])) / rng * x["v"]

def f_cmf(cs):
    if len(cs) < 30: return None, ""
    seg = cs[-20:]
    den = sum(x["v"] for x in seg)
    if den <= 0: return None, ""
    cmf = sum(_mfv(x) for x in seg) / den
    return (1 if cmf > 0.05 else (-1 if cmf < -0.05 else 0)), f"CMF {cmf:.3f}"

def f_mfi(cs):
    if len(cs) < 30: return None, ""
    seg = cs[-15:]
    pos = neg = 0.0
    for i in range(1, len(seg)):
        tp_p = (seg[i - 1]["h"] + seg[i - 1]["l"] + seg[i - 1]["c"]) / 3
        tp = (seg[i]["h"] + seg[i]["l"] + seg[i]["c"]) / 3
        flow = tp * seg[i]["v"]
        if tp > tp_p: pos += flow
        elif tp < tp_p: neg += flow
    mfi = 100.0 if neg <= 0 and pos > 0 else (50.0 if neg <= 0 else 100 - 100 / (1 + pos / neg))
    return (1 if mfi > 60 else (-1 if mfi < 40 else 0)), f"MFI {mfi:.0f}"

def f_ad_slope(cs):
    if len(cs) < 45: return None, ""
    ad = 0.0; series = []
    for x in cs:
        ad += _mfv(x); series.append(ad)
    mean_v = sum(x["v"] for x in cs[-20:]) / 20
    if mean_v <= 0: return None, ""
    slope = (series[-1] - series[-21]) / (20 * mean_v)
    return (1 if slope > 0.1 else (-1 if slope < -0.1 else 0)), f"A/D 20根归一斜率 {slope:.2f}"

def f_vol_break(cs):
    if len(cs) < 45: return None, ""
    prior = cs[-21:-1]
    hh = max(x["h"] for x in prior); ll = min(x["l"] for x in prior)
    mean_v = sum(x["v"] for x in prior) / len(prior)
    last = cs[-1]
    ratio = last["v"] / mean_v if mean_v > 0 else 0
    if last["c"] > hh: return (1 if ratio > 1 else 0), f"创20根新高，量比 {ratio:.2f}"
    if last["c"] < ll: return (-1 if ratio > 1 else 0), f"创20根新低，量比 {ratio:.2f}"
    return 0, f"未突破，量比 {ratio:.2f}"

FACTORS = [
    # name, category, func
    ("MACD", "momentum", f_macd),
    ("RSI", "momentum", f_rsi),
    ("ROC10", "momentum", lambda cs: _roc(cs, 10)),
    ("ROC60", "momentum", lambda cs: _roc(cs, 60)),
    ("随机指标", "momentum", f_stoch),
    ("CCI", "momentum", f_cci),
    ("Aroon", "momentum", f_aroon),
    ("ADX/DMI", "momentum", f_adx),
    ("OBV量能", "momentum", f_obv),
    ("SMA20/50", "trend", lambda cs: _cross_factor(cs, 20, 50, "SMA")),
    ("SMA50/200", "trend", lambda cs: _cross_factor(cs, 50, 200, "SMA")),
    ("EMA12/26", "trend", lambda cs: _cross_factor(cs, 12, 26, "EMA")),
    ("EWMAC16/64", "trend", f_ewmac),
    ("唐奇安20", "trend", f_donchian),
    ("Supertrend", "trend", f_supertrend),
    ("PSAR", "trend", f_psar),
    ("一目均衡", "trend", f_ichimoku),
    ("线性回归50", "trend", f_linreg),
    ("价vsSMA50", "trend", lambda cs: f_price_vs_sma(cs, 50)),
    ("价vsSMA200", "trend", lambda cs: f_price_vs_sma(cs, 200)),
    ("TSMOM120", "trend", f_tsmom),
    ("布林中轨", "trend", f_boll_mid),
    # --- revived 2026-11-27 (see FACTOR_AUDIT.md round 2) ---
    ("KST", "momentum", f_kst),
    ("距新高", "momentum", f_dist_high),
    ("布林%B反向", "momentum", f_pctb_rev),
    ("Z分数反向", "momentum", f_zscore_rev),
    ("RSI反转", "momentum", f_rsi_rev),
    ("收益偏度反向", "momentum", f_skew_rev),
    ("下行波动占比", "momentum", f_downside),
    ("价量相关20", "momentum", f_pvcorr),
    ("VWAP位置20", "momentum", f_vwap_pos),
    ("Chaikin资金流", "momentum", f_cmf),
    ("MFI", "momentum", f_mfi),
    ("A/D斜率", "momentum", f_ad_slope),
    ("Hull均线55", "trend", f_hull),
    ("KAMA30", "trend", f_kama),
    ("Vortex14", "trend", f_vortex),
    ("Keltner位置", "trend", f_keltner),
    ("放量突破", "trend", f_vol_break),
]

def direction_from_votes(votes):
    valid = [v for v in votes if v is not None]
    if not valid: return "无数据", 0, 0, 0
    pos = sum(1 for v in valid if v > 0); neg = sum(1 for v in valid if v < 0)
    score = sum(valid) / len(valid)
    d = "偏多" if score >= 0.25 else ("偏空" if score <= -0.25 else "中性")
    return d, pos, neg, len(valid)

def analyze(candles):
    closes = [c["c"] for c in candles]
    mom_votes, trend_votes, details = [], [], []
    for name, cat, fn in FACTORS:
        try:
            v, det = fn(candles)
        except Exception:
            v, det = None, ""
        if cat == "momentum": mom_votes.append(v)
        else: trend_votes.append(v)
        if v is not None:
            details.append({"name": name, "cat": cat, "vote": v, "detail": det})
    vote_mom_dir, mp, mn, mv = direction_from_votes(mom_votes)
    tr_dir, tp, tn, tv = direction_from_votes(trend_votes)
    # 动量方向按 MACD 动量结构判定（与趋势分开，定义写死并公开）：
    #  DIF>DEA（金叉状态/柱为正）→ 偏多；DIF<DEA 且柱连续放大向下 → 偏空；
    #  DIF<DEA 但柱连续≥3根收敛且 DIF 上行 → 空头动量衰竭，偏多（修复结构）；
    #  其余 → 中性。MACD 不可用（月线历史不足）时回退动量因子投票。
    mom_dir, mom_basis = vote_mom_dir, "动量因子投票"
    mm = macd(closes)
    if mm:
        h5 = mm["hist5"]
        rising = len(h5) >= 4 and all(h5[i] > h5[i-1] for i in range(1, len(h5)))
        falling = len(h5) >= 4 and all(h5[i] < h5[i-1] for i in range(1, len(h5)))
        if mm["dif"] > mm["dea"]:
            mom_dir, mom_basis = "偏多", f"MACD 金叉状态，柱 {mm['hist']:+.2f}"
        elif falling:
            mom_dir, mom_basis = "偏空", f"MACD 死叉且柱连续放大向下，柱 {mm['hist']:+.2f}"
        elif rising:
            mom_dir, mom_basis = "偏多", f"修复结构：柱连续 {len(h5)} 根收敛（{h5[0]:+.0f}→{h5[-1]:+.0f}），DIF 上行向零轴回归"
        else:
            mom_dir, mom_basis = "中性", f"MACD 柱 {mm['hist']:+.2f}，无连续收敛/放大"
    if mom_dir == tr_dir and mom_dir != "中性": call = mom_dir
    elif mom_dir == "中性" and tr_dir != "中性": call = tr_dir
    elif tr_dir == "中性" and mom_dir != "中性": call = mom_dir
    elif mom_dir == "中性" and tr_dir == "中性": call = "中性"
    else: call = "中性"  # conflict -> observation, no directional call
    m = macd(closes)
    a = atr(candles)
    rets = returns(closes)
    vol20 = stdev(rets, 20)
    peak = max(closes[-120:]) if closes else 0
    dd = (closes[-1] / peak - 1) * 100 if peak else 0
    return {
        "momentum_dir": mom_dir, "momentum_basis": mom_basis, "trend_dir": tr_dir, "call_dir": call,
        "momentum_votes": {"pos": mp, "neg": mn, "valid": mv},
        "trend_votes": {"pos": tp, "neg": tn, "valid": tv},
        "macd": ({"dif": round(m["dif"], 2), "dea": round(m["dea"], 2), "hist": round(m["hist"], 2),
                  "hist5": [round(x, 2) for x in m["hist5"]],
                  "cross_bars_ago": m["cross_bars_ago"][0], "cross_kind": m["cross_bars_ago"][1]} if m else None),
        "sma50": (round(sma(closes, 50), 2) if sma(closes, 50) else None),
        "sma200": (round(sma(closes, 200), 2) if sma(closes, 200) else None),
        "atr_pct": (round(a / closes[-1] * 100, 2) if a else None),
        "vol20_pct": (round(vol20 * 100, 2) if vol20 else None),
        "maxdd120_pct": round(dd, 2),
        "factors": details,
        "last_close": closes[-1],
        "last_candle_t": candles[-1]["t"],
        "bars": len(candles),
    }

def build_symbol(symbol):
    out = {"symbol": symbol, "timeframes": {}}
    daily, dsrc = fetch_daily_long(symbol)
    h4, hsrc = fetch(symbol, "4h", 400)
    weekly = resample_weekly(daily)
    monthly = resample_monthly(daily)
    for tf, candles, src in [("4h", h4, hsrc), ("1d", daily, dsrc), ("1w", weekly, dsrc + " 日线重采样（周一对齐）"), ("1M", monthly, dsrc + " 日线重采样（自然月）")]:
        if len(candles) >= 30:
            a = analyze(candles)
            a["source"] = src
            out["timeframes"][tf] = a
    # 快照价：生成时刻的现货 ticker（见 fetch_snapshot_price 的字段含义）。
    # 旧版这里误把最后一根已收盘日线收盘价当现价输出，行情一动就全线滞后一天，已改掉。
    snap_price, snap_src = fetch_snapshot_price(symbol)
    out["snapshot_price"] = snap_price
    out["snapshot_price_source"] = snap_src
    out["price_source"] = dsrc  # K 线数据来源（长历史口径），非价格来源
    # sparkline：只用已收盘日线收盘价（daily 在 fetch_daily_long/fetch 里已过滤 finished），
    # 取最后 ≤60 根，6 位有效数字足够画走势小图；无数据则空数组，前端整块不渲染。
    out["spark_1d"] = [float(f"{r['c']:.6g}") for r in daily[-60:]] if daily else []
    out["market"] = "crypto"
    out["live_pair"] = symbol + "USDT"
    return out

def build_bstock(symbol):
    """美股币股：只走 Binance Vision 的 bStocks 交易对（代码+B）。
    口径与加密一致（只用已收盘 K 线、动量/趋势分开），但历史短：
    周线约 20 根、月线约 5 根，不足 30 根的周期自动缺席，不硬凑。
    页面统一标注：币股行情，跟踪股价可能有小幅偏离，不冒充交易所股价。"""
    pair = symbol + "B"
    out = {"symbol": symbol, "timeframes": {}}
    daily = fetch_binance(pair, "1d", 1000)
    h4 = fetch_binance(pair, "4h", 400)
    weekly = resample_weekly(daily)
    monthly = resample_monthly(daily)
    src = "Binance 币股（bStocks）"
    for tf, candles in [("4h", h4), ("1d", daily), ("1w", weekly), ("1M", monthly)]:
        if len(candles) >= 30:
            a = analyze(candles)
            a["source"] = src if tf in ("4h", "1d") else src + " 日线重采样"
            out["timeframes"][tf] = a
    snap_price, snap_src = fetch_snapshot_price(pair)
    out["snapshot_price"] = snap_price
    out["snapshot_price_source"] = snap_src
    out["price_source"] = src
    out["spark_1d"] = [float(f"{r['c']:.6g}") for r in daily[-60:]] if daily else []
    out["market"] = "bstock"
    out["live_pair"] = pair + "USDT"
    return out
