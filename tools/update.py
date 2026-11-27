#!/usr/bin/env python3
"""多空罗盘台账更新脚本（可重复运行、幂等）。

每次运行：
1. 从 Gate.io（兜底 Binance Vision）拉已收盘 K 线，重算全部标的×周期信号。
2. 写 data/current.json（页面展示用快照）。
3. 台账 data/ledger.jsonl 只追加：
   - 某标的×周期出现新的已收盘 K 线时，先把该组上一条「进行中」记录结清
     （追加一条 settlement 记录，指向被结清记录 ID，写明命中/未命中与期间涨跌幅），
   - 再追加一条新的 signal 记录（进行中）。
   - 同一根 K 线重复运行不会重复追加（按 candle_t 去重）。
命中率只统计已结清且方向非中性的记录；中性（观察）记录结清只记涨跌幅，不计命中率分母。
"""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import build_symbol, SYMBOLS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LEDGER = os.path.join(DATA, "ledger.jsonl")
TF_LABEL = {"4h": "4小时", "1d": "日线", "1w": "周线", "1M": "月线"}
TF_ORDER = ["4h", "1d", "1w", "1M"]

def bj(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def load_ledger():
    rows = []
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows

def append(rows):
    with open(LEDGER, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def main():
    os.makedirs(DATA, exist_ok=True)
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    symbols = []
    for s in SYMBOLS:
        try:
            symbols.append(build_symbol(s))
        except Exception as e:
            print(f"WARN {s}: {e}")
    snapshot = {"generated_at_utc": utc(now), "generated_at_bj": bj(now),
                "source_primary": "Gate.io 现货公开接口", "source_fallback": "Binance Vision",
                "note": "正式信号只用已收盘 K 线；动量与趋势分开；无合成概率；美股不在 v1 范围",
                "symbols": symbols}
    with open(os.path.join(DATA, "current.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    ledger = load_ledger()
    seq = len(ledger) + 1
    open_recs = {}
    settled_ids = set()
    for r in ledger:
        if r["type"] == "settlement":
            settled_ids.add(r["settles"])
    for r in ledger:
        if r["type"] == "signal" and r["id"] not in settled_ids:
            open_recs[(r["symbol"], r["tf"])] = r
    new_rows = []
    for sym in symbols:
        for tf in TF_ORDER:
            a = sym["timeframes"].get(tf)
            if not a:
                continue
            key = (sym["symbol"], tf)
            open_r = open_recs.get(key)
            if open_r and open_r["candle_t"] == a["last_candle_t"]:
                continue  # same closed candle, idempotent
            if open_r:
                change = (a["last_close"] / open_r["price"] - 1) * 100
                if open_r["call_dir"] == "偏多":
                    verdict = "命中" if change > 0 else ("未命中" if change < 0 else "未命中")
                elif open_r["call_dir"] == "偏空":
                    verdict = "命中" if change < 0 else ("未命中" if change > 0 else "未命中")
                else:
                    verdict = "观察结清"
                new_rows.append({
                    "id": f"L{seq:05d}", "type": "settlement", "settles": open_r["id"],
                    "symbol": sym["symbol"], "tf": tf, "tf_label": TF_LABEL[tf],
                    "settled_at_utc": utc(now), "settled_at_bj": bj(now),
                    "entry_price": open_r["price"], "exit_price": a["last_close"],
                    "change_pct": round(change, 3), "verdict": verdict,
                    "reason": "周期到期（新一根 K 线收盘）" if open_r["call_dir"] == a["call_dir"] else "方向翻转/周期到期",
                })
                seq += 1
            m = a["macd"] or {}
            new_rows.append({
                "id": f"L{seq:05d}", "type": "signal",
                "symbol": sym["symbol"], "tf": tf, "tf_label": TF_LABEL[tf],
                "recorded_at_utc": utc(now), "recorded_at_bj": bj(now),
                "candle_t": a["last_candle_t"],
                "candle_close_utc": utc(a["last_candle_t"]), "candle_close_bj": bj(a["last_candle_t"]),
                "price": a["last_close"], "call_dir": a["call_dir"],
                "momentum_dir": a["momentum_dir"], "trend_dir": a["trend_dir"],
                "momentum_value": f"MACD DIF {m.get('dif')} / DEA {m.get('dea')} / 柱 {m.get('hist')}" if m else "",
                "trend_value": f"SMA50 {a['sma50']} / SMA200 {a['sma200']}",
                "source": a["source"], "status": "进行中",
            })
            seq += 1
    if new_rows:
        append(new_rows)
    ledger = load_ledger()
    with open(os.path.join(DATA, "ledger.json"), "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=1)
    settled = [r for r in ledger if r["type"] == "settlement" and r["verdict"] in ("命中", "未命中")]
    hits = sum(1 for r in settled if r["verdict"] == "命中")
    print(f"symbols={len(symbols)} appended={len(new_rows)} settled_scored={len(settled)} hits={hits}")

if __name__ == "__main__":
    main()
