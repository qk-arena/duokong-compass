#!/usr/bin/env python3
"""多空罗盘历史回测：用与线上完全相同的引擎（tools/engine.py 的 analyze，
39 个因子、同样的动量/趋势/综合判定、同样的已收盘口径）在历史 K 线上逐根回放。

结算口径（写死）：信号在第 i 根已收盘 K 线生成（call_dir 偏多/偏空才计入，
中性不计），以第 i+1 根收盘价 vs 第 i 根收盘价定对错：偏多且涨幅>0 命中，
偏空且涨幅<0 命中，其余（含涨幅=0）未命中；涨跌幅一并记录。
4h/日/周/月各自独立统计。命中率 = 命中 / (命中+未命中)，按 同币种+同周期+
同方向 分组；样本 <30 前端只显示「样本不足」。

数据：Gate 优先（分页拉长历史），Binance Vision 兜底/补全，与线上一致。
输出 data/backtest.json（随站发布）+ data/backtest_btc_1d_signals.json
（BTC 日线逐条信号明细，供人工复核）。
可复跑：python3 tools/backtest.py
"""
import json, os, sys, time, urllib.request, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

WARMUP = {"4h": 300, "1d": 300, "1w": 200, "1M": 40}
WARMUP_STOCK = {"4h": 300, "1d": 60}


def gate_paged(symbol, interval, pages):
    """Gate 分页向后拉长历史（每页 1000 根）。"""
    rows = engine.fetch_gate(symbol, interval, 1000)
    got = list(rows)
    for _ in range(pages - 1):
        if not got:
            break
        to = got[0]["t"] - 1
        url = (f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={symbol}_USDT"
               f"&interval={interval}&limit=1000&to={to}")
        older = None
        for _try in range(2):
            try:
                with urllib.request.urlopen(url, timeout=45) as r:
                    older = json.load(r)
                break
            except Exception:
                older = None
        if not older:
            break
        orows = [{"t": int(c[0]), "o": float(c[5]), "h": float(c[3]), "l": float(c[4]),
                  "c": float(c[2]), "v": float(c[6]),
                  "finished": str(c[7]).lower() == "true"} for c in older]
        got = orows + got
        time.sleep(0.3)
    closed = [r for r in got if r["finished"]]
    closed.sort(key=lambda x: x["t"])
    return closed


def binance_paged(symbol_pair, interval, total):
    """Binance Vision 分页向后拉长历史。symbol_pair 如 BTCUSDT / NVDABUSDT。"""
    out = []
    end = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    span = {"4h": 14400, "1d": 86400}[interval]
    while len(out) < total:
        url = (f"https://data-api.binance.vision/api/v3/klines?symbol={symbol_pair}"
               f"&interval={interval}&limit=1000&endTime={end}")
        with urllib.request.urlopen(url, timeout=45) as r:
            data = json.load(r)
        if not data:
            break
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        batch = []
        for c in data:
            t = int(c[0]) // 1000
            if t + span <= now:
                batch.append({"t": t, "o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
                              "c": float(c[4]), "v": float(c[5]), "finished": True})
        if not batch:
            break
        out = batch + out
        end = batch[0]["t"] * 1000 - 1
        time.sleep(0.3)
    out.sort(key=lambda x: x["t"])
    return out[-total:]


def get_4h(symbol, is_stock):
    if is_stock:
        return binance_paged(symbol + "BUSDT", "4h", 1100)
    try:
        rows = gate_paged(symbol, "4h", 3)
        if len(rows) >= 2000:
            return rows
    except Exception:
        pass
    return binance_paged(symbol + "USDT", "4h", 2400)


def replay(candles, warmup, keep_detail=False):
    """逐根回放。返回 (stats, detail)：stats[dir] = {n, hits}。"""
    stats = {"偏多": {"n": 0, "hits": 0}, "偏空": {"n": 0, "hits": 0}}
    detail = []
    for i in range(warmup, len(candles) - 1):
        a = engine.analyze(candles[:i + 1])
        d = a["call_dir"]
        if d not in ("偏多", "偏空"):
            continue
        entry = candles[i]["c"]
        exitp = candles[i + 1]["c"]
        chg = (exitp / entry - 1) * 100
        hit = (chg > 0) if d == "偏多" else (chg < 0)
        stats[d]["n"] += 1
        if hit:
            stats[d]["hits"] += 1
        if keep_detail:
            detail.append({
                "bar_t": candles[i]["t"],
                "bar_date_utc": dt.datetime.fromtimestamp(candles[i]["t"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "dir": d, "entry": entry, "exit": exitp,
                "change_pct": round(chg, 4), "verdict": "命中" if hit else "未命中",
                "momentum_dir": a["momentum_dir"], "trend_dir": a["trend_dir"],
            })
    return stats, detail


def pack(stats):
    out = {}
    for d, s in stats.items():
        out[d] = {"n": s["n"], "hits": s["hits"],
                  "rate": (round(s["hits"] / s["n"] * 100, 1) if s["n"] else None)}
    return out


def rng(candles):
    if not candles:
        return None
    f = dt.datetime.fromtimestamp(candles[0]["t"], dt.timezone.utc).strftime("%Y-%m-%d")
    l = dt.datetime.fromtimestamp(candles[-1]["t"], dt.timezone.utc).strftime("%Y-%m-%d")
    return {"from": f, "to": l, "bars": len(candles)}


PROGRESS = "/tmp/backtest_progress.json"


def fetch_binance_retry(pair, interval, limit, tries=4):
    last = None
    for i in range(tries):
        try:
            return engine.fetch_binance(pair, interval, limit)
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last


def save(result, complete):
    result["complete"] = complete
    with open(PROGRESS, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    with open(os.path.join(DATA, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


def main():
    result = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "method": "与线上相同引擎逐根回放已收盘 K 线；结算=下一根收盘 vs 发出收盘；中性不计；样本<30 不显示百分比",
        "symbols": {},
    }
    if os.path.exists(PROGRESS):
        try:
            old = json.load(open(PROGRESS, encoding="utf-8"))
            if isinstance(old.get("symbols"), dict):
                result["symbols"] = old["symbols"]
                print(f"resume: {len(result['symbols'])} symbols already done", flush=True)
        except Exception:
            pass
    btc_detail = None
    if os.path.exists(os.path.join(DATA, "backtest_btc_1d_signals.json")) and "BTC" in result["symbols"]:
        btc_detail = json.load(open(os.path.join(DATA, "backtest_btc_1d_signals.json"), encoding="utf-8"))
    for sym in engine.SYMBOLS:
        if sym in result["symbols"]:
            continue
        daily, _ = engine.fetch_daily_long(sym)
        series = {
            "4h": get_4h(sym, False),
            "1d": daily,
            "1w": engine.resample_weekly(daily),
            "1M": engine.resample_monthly(daily),
        }
        entry = {}
        for tf, candles in series.items():
            if len(candles) < WARMUP[tf] + 5:
                continue
            stats, detail = replay(candles, WARMUP[tf], keep_detail=(sym == "BTC" and tf == "1d"))
            entry[tf] = {"range": rng(candles), "rates": pack(stats)}
            if detail:
                btc_detail = detail
        result["symbols"][sym] = entry
        if btc_detail is not None:
            with open(os.path.join(DATA, "backtest_btc_1d_signals.json"), "w", encoding="utf-8") as f:
                json.dump(btc_detail, f, ensure_ascii=False, indent=1)
        save(result, False)
        print(f"crypto {sym} done", flush=True)
    for sym in engine.BSTOCKS:
        if sym in result["symbols"]:
            continue
        daily = fetch_binance_retry(sym + "B", "1d", 1000)
        h4 = None
        for _try in range(3):
            try:
                h4 = get_4h(sym, True)
                break
            except Exception:
                time.sleep(10)
        series = {"4h": h4 or [], "1d": daily}
        entry = {}
        for tf, candles in series.items():
            if len(candles) < WARMUP_STOCK[tf] + 5:
                continue
            stats, _ = replay(candles, WARMUP_STOCK[tf])
            entry[tf] = {"range": rng(candles), "rates": pack(stats)}
        result["symbols"][sym] = entry
        save(result, False)
        print(f"bstock {sym} done", flush=True)
    save(result, True)
    tot = 0
    for sym, tfs in result["symbols"].items():
        for tf, e in tfs.items():
            for d, s in e["rates"].items():
                tot += s["n"]
    print(f"TOTAL_SIGNALS={tot}")


if __name__ == "__main__":
    main()
