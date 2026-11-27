const TF_LABEL = {"4h":"4小时","1d":"日线","1w":"周线","1M":"月线"};
const TF_ORDER = ["4h","1d","1w","1M"];
const CN_NAME = {"BTC":"比特币","ETH":"以太坊","SOL":"索拉纳","BNB":"币安币","XRP":"瑞波币","DOGE":"狗狗币","ADA":"艾达币","LINK":"链联"};
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
  const cx = 80, cy = 78, r = 62;
  const pt = (deg, rr)=>[cx + rr * Math.cos(Math.PI * deg / 180), cy - rr * Math.sin(Math.PI * deg / 180)];
  const arc = (d0, d1)=>{ const p0 = pt(d0, r), p1 = pt(d1, r); return `M ${p0[0].toFixed(1)} ${p0[1].toFixed(1)} A ${r} ${r} 0 0 1 ${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`; };
  const ticks = [180, 135, 90, 45, 0].map(d=>{ const p0 = pt(d, r - 7), p1 = pt(d, r + 3); return `<line x1="${p0[0].toFixed(1)}" y1="${p0[1].toFixed(1)}" x2="${p1[0].toFixed(1)}" y2="${p1[1].toFixed(1)}" stroke="#55624a" stroke-width="2.2"/>`; }).join("");
  const nDeg = 90 - bal * 90; // bal=-1 → 180（最左/空），bal=+1 → 0（最右/多）
  const np = pt(nDeg, r - 15);
  const ncol = bal > 0.05 ? "#2bea79" : (bal < -0.05 ? "#ff3761" : "#c6f542");
  return `<div class="gaugewrap"><svg class="gauge" viewBox="0 0 160 94" role="img" aria-label="因子投票仪表盘">
    <path d="${arc(180, 90)}" fill="none" stroke="rgba(255,55,97,.5)" stroke-width="12" stroke-linecap="round"/>
    <path d="${arc(90, 0)}" fill="none" stroke="rgba(43,234,121,.5)" stroke-width="12" stroke-linecap="round"/>
    ${ticks}
    <line x1="${cx}" y1="${cy}" x2="${np[0].toFixed(1)}" y2="${np[1].toFixed(1)}" stroke="${ncol}" stroke-width="5" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="6" fill="#fff"/>
    <circle cx="${cx}" cy="${cy}" r="2.6" fill="#111"/>
    <text x="4" y="93" font-size="13" font-weight="700" fill="#ff3761">空</text>
    <text x="143" y="93" font-size="13" font-weight="700" fill="#2bea79">多</text>
  </svg><div class="gauge-cap">因子投票 <span class="mono">${pos} 多 / ${neg} 空</span><div class="gauge-sub">共 ${tot} 票，非概率</div></div></div>`;
}

/* 因子点亮格：一格一个因子，绿=投多、红=投空、黄=中性；悬停看因子名与读数 */
function factorGrid(a){
  const cells = a.factors.map(f=>{
    const cls = f.vote>0 ? "f-up" : (f.vote<0 ? "f-down" : "f-flat");
    const vt = f.vote>0 ? "多" : (f.vote<0 ? "空" : "中");
    return `<span class="fcell ${cls}" title="${f.cat==="momentum"?"动量":"趋势"} · ${f.name}：${vt}（${f.detail}）"></span>`;
  }).join("");
  return `<div class="fgrid">${cells}</div>`;
}

function periodCard(tf, a){
  const factors = a.factors.map(f=>{
    const fcls = f.vote>0 ? "f-up" : (f.vote<0 ? "f-down" : "f-flat");
    return `<div class="factor ${fcls}"><span class="fdot"></span>${f.cat==="momentum"?"动量":"趋势"} · ${f.name}：<span class="${f.vote>0?"up":(f.vote<0?"down":"muted")}">${f.vote>0?"多":(f.vote<0?"空":"中")}</span> <span class="muted">${f.detail}</span></div>`;
  }).join("");
  const shortSrc = a.source.includes("Binance") ? "Gate+Binance" : "Gate";
  return `<div class="card call-${badgeClass(a.call_dir)}">
    <div class="tf"><span class="tfname">${TF_LABEL[tf]}</span><span class="tfmeta">${a.bars} 根 · ${shortSrc}</span></div>
    ${gaugeSVG(a)}
    <div class="dirbadges"><span class="badge-d ${badgeClass(a.momentum_dir)}"><i>动量</i><b>${a.momentum_dir}</b></span><span class="badge-d ${badgeClass(a.trend_dir)}"><i>趋势</i><b>${a.trend_dir}</b></span><span class="badge-d ${badgeClass(a.call_dir)}"><i>综合</i><b>${a.call_dir}</b></span></div>
    ${factorGrid(a)}
    <details><summary>因子明细（${a.factors.length} 个）</summary><div class="factor"><span class="muted">数据来源：${a.source} · ${a.bars} 根已收盘 K 线</span></div>${factors}</details>
  </div>`;
}

/* sparkline 宽条：只用 current.json 的 spark_1d（已收盘日线收盘价，≤60 根）；无数据整块不渲染 */
function sparkWide(s){
  const sp = s.spark_1d || [];
  if(sp.length < 2) return "";
  const w = 320, h = 64, min = Math.min(...sp), max = Math.max(...sp), rg = (max - min) || 1;
  const pts = sp.map((v, i)=>`${(i / (sp.length - 1) * w).toFixed(1)},${(h - 5 - ((v - min) / rg) * (h - 10)).toFixed(1)}`).join(" ");
  const chg = (sp[sp.length - 1] / sp[0] - 1) * 100;
  const col = chg > 0 ? "#2bea79" : (chg < 0 ? "#ff3761" : "#9a9a9a");
  const last = pts.split(" ").pop().split(",");
  return `<div class="sparkwide"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="已收盘日线走势"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8" vector-effect="non-scaling-stroke"/><circle cx="${last[0]}" cy="${last[1]}" r="3" fill="#c6f542"/></svg><div class="spark-caprow"><span>近${sp.length}根已收盘日线收盘价</span><span class="mono" style="color:${col}">区间 ${chg > 0 ? "+" : ""}${chg.toFixed(2)}%</span></div></div>`;
}

/* 芯片综合口径：四个周期全部因子票数合计（只是票数合计，不是概率） */
function aggVotes(s){
  let pos = 0, neg = 0;
  TF_ORDER.forEach(tf=>{
    const a = s.timeframes[tf]; if(!a) return;
    a.factors.forEach(f=>{ if(f.vote > 0) pos++; else if(f.vote < 0) neg++; });
  });
  const dir = pos > neg ? "偏多" : (pos < neg ? "偏空" : "中性");
  return {pos, neg, dir};
}

let selected = "BTC";
let curData = null;

function renderChips(cur){
  const host = document.getElementById("chips");
  host.innerHTML = cur.symbols.map(s=>{
    const v = aggVotes(s);
    const bc = badgeClass(v.dir);
    return `<button type="button" class="chip${s.symbol===selected?" sel":""}" data-sym="${s.symbol}">
      <span class="cdot ${bc}"></span>
      <span class="ccode">${s.symbol}</span>
      <span class="cname">${CN_NAME[s.symbol]||""}</span>
      <span class="cval"><span class="cbadge ${bc}">${v.dir}</span><span class="cvotes">${v.pos}多·${v.neg}空</span></span>
    </button>`;
  }).join("");
  host.querySelectorAll(".chip").forEach(ch=>{
    ch.addEventListener("click", ()=>{
      selected = ch.dataset.sym;
      renderChips(curData);
      renderDetail(curData);
    });
  });
}

function renderDetail(cur){
  const s = cur.symbols.find(x=>x.symbol===selected) || cur.symbols[0];
  if(!s) return;
  selected = s.symbol;
  const sp = s.spark_1d || [];
  let chgHtml = `<span class="muted">—</span>`;
  if(sp.length >= 2){
    const chg = (sp[sp.length - 1] / sp[sp.length - 2] - 1) * 100;
    chgHtml = `<span class="${chg>0?"up":(chg<0?"down":"muted")}">${chg>0?"+":""}${chg.toFixed(2)}%</span> <span class="dchg-lab">日线涨跌（已收盘）</span>`;
  }
  const cards = TF_ORDER.filter(tf=>s.timeframes[tf]).map(tf=>periodCard(tf, s.timeframes[tf])).join("");
  document.getElementById("detail").innerHTML = `
    <div class="dhead">
      <div class="dmain">
        <div class="dbig"><span class="dcode">${s.symbol}</span> <span class="dname">${CN_NAME[s.symbol]||""}</span></div>
        <div class="dsub">${s.symbol}/USDT 现货 · 动量与趋势分开 · 仪表盘为因子投票，非概率</div>
        <div class="dsub">现价来源 ${s.price_source.includes("Binance") ? "Gate（长历史 Binance 补全）" : s.price_source} · 最后一根已收盘日线 · 更新 ${cur.generated_at_bj}（北京）</div>
      </div>
      <div class="dright">
        <div class="dprice">${fmtPrice(s.price)}</div>
        <div class="dchg">${chgHtml}</div>
      </div>
    </div>
    <div class="grid">${cards}</div>
    ${sparkWide(s)}`;
}

function renderScore(ledger){
  const settlements = ledger.filter(r=>r.type==="settlement");
  const scored = settlements.filter(r=>r.verdict==="命中"||r.verdict==="未命中");
  const hits = scored.filter(r=>r.verdict==="命中").length;
  const miss = scored.length - hits;
  const open = ledger.filter(r=>r.type==="signal").length - settlements.length;
  document.getElementById("sc-settled").textContent = scored.length;
  const rateEl = document.getElementById("sc-rate");
  if(scored.length>0){
    const rate = hits/scored.length*100;
    rateEl.innerHTML = `<span class="${rate>=50?"up":"down"}">${rate.toFixed(1)}%</span><span class="muted rate-sub">（${hits}/${scored.length}）</span>`;
  } else {
    rateEl.innerHTML = `<span class="muted">暂无</span><span class="muted rate-sub">（样本 0）</span>`;
  }
  document.getElementById("sc-hits").innerHTML = `<span class="up">${hits} 命中</span> / <span class="down">${miss} 未命中</span>`;
  document.getElementById("sc-open").textContent = Math.max(open,0);
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
}

function renderLedger(ledger){
  const settlements = ledger.filter(r=>r.type==="settlement");
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

async function load(bust){
  const q = bust ? `?t=${Date.now()}` : "";
  const cur = await (await fetch(`data/current.json${q}`)).json();
  const ledger = await (await fetch(`data/ledger.json${q}`)).json();
  curData = cur;
  document.getElementById("gen").textContent = `数据生成：${cur.generated_at_bj}（北京时间） / ${cur.generated_at_utc}；主源 ${cur.source_primary}，兜底 ${cur.source_fallback}`;
  document.getElementById("cap-source").textContent = `主源 ${cur.source_primary}`;
  document.getElementById("cap-symbols").textContent = `${cur.symbols.length} 个标的 · 4 周期`;
  const f0 = cur.symbols[0] && cur.symbols[0].timeframes["1d"];
  document.getElementById("cap-factors").textContent = `${f0 ? f0.factors.length : "—"} 个因子 · 票数制`;
  document.getElementById("cap-updated").textContent = `更新 ${cur.generated_at_bj}`;
  renderScore(ledger);
  renderChips(cur);
  renderDetail(cur);
  renderLedger(ledger);
}

const refreshBtn = document.getElementById("refresh");
refreshBtn.addEventListener("click", async ()=>{
  refreshBtn.disabled = true;
  const old = refreshBtn.textContent;
  refreshBtn.textContent = "刷新中…";
  try { await load(true); } catch(e) { /* 保留旧内容，下次再试 */ }
  refreshBtn.textContent = old;
  refreshBtn.disabled = false;
});

load(false).catch(e=>{ document.getElementById("detail").innerHTML = `<div class="ledger-item">数据加载失败：${e.message}</div>`; });
