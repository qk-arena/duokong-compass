#!/usr/bin/env python3
"""独立核验：用第二套独立代码 + 第二数据源（Binance Vision）重算，
与 engine.py（Gate 数据）逐因子比对。抽验范围：BTC 全周期（4h/日/周/月）
+ ETH、SOL 全周期。结果写 VERIFY_RESULT.json。
独立实现差异：EMA 用首值递推（非 SMA 播种）、RSI 用简单均值版、Aroon 按
公开定义（窗口恰好 n 根、(n-days)/n*100）独立重写。
"""
import json, math, os, sys, urllib.request, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = "https://data-api.binance.vision/api/v3/klines?symbol={s}USDT&interval={i}&limit={n}"

def binance(symbol, interval, limit):
    with urllib.request.urlopen(BIN.format(s=symbol, i=interval, n=limit), timeout=40) as r:
        data = json.load(r)
    span = {"4h": 14400, "1d": 86400, "1w": 604800, "1M": 2592000}[interval]
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    out = []
    for c in data:
        t = int(c[0]) // 1000
        # for 1M the span varies; use exchange closeTime instead
        close_t = int(c[6]) // 1000
        if close_t < now:
            out.append({"t": t, "o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
                        "c": float(c[4]), "v": float(c[5]), "finished": True})
    return out

def ema2(vals, n):
    k = 2 / (n + 1); out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def macd2(closes):
    e12, e26 = ema2(closes, 12), ema2(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema2(dif, 9)
    return dif[-1], dea[-1], 2 * (dif[-1] - dea[-1])

def rsi2(closes, n=14):
    if len(closes) < n + 1: return None
    ds = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    g = sum(max(d, 0) for d in ds[-n:]) / n
    l = sum(max(-d, 0) for d in ds[-n:]) / n
    if g == 0 and l == 0: return 50.0
    if l == 0: return 100.0
    return 100 - 100 / (1 + g / l)

def aroon2(cs, n=25):
    seg = cs[-n:]
    hi = max(x["h"] for x in seg); lo = min(x["l"] for x in seg)
    dhi = (n - 1) - [x["h"] for x in seg].index(hi)
    dlo = (n - 1) - [x["l"] for x in seg].index(lo)
    return (n - dhi) / n * 100, (n - dlo) / n * 100

def main():
    checks = []
    for symbol in ["BTC", "ETH", "SOL"]:
        daily_g, _ = engine.fetch_daily_long(symbol)
        h4_g, _ = engine.fetch(symbol, "4h", 400)
        gate_tf = {"4h": h4_g, "1d": daily_g, "1w": engine.resample_weekly(daily_g), "1M": engine.resample_monthly(daily_g)}
        for tf, bint in [("4h", "4h"), ("1d", "1d"), ("1w", "1w"), ("1M", "1M")]:
            g = gate_tf[tf]
            b = binance(symbol, bint, 1000 if bint in ("1d",) else 400)
            if len(g) < 30 or len(b) < 30:
                checks.append({"symbol": symbol, "tf": tf, "status": "数据不足", "gate_bars": len(g), "binance_bars": len(b)})
                continue
            gc = [c["c"] for c in g]; bc = [c["c"] for c in b]
            price_diff = abs(gc[-1] / bc[-1] - 1) * 100
            gm = engine.macd(gc); bm = macd2(bc)
            gr = engine.rsi(gc); br = rsi2(bc)
            ga = engine.f_aroon(g); ba = aroon2(b)
            # factor vote agreement between engine-on-Gate and engine-on-Binance candles
            gv = {}; bv = {}
            for name, cat, fn in engine.FACTORS:
                try: gv[name] = fn(g)[0]
                except Exception: gv[name] = None
                try: bv[name] = fn(b)[0]
                except Exception: bv[name] = None
            both = [(gv[k], bv[k]) for k in gv if gv[k] is not None and bv[k] is not None]
            agree = sum(1 for x, y in both if x == y)
            checks.append({
                "symbol": symbol, "tf": tf, "status": "已核",
                "gate_bars": len(g), "binance_bars": len(b),
                "last_close_gate": gc[-1], "last_close_binance": bc[-1],
                "price_diff_pct": round(price_diff, 4),
                "macd_gate": {"dif": round(gm["dif"], 2), "dea": round(gm["dea"], 2), "hist": round(gm["hist"], 2)} if gm else None,
                "macd_binance_indep": {"dif": round(bm[0], 2), "dea": round(bm[1], 2), "hist": round(bm[2], 2)},
                "macd_hist_sign_agree": (gm is not None and (gm["hist"] > 0) == (bm[2] > 0)),
                "rsi_gate": round(gr, 2) if gr else None, "rsi_binance_indep": round(br, 2) if br else None,
                "rsi_abs_diff": round(abs(gr - br), 2) if gr and br else None,
                "aroon_gate": ga[1] if ga else None, "aroon_binance_indep": f"Aroon 上 {ba[0]:.0f} / 下 {ba[1]:.0f}",
                "factor_votes_compared": len(both), "factor_votes_agree": agree,
                "factor_vote_agreement_pct": round(agree / len(both) * 100, 1) if both else None,
                "vote_mismatches": [k for k in gv if gv[k] is not None and bv[k] is not None and gv[k] != bv[k]],
            })
            print(symbol, tf, "price_diff%", round(price_diff, 4), "hist_sign_agree", checks[-1]["macd_hist_sign_agree"],
                  "rsi_diff", checks[-1]["rsi_abs_diff"], "vote_agree", f"{agree}/{len(both)}", "mismatch", checks[-1]["vote_mismatches"])
    with open(os.path.join(ROOT, "VERIFY_RESULT.json"), "w", encoding="utf-8") as f:
        json.dump({"verified_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                   "scope": "BTC/ETH/SOL × 4h/日/周/月；Gate（主源） vs Binance Vision（第二源）+ 独立代码重算 MACD/RSI/Aroon",
                   "checks": checks}, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
