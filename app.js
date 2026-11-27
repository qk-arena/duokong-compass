const TF_LABEL = {"4h":"4小时","1d":"日线","1w":"周线","1M":"月线"};
const TF_ORDER = ["4h","1d","1w","1M"];
function dirClass(d){ return d==="偏多" ? "up" : (d==="偏空" ? "down" : "accent"); }
function pct(x){ const s = x>0?"+":""; return `<span class="${x>0?"up":(x<0?"down":"muted")}">${s}${x.toFixed(2)}%</span>`; }
function fmtPrice(p){ return p>=100? p.toFixed(2) : (p>=1? p.toFixed(4) : p.toFixed(5)); }

async function load(){
  const cur = await (await fetch("data/current.json")).json();
  const ledger = await (await fetch("data/ledger.json")).json();
  document.getElementById("gen").textContent = `数据生成：${cur.generated_at_bj}（北京时间） / ${cur.generated_at_utc}；主源 ${cur.source_primary}，兜底 ${cur.source_fallback}`;

  // scoreboard from settled ledger records only
  const settlements = ledger.filter(r=>r.type==="settlement");
  const scored = settlements.filter(r=>r.verdict==="命中"||r.verdict==="未命中");
  const hits = scored.filter(r=>r.verdict==="命中").length;
  const open = ledger.filter(r=>r.type==="signal").length - settlements.length;
  document.getElementById("sc-settled").textContent = scored.length;
  const rateEl = document.getElementById("sc-rate");
  if(scored.length>0){
    const rate = hits/scored.length*100;
    rateEl.innerHTML = `<span class="${rate>=50?"up":"down"}">${rate.toFixed(1)}%</span> <span class="muted" style="font-size:14px">（${hits}/${scored.length}）</span>`;
  } else {
    rateEl.innerHTML = `<span class="muted">暂无</span> <span class="muted" style="font-size:14px">（样本 0）</span>`;
  }
  document.getElementById("sc-hits").innerHTML = `<span class="up">${hits} 命中</span> / <span class="down">${scored.length-hits} 未命中</span>`;
  const openEl = document.getElementById("sc-open"); openEl.textContent = Math.max(open,0);

  // symbol cards, two per row
  const host = document.getElementById("symbols");
  host.innerHTML = cur.symbols.map(s=>{
    const cards = TF_ORDER.filter(tf=>s.timeframes[tf]).map(tf=>{
      const a = s.timeframes[tf];
      const m = a.macd;
      const macdLine = m? `MACD DIF ${m.dif} / DEA ${m.dea} / 柱 ${m.hist>0?"+":""}${m.hist}` : "MACD 历史不足";
      const factors = a.factors.map(f=>`<div class="factor">${f.cat==="momentum"?"动量":"趋势"} · ${f.name}：<span class="${f.vote>0?"up":(f.vote<0?"down":"muted")}">${f.vote>0?"多":(f.vote<0?"空":"中")}</span> <span class="muted">${f.detail}</span></div>`).join("");
      return `<div class="card">
        <div class="tf"><span>${TF_LABEL[tf]}</span><span>${a.bars} 根已收盘K线 · ${a.source}</span></div>
        <div class="dirline"><span class="${dirClass(a.momentum_dir)}">动量 ${a.momentum_dir}</span> <span class="sep">|</span> <span class="${dirClass(a.trend_dir)}">趋势 ${a.trend_dir}</span></div>
        <div class="basis">动量依据：${a.momentum_basis}</div>
        <div class="basis">趋势依据：SMA50 ${a.sma50??"—"} / SMA200 ${a.sma200??"—"}；趋势因子 ${a.trend_votes.pos} 多 / ${a.trend_votes.neg} 空（共 ${a.trend_votes.valid} 个）</div>
        <div class="numbers">${macdLine}<br>ATR ${a.atr_pct??"—"}% · 20期波动 ${a.vol20_pct??"—"}% · 近120期最大回撤 ${a.maxdd120_pct}% · 收盘 ${fmtPrice(a.last_close)}</div>
        <details><summary>因子明细（${a.factors.length} 个，票数制，无合成百分比）</summary>${factors}</details>
      </div>`;
    }).join("");
    return `<div class="symhead"><span class="sym">${s.symbol}/USDT</span><span class="price">${fmtPrice(s.price)}</span><span class="muted" style="font-size:12px">现价来源 ${s.price_source}（最后一根已收盘日线）</span></div><div class="grid">${cards}</div>`;
  }).join("");

  // ledger, newest first
  const byId = {}; ledger.forEach(r=>byId[r.id]=r);
  const settledMap = {}; settlements.forEach(r=>settledMap[r.settles]=r);
  const items = [...ledger].reverse().slice(0,120).map(r=>{
    if(r.type==="settlement"){
      const orig = byId[r.settles]||{};
      const v = r.verdict==="命中" ? `<span class="badge up">命中</span>` : (r.verdict==="未命中" ? `<span class="badge down">未命中</span>` : `<span class="badge accent">观察结清</span>`);
      return `<div class="ledger-item">${v} ${r.symbol} ${r.tf_label} · 结清 ${r.id} ← 记录 ${r.settles}（原方向 ${orig.call_dir||"—"}）<br>入场 ${fmtPrice(r.entry_price)} → 出场 ${fmtPrice(r.exit_price)} · 期间涨跌 ${pct(r.change_pct)}<br><span class="muted">结清时间 ${r.settled_at_bj}（北京） / ${r.settled_at_utc} · ${r.reason}</span></div>`;
    }
    const st = settledMap[r.id];
    const status = st ? (st.verdict==="命中"? `<span class="badge up">已结清 · 命中</span>` : (st.verdict==="未命中"? `<span class="badge down">已结清 · 未命中</span>` : `<span class="badge accent">已结清 · 观察</span>`)) : `<span class="badge accent">进行中</span>`;
    return `<div class="ledger-item">${status} ${r.symbol} ${r.tf_label} · ${r.id} · 方向 <span class="${dirClass(r.call_dir)}" style="font-weight:700">${r.call_dir}</span>（动量 ${r.momentum_dir} / 趋势 ${r.trend_dir}）<br>发出价 ${fmtPrice(r.price)} · 记录时间 ${r.recorded_at_bj}（北京） / ${r.recorded_at_utc}<br><span class="muted">${r.momentum_value}；${r.trend_value}；来源 ${r.source}</span></div>`;
  }).join("");
  document.getElementById("ledger").innerHTML = items || `<div class="ledger-item">暂无记录</div>`;
}
load().catch(e=>{ document.getElementById("symbols").innerHTML = `<div class="ledger-item">数据加载失败：${e.message}</div>`; });
