const TF_LABEL = {"4h":"4小时","1d":"日线","1w":"周线","1M":"月线"};
const TF_ORDER = ["4h","1d","1w","1M"];
function dirClass(d){ return d==="偏多" ? "up" : (d==="偏空" ? "down" : "accent"); }
function badgeClass(d){ return d==="偏多" ? "up" : (d==="偏空" ? "down" : "flat"); }
function pct(x){ const s = x>0?"+":""; return `<span class="${x>0?"up":(x<0?"down":"muted")}">${s}${x.toFixed(2)}%</span>`; }
function fmtPrice(p){ return p>=100? p.toFixed(2) : (p>=1? p.toFixed(4) : p.toFixed(5)); }

/* 半圆仪表盘口径（用户定版，写死于此）：
   指针位置只由该周期全部因子的投票平衡决定——
   balance = (多票 − 空票) / (多票 + 空票)，范围 [-1, 1]；
   -1 = 全部投空（指针最左，红区），+1 = 全部投多（指针最右，绿区），0 = 多空持平（正中）。
   仪表盘标题与标注一律写「因子投票」；它不是概率、不是胜率，不显示任何百分比。 */
function gaugeSVG(a){
  let pos = 0, neg = 0;
  a.factors.forEach(f=>{ if(f.vote > 0) pos++; else if(f.vote < 0) neg++; });
  const tot = pos + neg;
  const bal = tot ? (pos - neg) / tot : 0;
  const cx = 60, cy = 56, r = 46;
  const pt = (deg, rr)=>[cx + rr * Math.cos(Math.PI * deg / 180), cy - rr * Math.sin(Math.PI * deg / 180)];
  const arc = (d0, d1)=>{ const p0 = pt(d0, r), p1 = pt(d1, r); return `M ${p0[0].toFixed(1)} ${p0[1].toFixed(1)} A ${r} ${r} 0 0 1 ${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`; };
  const ticks = [180, 135, 90, 45, 0].map(d=>{ const p0 = pt(d, r - 5), p1 = pt(d, r); return `<line x1="${p0[0].toFixed(1)}" y1="${p0[1].toFixed(1)}" x2="${p1[0].toFixed(1)}" y2="${p1[1].toFixed(1)}" stroke="#4a5540" stroke-width="1.4"/>`; }).join("");
  const nDeg = 90 - bal * 90; // bal=-1 → 180（最左/空），bal=+1 → 0（最右/多）
  const np = pt(nDeg, r - 11);
  const ncol = bal > 0.05 ? "#2bea79" : (bal < -0.05 ? "#ff3761" : "#c6f542");
  return `<div class="gaugewrap"><svg class="gauge" viewBox="0 0 120 64" role="img" aria-label="因子投票仪表盘">
    <path d="${arc(180, 90)}" fill="none" stroke="rgba(255,55,97,.45)" stroke-width="7" stroke-linecap="round"/>
    <path d="${arc(90, 0)}" fill="none" stroke="rgba(43,234,121,.45)" stroke-width="7" stroke-linecap="round"/>
    ${ticks}
    <line x1="${cx}" y1="${cy}" x2="${np[0].toFixed(1)}" y2="${np[1].toFixed(1)}" stroke="${ncol}" stroke-width="2.6" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="3.6" fill="#fff"/>
    <text x="10" y="64" font-size="9" fill="#ff3761">空</text>
    <text x="104" y="64" font-size="9" fill="#2bea79">多</text>
  </svg><div class="gauge-cap">因子投票 <span class="mono" style="color:#fff">${pos} 多 / ${neg} 空</span>（共 ${tot} 票，非概率）</div></div>`;
}

/* 趋势票数天平条：以趋势因子多/空票数差从正中向两侧生长，装的是票数不是百分比 */
function balBar(v){
  const tot = v.pos + v.neg;
  const b = tot ? (v.pos - v.neg) / tot : 0;
  const w = Math.abs(b) * 50;
  const left = b < 0 ? 50 - w : 50;
  const col = b > 0 ? "#2bea79" : (b < 0 ? "#ff3761" : "#c6f542");
  const pips = `<span class="pips"><span class="up">${"●".repeat(v.pos)}</span><span class="down">${"●".repeat(v.neg)}</span></span>`;
  return `<div class="balbar"><div class="bal-mid"></div><div class="bal-fill" style="left:${left}%;width:${w}%;background:${col}"></div></div><div class="bal-cap">趋势票数天平 ${pips} <span class="mono">${v.pos} 多 / ${v.neg} 空</span></div>`;
}

/* sparkline：只用 current.json 的 spark_1d（已收盘日线收盘价，≤60 根）；无数据整块不渲染 */
function sparkSVG(s){
  const sp = s.spark_1d || [];
  if(sp.length < 2) return "";
  const w = 96, h = 28, min = Math.min(...sp), max = Math.max(...sp), rg = (max - min) || 1;
  const pts = sp.map((v, i)=>`${(i / (sp.length - 1) * w).toFixed(1)},${(h - 3 - ((v - min) / rg) * (h - 6)).toFixed(1)}`).join(" ");
  const chg = (sp[sp.length - 1] / sp[0] - 1) * 100;
  const col = chg > 0 ? "#2bea79" : (chg < 0 ? "#ff3761" : "#9a9a9a");
  const last = pts.split(" ").pop().split(",");
  return `<div class="spark"><svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/><circle cx="${last[0]}" cy="${last[1]}" r="2.4" fill="#c6f542"/></svg><div class="spark-cap">近${sp.length}根已收盘日线 <span style="color:${col}">${chg > 0 ? "+" : ""}${chg.toFixed(2)}%</span></div></div>`;
}

async function load(){
  const cur = await (await fetch("data/current.json")).json();
  const ledger = await (await fetch("data/ledger.json")).json();
  document.getElementById("gen").textContent = `数据生成：${cur.generated_at_bj}（北京时间） / ${cur.generated_at_utc}；主源 ${cur.source_primary}，兜底 ${cur.source_fallback}`;

  // scoreboard from settled ledger records only
  const settlements = ledger.filter(r=>r.type==="settlement");
  const scored = settlements.filter(r=>r.verdict==="命中"||r.verdict==="未命中");
  const hits = scored.filter(r=>r.verdict==="命中").length;
  const miss = scored.length - hits;
  const open = ledger.filter(r=>r.type==="signal").length - settlements.length;
  document.getElementById("sc-settled").textContent = scored.length;
  const rateEl = document.getElementById("sc-rate");
  if(scored.length>0){
    const rate = hits/scored.length*100;
    rateEl.innerHTML = `<span class="${rate>=50?"up":"down"}">${rate.toFixed(1)}%</span> <span class="muted" style="font-size:14px">（${hits}/${scored.length}）</span>`;
  } else {
    rateEl.innerHTML = `<span class="muted">暂无</span> <span class="muted" style="font-size:14px">（样本 0）</span>`;
  }
  document.getElementById("sc-hits").innerHTML = `<span class="up">${hits} 命中</span> / <span class="down">${miss} 未命中</span>`;
  const openEl = document.getElementById("sc-open"); openEl.textContent = Math.max(open,0);
  // 命中/未命中双色块：宽度按计数比例；全 0 时等宽灰块
  const hb = document.getElementById("hitbar");
  const hbH = document.getElementById("hb-hit"), hbM = document.getElementById("hb-miss");
  document.getElementById("hb-hit-lab").textContent = `命中 ${hits}`;
  document.getElementById("hb-miss-lab").textContent = `未命中 ${miss}`;
  if(scored.length>0){
    hb.classList.remove("zero");
    hbH.style.width = Math.max(hits/scored.length*100, 16) + "%";
    hbM.style.width = Math.max(miss/scored.length*100, 16) + "%";
  } else {
    hb.classList.add("zero");
    hbH.style.width = "50%"; hbM.style.width = "50%";
  }

  // symbol cards, two per row
  const host = document.getElementById("symbols");
  host.innerHTML = cur.symbols.map(s=>{
    const strip = TF_ORDER.filter(tf=>s.timeframes[tf]).map(tf=>{
      const a = s.timeframes[tf];
      return `<div class="tfseg seg-${badgeClass(a.call_dir)}"><div class="tfl">${TF_LABEL[tf]}</div><div class="tfd ${dirClass(a.call_dir)}">${a.call_dir}</div></div>`;
    }).join("");
    const cards = TF_ORDER.filter(tf=>s.timeframes[tf]).map(tf=>{
      const a = s.timeframes[tf];
      const m = a.macd;
      const macdLine = m? `MACD DIF ${m.dif} / DEA ${m.dea} / 柱 ${m.hist>0?"+":""}${m.hist}` : "MACD 历史不足";
      const factors = a.factors.map(f=>{
        const fcls = f.vote>0 ? "f-up" : (f.vote<0 ? "f-down" : "f-flat");
        return `<div class="factor ${fcls}"><span class="fdot"></span>${f.cat==="momentum"?"动量":"趋势"} · ${f.name}：<span class="${f.vote>0?"up":(f.vote<0?"down":"muted")}">${f.vote>0?"多":(f.vote<0?"空":"中")}</span> <span class="muted">${f.detail}</span></div>`;
      }).join("");
      return `<div class="card call-${badgeClass(a.call_dir)}">
        <div class="tf"><span>${TF_LABEL[tf]}</span><span>${a.bars} 根已收盘K线 · ${a.source}</span></div>
        ${gaugeSVG(a)}
        <div class="dirbadges"><span class="badge-d ${badgeClass(a.momentum_dir)}">动量 ${a.momentum_dir}</span><span class="badge-d ${badgeClass(a.trend_dir)}">趋势 ${a.trend_dir}</span><span class="badge-d ${badgeClass(a.call_dir)}">综合 ${a.call_dir}</span></div>
        <div class="basis">动量依据：${a.momentum_basis}</div>
        <div class="basis">趋势依据：SMA50 ${a.sma50??"—"} / SMA200 ${a.sma200??"—"}；趋势因子 ${a.trend_votes.pos} 多 / ${a.trend_votes.neg} 空（共 ${a.trend_votes.valid} 个）</div>
        ${balBar(a.trend_votes)}
        <div class="numbers">${macdLine}<br>ATR ${a.atr_pct??"—"}% · 20期波动 ${a.vol20_pct??"—"}% · 近120期最大回撤 ${a.maxdd120_pct}% · 收盘 ${fmtPrice(a.last_close)}</div>
        <details><summary>因子明细（${a.factors.length} 个，票数制，无合成百分比）</summary>${factors}</details>
      </div>`;
    }).join("");
    return `<div class="symblock"><div class="symhead"><div class="symmain"><span class="sym">${s.symbol}/USDT</span> <span class="price">${fmtPrice(s.price)}</span><div class="srcnote">现价来源 ${s.price_source}（最后一根已收盘日线）</div></div>${sparkSVG(s)}</div><div class="tfstrip">${strip}</div><div class="grid">${cards}</div></div>`;
  }).join("");

  // ledger, newest first
  const byId = {}; ledger.forEach(r=>byId[r.id]=r);
  const settledMap = {}; settlements.forEach(r=>settledMap[r.settles]=r);
  const items = [...ledger].reverse().slice(0,120).map(r=>{
    if(r.type==="settlement"){
      const orig = byId[r.settles]||{};
      const v = r.verdict==="命中" ? `<span class="badge up">命中</span>` : (r.verdict==="未命中" ? `<span class="badge down">未命中</span>` : `<span class="badge flat">观察结清</span>`);
      return `<div class="ledger-item">${v} ${r.symbol} ${r.tf_label} · 结清 ${r.id} ← 记录 ${r.settles}（原方向 ${orig.call_dir||"—"}）<br>入场 ${fmtPrice(r.entry_price)} → 出场 ${fmtPrice(r.exit_price)} · 期间涨跌 ${pct(r.change_pct)}<br><span class="muted">结清时间 ${r.settled_at_bj}（北京） / ${r.settled_at_utc} · ${r.reason}</span></div>`;
    }
    const st = settledMap[r.id];
    const status = st ? (st.verdict==="命中"? `<span class="badge up">已结清 · 命中</span>` : (st.verdict==="未命中"? `<span class="badge down">已结清 · 未命中</span>` : `<span class="badge flat">已结清 · 观察</span>`)) : `<span class="badge flat">进行中</span>`;
    return `<div class="ledger-item">${status} ${r.symbol} ${r.tf_label} · ${r.id} · 方向 <span class="${dirClass(r.call_dir)}" style="font-weight:700">${r.call_dir}</span>（动量 ${r.momentum_dir} / 趋势 ${r.trend_dir}）<br>发出价 ${fmtPrice(r.price)} · 记录时间 ${r.recorded_at_bj}（北京） / ${r.recorded_at_utc}<br><span class="muted">${r.momentum_value}；${r.trend_value}；来源 ${r.source}</span></div>`;
  }).join("");
  document.getElementById("ledger").innerHTML = items || `<div class="ledger-item">暂无记录</div>`;
}
load().catch(e=>{ document.getElementById("symbols").innerHTML = `<div class="ledger-item">数据加载失败：${e.message}</div>`; });
