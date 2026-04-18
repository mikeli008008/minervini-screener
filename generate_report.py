"""
Minervini Screener - 完整HTML交互式报告生成器
=====================================
读取 reports/latest.json,生成 docs/index.html
如果开启GitHub Pages,即可在线访问
"""
import json
import os
from pathlib import Path


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MINERVINI SCREENER · __DATE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,600;9..144,800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0a0a0a; --bg-panel: #111; --bg-hover: #1a1a1a;
  --border: #1f1f1f; --border-light: #2a2a2a;
  --text: #e8e8e8; --text-dim: #888; --text-faint: #555;
  --accent: #d4ff00; --accent-dim: #9ab800;
  --red: #ff4444; --green: #00d68f; --amber: #ffaa00;
  --pass: #d4ff00; --fail: #ff3355;
}
* { margin:0; padding:0; box-sizing:border-box; }
html, body { background:var(--bg); color:var(--text); font-family:'JetBrains Mono',monospace; font-size:13px; line-height:1.5; overflow-x:hidden; }
body::before { content:''; position:fixed; inset:0; background-image: radial-gradient(circle at 15% 20%, rgba(212,255,0,0.03) 0%, transparent 40%), radial-gradient(circle at 85% 80%, rgba(0,214,143,0.02) 0%, transparent 40%); pointer-events:none; z-index:0; }
.wrap { position:relative; z-index:1; max-width:1600px; margin:0 auto; padding:24px 32px; }
.header { display:flex; align-items:flex-end; justify-content:space-between; padding-bottom:20px; margin-bottom:28px; border-bottom:1px solid var(--border-light); }
.brand h1 { font-family:'Fraunces',serif; font-size:42px; font-weight:300; letter-spacing:-0.02em; line-height:1; margin-bottom:8px; }
.brand h1 em { font-style:italic; color:var(--accent); font-weight:400; }
.brand .sub { font-size:11px; color:var(--text-dim); letter-spacing:0.15em; text-transform:uppercase; }
.meta { text-align:right; font-size:11px; color:var(--text-dim); }
.meta .clock { font-size:13px; color:var(--text); letter-spacing:0.05em; }
.stats { display:grid; grid-template-columns:repeat(5,1fr); gap:1px; background:var(--border); border:1px solid var(--border); margin-bottom:24px; }
.stat { background:var(--bg-panel); padding:18px 20px; }
.stat .label { font-size:10px; color:var(--text-dim); letter-spacing:0.15em; text-transform:uppercase; margin-bottom:8px; }
.stat .value { font-family:'Fraunces',serif; font-size:32px; font-weight:300; letter-spacing:-0.02em; line-height:1; }
.stat .value .unit { font-size:14px; color:var(--text-dim); margin-left:4px; }
.stat.accent .value { color:var(--accent); }
.stat .trend { font-size:11px; margin-top:6px; color:var(--text-dim); }
.filters { display:flex; gap:16px; align-items:center; padding:16px 20px; background:var(--bg-panel); border:1px solid var(--border); margin-bottom:1px; flex-wrap:wrap; }
.filters .fgroup { display:flex; align-items:center; gap:8px; }
.filters label { font-size:10px; color:var(--text-dim); letter-spacing:0.1em; text-transform:uppercase; }
.filters select, .filters input { background:var(--bg); border:1px solid var(--border-light); color:var(--text); padding:6px 10px; font-family:inherit; font-size:12px; outline:none; }
.filters select:focus, .filters input:focus { border-color:var(--accent); }
.filters .toggle { padding:6px 12px; border:1px solid var(--border-light); cursor:pointer; font-size:11px; letter-spacing:0.1em; color:var(--text-dim); transition:all 0.15s; user-select:none; }
.filters .toggle:hover { color:var(--text); border-color:var(--text-dim); }
.filters .toggle.active { color:var(--bg); background:var(--accent); border-color:var(--accent); }
.filters .count { margin-left:auto; font-size:11px; color:var(--text-dim); }
.filters .count b { color:var(--accent); font-weight:500; }
.table-wrap { border:1px solid var(--border); background:var(--bg-panel); overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:12px; }
thead th { background:#0f0f0f; color:var(--text-dim); font-weight:500; font-size:10px; letter-spacing:0.12em; text-transform:uppercase; text-align:left; padding:12px 14px; border-bottom:1px solid var(--border-light); cursor:pointer; user-select:none; white-space:nowrap; position:sticky; top:0; z-index:10; }
thead th:hover { color:var(--text); }
thead th.sorted { color:var(--accent); }
thead th.sorted::after { content:' ▾'; }
thead th.sorted.asc::after { content:' ▴'; }
thead th.num { text-align:right; }
tbody tr { border-bottom:1px solid var(--border); cursor:pointer; transition:background 0.1s; }
tbody tr:hover { background:var(--bg-hover); }
tbody tr.expanded { background:var(--bg-hover); }
tbody td { padding:12px 14px; white-space:nowrap; }
tbody td.num { text-align:right; font-variant-numeric:tabular-nums; }
.ticker { font-weight:700; color:var(--text); letter-spacing:0.02em; }
.name { color:var(--text-dim); font-size:11px; max-width:180px; overflow:hidden; text-overflow:ellipsis; }
.score-cell { display:inline-flex; align-items:center; gap:8px; font-family:'Fraunces',serif; font-weight:600; font-size:15px; }
.score-bar { display:inline-block; width:40px; height:4px; background:var(--border-light); position:relative; overflow:hidden; }
.criteria-dots { display:inline-flex; gap:3px; }
.dot { width:8px; height:8px; border-radius:50%; background:var(--fail); opacity:0.3; }
.dot.on { background:var(--pass); opacity:1; }
.rs-badge { display:inline-block; padding:2px 8px; border:1px solid var(--border-light); font-size:11px; font-weight:500; }
.rs-badge.high { color:var(--accent); border-color:var(--accent-dim); }
.rs-badge.mid { color:var(--amber); border-color:var(--amber); }
.rs-badge.low { color:var(--text-dim); }
.pct.pos { color:var(--green); }
.pct.neg { color:var(--red); }
.tag { display:inline-block; padding:2px 6px; font-size:10px; letter-spacing:0.05em; background:var(--border); color:var(--text-dim); text-transform:uppercase; }
.tag.vcp { background:rgba(212,255,0,0.12); color:var(--accent); }
.tag.vol { background:rgba(0,214,143,0.12); color:var(--green); }
.detail-row { display:none; }
.detail-row.show { display:table-row; }
.detail-row td { padding:0; background:#0d0d0d; border-bottom:1px solid var(--border-light); }
.detail-inner { padding:24px 28px; display:grid; grid-template-columns:1fr 1fr; gap:32px; }
.detail-section h3 { font-family:'Fraunces',serif; font-size:16px; font-weight:400; color:var(--text); margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid var(--border); letter-spacing:-0.01em; }
.criteria-list { list-style:none; }
.criteria-list li { display:flex; align-items:center; gap:12px; padding:8px 0; font-size:12px; border-bottom:1px dashed var(--border); }
.criteria-list li:last-child { border:none; }
.check { width:20px; height:20px; display:inline-flex; align-items:center; justify-content:center; border:1px solid; border-radius:2px; font-weight:700; font-size:11px; flex-shrink:0; }
.check.pass { color:var(--pass); border-color:var(--pass); }
.check.fail { color:var(--fail); border-color:var(--fail); opacity:0.6; }
.criteria-list .desc { flex:1; color:var(--text); }
.chart-box { background:var(--bg); border:1px solid var(--border); padding:20px; height:280px; position:relative; }
.chart-box svg { width:100%; height:100%; }
.chart-box .chart-label { position:absolute; top:12px; left:16px; font-size:10px; color:var(--text-dim); letter-spacing:0.1em; text-transform:uppercase; }
.chart-box .chart-price { position:absolute; top:12px; right:16px; font-family:'Fraunces',serif; font-size:18px; color:var(--text); }
.metrics-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:1px; background:var(--border); margin-top:16px; }
.mcell { background:var(--bg); padding:12px; }
.mcell .ml { font-size:9px; color:var(--text-faint); letter-spacing:0.1em; text-transform:uppercase; }
.mcell .mv { font-size:14px; color:var(--text); margin-top:4px; font-variant-numeric:tabular-nums; }
.footer { margin-top:32px; padding-top:20px; border-top:1px solid var(--border); font-size:11px; color:var(--text-faint); text-align:center; letter-spacing:0.1em; }
.footer em { color:var(--text-dim); font-style:italic; }
.tape { overflow:hidden; border-top:1px solid var(--border); border-bottom:1px solid var(--border); background:#080808; padding:8px 0; margin-bottom:24px; }
.tape-inner { display:flex; gap:32px; animation:scroll 60s linear infinite; white-space:nowrap; font-size:11px; }
.tape-item { color:var(--text-dim); }
.tape-item .t { color:var(--text); font-weight:500; }
.tape-item .p { color:var(--green); }
.tape-item .p.down { color:var(--red); }
@keyframes scroll { from { transform:translateX(0); } to { transform:translateX(-50%); } }
@media (max-width:900px) {
  .wrap { padding:16px; }
  .header { flex-direction:column; align-items:flex-start; gap:16px; }
  .brand h1 { font-size:32px; }
  .stats { grid-template-columns:repeat(2,1fr); }
  .detail-inner { grid-template-columns:1fr; }
  thead th, tbody td { padding:8px 10px; font-size:11px; }
  .name { display:none; }
}
</style>
</head>
<body>
<div class="wrap">
<header class="header">
  <div class="brand">
    <h1>MINERVINI <em>SCREENER</em></h1>
    <div class="sub">SEPA · Stage 2 Uptrend · VCP Detection</div>
  </div>
  <div class="meta">
    <div class="clock" id="clock"></div>
    <div>Data: US Equities · <span id="dataDate"></span></div>
    <div>Benchmark SPY 1Y: <span id="spyRet"></span></div>
  </div>
</header>
<div class="tape"><div class="tape-inner" id="tape"></div></div>
<div class="stats" style="grid-template-columns:repeat(6,1fr);">
  <div class="stat accent"><div class="label">Universe</div><div class="value" id="sTotal">—</div><div class="trend">scanned</div></div>
  <div class="stat"><div class="label">All 8 Passed</div><div class="value"><span id="s8num">—</span></div><div class="trend">qualifiers</div></div>
  <div class="stat" style="background:linear-gradient(135deg, rgba(212,255,0,0.06), var(--bg-panel));">
    <div class="label" style="color:var(--accent);">★ Perfect</div>
    <div class="value" id="sPerfect" style="color:var(--accent);">—</div>
    <div class="trend" style="color:var(--accent);">top priority</div>
  </div>
  <div class="stat"><div class="label">True VCP</div><div class="value" id="sTrueVCP">—</div><div class="trend">pattern match</div></div>
  <div class="stat"><div class="label">Near Pivot</div><div class="value" id="sNearPivot">—</div><div class="trend">breakout zone</div></div>
  <div class="stat"><div class="label">Top RS</div><div class="value" id="sRS">—</div><div class="trend">percentile 99</div></div>
</div>
<div class="filters">
  <div class="fgroup"><label>Filter</label>
    <div class="toggle active" data-filter="all">All</div>
    <div class="toggle" data-filter="perfect" style="color:var(--accent);border-color:var(--accent-dim);">★ Perfect</div>
    <div class="toggle" data-filter="truevcp">True VCP</div>
    <div class="toggle" data-filter="pass8">8/8 Pass</div>
    <div class="toggle" data-filter="pass7">7+/8</div>
    <div class="toggle" data-filter="nearpivot">Near Pivot</div>
    <div class="toggle" data-filter="rs90">RS ≥ 90</div>
  </div>
  <div class="fgroup"><label>Sector</label><select id="sectorFilter"><option value="">All Sectors</option></select></div>
  <div class="fgroup"><label>Search</label><input type="text" id="search" placeholder="Ticker or name..." style="width:180px;"></div>
  <div class="count">Showing <b id="showCount">0</b> of <span id="totalCount">0</span></div>
</div>
<div class="table-wrap">
  <table id="stockTable">
    <thead><tr>
      <th data-sort="ticker">Ticker</th><th data-sort="name">Company</th><th data-sort="sector">Sector</th>
      <th data-sort="minervini_score" class="num sorted">Score</th><th data-sort="criteria_passed" class="num">Pass</th>
      <th data-sort="rs_rating" class="num">RS</th><th data-sort="price" class="num">Price</th>
      <th data-sort="return_1y" class="num">1Y %</th><th data-sort="pct_from_high" class="num">From High</th>
      <th>Setup</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>
<div class="footer">
  Strategy reference · <em>Mark Minervini — SEPA Methodology · Trade Like a Stock Market Wizard</em><br>
  This is a research tool. Not investment advice. Always do your own due diligence.
</div>
</div>
<script>
const DATA = __DATA_PLACEHOLDER__;
const CRITERIA_LABELS = {
  c1_price_above_ma150_200:'收盘价在150日与200日均线之上',
  c2_ma150_above_ma200:'150日均线在200日均线之上',
  c3_ma200_uptrend:'200日均线向上（至少1个月）',
  c4_ma50_above_ma150_200:'50日均线在150日与200日均线之上',
  c5_price_above_ma50:'收盘价在50日均线之上',
  c6_price_30pct_above_low:'当前价格比52周低点高30%以上',
  c7_price_within_25pct_of_high:'当前价格在52周高点的25%范围内',
  c8_rs_rating_70plus:'相对强度RS评分 ≥ 70'
};
let state = { filter:'all', sector:'', search:'', sortKey:'minervini_score', sortAsc:false, expandedTicker:null };
function fmt(n,d=2){ if(n===null||n===undefined) return '—'; return Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}); }
function fmtPct(n,d=1){ if(n===null||n===undefined) return '—'; const s = n>0?'+':''; return s+fmt(n,d)+'%'; }
function mcFmt(mc){ if(!mc) return '—'; if(mc>=1e12) return (mc/1e12).toFixed(2)+'T'; if(mc>=1e9) return (mc/1e9).toFixed(1)+'B'; if(mc>=1e6) return (mc/1e6).toFixed(1)+'M'; return mc.toString(); }
function updateClock(){ const n=new Date(); document.getElementById('clock').textContent = n.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' LOCAL'; }
setInterval(updateClock,1000); updateClock();
function initStats(){
  document.getElementById('sTotal').textContent = DATA.total_stocks;
  document.getElementById('totalCount').textContent = DATA.total_stocks;
  document.getElementById('s8num').textContent = DATA.all_8_passed_count;
  document.getElementById('dataDate').textContent = DATA.generated_at.split(' ')[0];
  document.getElementById('spyRet').textContent = fmtPct(DATA.spy_return_1y);
  document.getElementById('sPerfect').textContent = DATA.perfect_setup_count || 0;
  document.getElementById('sTrueVCP').textContent = DATA.true_vcp_count || 0;
  document.getElementById('sNearPivot').textContent = DATA.near_pivot_count || 0;
  const maxRS = Math.max(...DATA.stocks.map(s=>s.rs_rating));
  document.getElementById('sRS').textContent = Math.round(maxRS);
  const sectors = [...new Set(DATA.stocks.map(s=>s.sector))].sort();
  const sel = document.getElementById('sectorFilter');
  sectors.forEach(s=>{ if(s && s!=='N/A'){ const o=document.createElement('option'); o.value=s; o.textContent=s; sel.appendChild(o); } });
  const tape = document.getElementById('tape');
  const tapeStocks = DATA.stocks.slice(0,20);
  const tapeHTML = tapeStocks.map(s=>{ const cls = s.return_1y>=0?'p':'p down'; return `<span class="tape-item"><span class="t">${s.ticker}</span> <span>$${fmt(s.price)}</span> <span class="${cls}">${fmtPct(s.return_1y)}</span></span>`; }).join('');
  tape.innerHTML = tapeHTML+tapeHTML;
}
function getFiltered(){
  let list = DATA.stocks.slice();
  if(state.filter==='perfect') list = list.filter(s => (s.vcp||{}).has_vcp && s.all_8_passed && (s.vcp||{}).near_pivot);
  else if(state.filter==='truevcp') list = list.filter(s => (s.vcp||{}).has_vcp);
  else if(state.filter==='pass8') list = list.filter(s=>s.criteria_passed===8);
  else if(state.filter==='pass7') list = list.filter(s=>s.criteria_passed>=7);
  else if(state.filter==='nearpivot') list = list.filter(s=>(s.vcp||{}).near_pivot);
  else if(state.filter==='rs90') list = list.filter(s=>s.rs_rating>=90);
  if(state.sector) list = list.filter(s=>s.sector===state.sector);
  if(state.search){ const q = state.search.toLowerCase(); list = list.filter(s=>s.ticker.toLowerCase().includes(q)||s.name.toLowerCase().includes(q)); }
  list.sort((a,b)=>{ const va=a[state.sortKey], vb=b[state.sortKey]; if(typeof va==='string') return state.sortAsc?va.localeCompare(vb):vb.localeCompare(va); return state.sortAsc?va-vb:vb-va; });
  return list;
}
function renderTable(){
  const list = getFiltered();
  const tbody = document.getElementById('tbody');
  document.getElementById('showCount').textContent = list.length;
  tbody.innerHTML = list.map(s=>{
    const c = s.criteria;
    const dots = Object.values(c).map(v=>`<span class="dot${v?' on':''}"></span>`).join('');
    const rsClass = s.rs_rating>=90?'high':s.rs_rating>=70?'mid':'low';
    const retClass = s.return_1y>=0?'pos':'neg';
    const v = s.vcp || {};
    const isPerfect = v.has_vcp && s.all_8_passed && v.near_pivot;
    const tags = [];
    if (isPerfect) {
      tags.push('<span class="tag" style="background:linear-gradient(135deg,rgba(212,255,0,0.25),rgba(212,255,0,0.1));color:var(--accent);font-weight:700;letter-spacing:0.08em;border:1px solid rgba(212,255,0,0.4);">★PERFECT</span>');
    } else if (v.has_vcp) {
      tags.push('<span class="tag vcp" style="font-weight:600;">✓VCP</span>');
    } else if (s.volatility_contraction) {
      tags.push('<span class="tag" style="color:#9ab800;background:rgba(212,255,0,0.06);">atr</span>');
    }
    if (v.near_pivot && !isPerfect) {
      tags.push('<span class="tag" style="background:rgba(255,170,0,0.18);color:var(--amber);">PIVOT</span>');
    }
    if (s.volume_drying) tags.push('<span class="tag vol">VOL↓</span>');
    const scoreBarWidth = Math.min(100,(s.minervini_score/135)*100);
    return `<tr data-ticker="${s.ticker}" onclick="toggleDetail('${s.ticker}')">
      <td class="ticker">${s.ticker}</td><td class="name">${s.name}</td>
      <td style="color:var(--text-dim);font-size:11px;">${s.sector.substring(0,12)}</td>
      <td class="num"><span class="score-cell">${fmt(s.minervini_score,1)}<span class="score-bar"><span style="display:block;height:100%;background:var(--accent);width:${scoreBarWidth}%"></span></span></span></td>
      <td class="num"><span class="criteria-dots">${dots}</span> <span style="margin-left:6px;color:var(--text-dim);">${s.criteria_passed}/8</span></td>
      <td class="num"><span class="rs-badge ${rsClass}">${Math.round(s.rs_rating)}</span></td>
      <td class="num">$${fmt(s.price)}</td>
      <td class="num pct ${retClass}">${fmtPct(s.return_1y)}</td>
      <td class="num" style="color:var(--text-dim);">${fmtPct(s.pct_from_high)}</td>
      <td>${tags.join(' ')}</td>
    </tr>
    <tr class="detail-row" id="detail-${s.ticker}"><td colspan="10"></td></tr>`;
  }).join('');
  document.querySelectorAll('thead th').forEach(th=>{ th.classList.remove('sorted','asc'); if(th.dataset.sort===state.sortKey){ th.classList.add('sorted'); if(state.sortAsc) th.classList.add('asc'); } });
  if(state.expandedTicker){ const row = document.querySelector(`tr[data-ticker="${state.expandedTicker}"]`); if(row) expandDetail(state.expandedTicker,true); }
}
function toggleDetail(ticker){
  const detailRow = document.getElementById(`detail-${ticker}`);
  const mainRow = document.querySelector(`tr[data-ticker="${ticker}"]`);
  if(state.expandedTicker===ticker){ detailRow.classList.remove('show'); mainRow.classList.remove('expanded'); state.expandedTicker=null; }
  else { if(state.expandedTicker){ const prev=document.getElementById(`detail-${state.expandedTicker}`); const prevMain=document.querySelector(`tr[data-ticker="${state.expandedTicker}"]`); if(prev) prev.classList.remove('show'); if(prevMain) prevMain.classList.remove('expanded'); } expandDetail(ticker); state.expandedTicker=ticker; }
}
function expandDetail(ticker){
  const s = DATA.stocks.find(x=>x.ticker===ticker); if(!s) return;
  const detailRow = document.getElementById(`detail-${ticker}`);
  const mainRow = document.querySelector(`tr[data-ticker="${ticker}"]`);
  if(!detailRow) return;
  const criteriaItems = Object.entries(s.criteria).map(([k,v])=>`<li><span class="check ${v?'pass':'fail'}">${v?'✓':'✗'}</span><span class="desc">${CRITERIA_LABELS[k]}</span></li>`).join('');
  const chart = renderChart(s);
  
  // === VCP详情区 ===
  const vcp = s.vcp || {};
  const hasVcp = vcp.has_vcp;
  const contractions = vcp.contractions || [];
  const isPerfect = hasVcp && s.all_8_passed && vcp.near_pivot;
  
  let vcpContent;
  if (contractions.length === 0) {
    vcpContent = `<div style="color:var(--text-dim);font-size:12px;padding:16px 0;text-align:center;">
      No significant contractions detected in the last 90 days.
    </div>`;
  } else {
    const depthsHTML = contractions.map((c, i) => {
      const isLast = i === contractions.length - 1;
      const color = isLast ? 'var(--accent)' : 'var(--text-dim)';
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--border);font-size:11px;">
        <span style="color:var(--text-dim);">#${i+1}</span>
        <span style="color:var(--text);font-family:monospace;">$${fmt(c.peak_price)} → $${fmt(c.trough_price)}</span>
        <span style="color:${color};font-weight:${isLast?'600':'400'};">${c.depth_pct.toFixed(1)}%</span>
      </div>`;
    }).join('');
    
    const tightening = vcp.tightening ? 
      '<span style="color:var(--accent);">Tightening ✓</span>' : 
      '<span style="color:var(--amber);">Not tightening</span>';
    
    const nearPivot = vcp.near_pivot ? 
      '<span style="color:var(--accent);">In breakout zone ✓</span>' : 
      '<span style="color:var(--text-dim);">Not near pivot</span>';
    
    const vcpStatus = hasVcp ? 
      `<div style="background:linear-gradient(135deg, rgba(212,255,0,0.12), rgba(212,255,0,0.02));border:1px solid rgba(212,255,0,0.3);border-left:3px solid var(--accent);padding:10px 14px;margin-bottom:14px;">
        <div style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:0.05em;">${isPerfect ? '★ PERFECT SETUP' : '✓ TRUE VCP DETECTED'}</div>
        <div style="color:var(--text-dim);font-size:10px;margin-top:3px;">VCP Score: ${vcp.score}/100 · ${contractions.length} contractions</div>
      </div>` :
      `<div style="background:var(--bg);border:1px solid var(--border);padding:10px 14px;margin-bottom:14px;">
        <div style="color:var(--text-dim);font-size:12px;">No VCP pattern (Score: ${vcp.score || 0}/100)</div>
        <div style="color:var(--text-faint);font-size:10px;margin-top:3px;">Needs: ≥2 tightening contractions, final &lt;15%</div>
      </div>`;
    
    const currentPrice = s.price;
    const pivot = vcp.pivot_price || 0;
    const distToPivot = pivot ? ((pivot - currentPrice) / pivot * 100) : 0;
    const pivotStatus = currentPrice >= pivot 
      ? `<span style="color:var(--accent);font-weight:600;">ABOVE PIVOT</span>` 
      : `${distToPivot.toFixed(1)}% below`;
    
    vcpContent = `
      ${vcpStatus}
      <div class="metrics-grid" style="margin-bottom:16px;">
        <div class="mcell">
          <div class="ml">Pivot Price</div>
          <div class="mv" style="color:var(--amber);font-weight:600;">$${fmt(pivot)}</div>
        </div>
        <div class="mcell">
          <div class="ml">Distance</div>
          <div class="mv" style="font-size:11px;">${pivotStatus}</div>
        </div>
        <div class="mcell">
          <div class="ml">Volume Ratio</div>
          <div class="mv" style="color:${vcp.volume_ratio < 0.85 ? 'var(--accent)' : 'var(--text-dim)'};">${fmt(vcp.volume_ratio || 1, 2)}×</div>
        </div>
      </div>
      <div style="font-size:10px;color:var(--text-dim);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;">
        Contraction sequence
      </div>
      ${depthsHTML}
      <div style="display:flex;gap:12px;margin-top:12px;font-size:11px;">
        ${tightening} · ${nearPivot}
      </div>`;
  }
  
  detailRow.querySelector('td').innerHTML = `<div class="detail-inner" style="grid-template-columns:1fr 1fr 1fr;">
    <div class="detail-section">
      <h3>Trend Template · 趋势模板</h3>
      <ul class="criteria-list">${criteriaItems}</ul>
      <div class="metrics-grid" style="margin-top:16px;">
        <div class="mcell"><div class="ml">Market Cap</div><div class="mv">$${mcFmt(s.market_cap)}</div></div>
        <div class="mcell"><div class="ml">52W High</div><div class="mv">$${fmt(s.high_52w)}</div></div>
        <div class="mcell"><div class="ml">52W Low</div><div class="mv">$${fmt(s.low_52w)}</div></div>
        <div class="mcell"><div class="ml">MA 50</div><div class="mv">$${fmt(s.ma50)}</div></div>
        <div class="mcell"><div class="ml">MA 200</div><div class="mv">$${fmt(s.ma200)}</div></div>
        <div class="mcell"><div class="ml">From Low</div><div class="mv" style="color:var(--green)">+${fmt(s.pct_from_low,0)}%</div></div>
      </div>
    </div>
    
    <div class="detail-section">
      <h3>VCP Analysis · 波动收缩</h3>
      ${vcpContent}
    </div>
    
    <div class="detail-section">
      <h3>Price Action · 价格走势 (6M)</h3>
      <div class="chart-box">
        <div class="chart-label">${s.ticker} · ${s.industry||''}</div>
        <div class="chart-price">$${fmt(s.price)}</div>
        ${chart}
      </div>
      <div class="metrics-grid" style="margin-top:12px;">
        <div class="mcell"><div class="ml">ATR 10D</div><div class="mv">${fmt(s.atr_10)}</div></div>
        <div class="mcell"><div class="ml">ATR 40D</div><div class="mv">${fmt(s.atr_40)}</div></div>
        <div class="mcell"><div class="ml">Pullback</div><div class="mv">${fmtPct(s.pullback_from_recent_high)}</div></div>
        <div class="mcell"><div class="ml">RS Rating</div><div class="mv" style="color:var(--accent)">${Math.round(s.rs_rating)}</div></div>
        <div class="mcell"><div class="ml">RS vs SPY</div><div class="mv" style="color:var(--accent)">+${fmt(s.rs_raw,0)}%</div></div>
        <div class="mcell"><div class="ml">1Y Return</div><div class="mv" style="color:${s.return_1y>=0?'var(--green)':'var(--red)'}">${fmtPct(s.return_1y)}</div></div>
      </div>
    </div>
  </div>`;
  detailRow.classList.add('show'); mainRow.classList.add('expanded');
}
function renderChart(s){
  const hist = s.price_history; if(!hist||hist.length<2) return '';
  const w=600,h=220,padL=50,padR=20,padT=30,padB=30;
  const prices = hist.map(p=>p.c);
  let minP=Math.min(...prices), maxP=Math.max(...prices);
  
  // 如果有pivot,让图表包含pivot价格范围
  const vcp = s.vcp || {};
  const pivot = vcp.pivot_price || 0;
  if (pivot > 0) {
    minP = Math.min(minP, pivot * 0.98);
    maxP = Math.max(maxP, pivot * 1.02);
  }
  const range = maxP - minP || 1;
  
  const x=i=>padL+(i/(hist.length-1))*(w-padL-padR);
  const y=p=>padT+(1-(p-minP)/range)*(h-padT-padB);
  const path = hist.map((p,i)=>`${i===0?'M':'L'}${x(i).toFixed(1)} ${y(p.c).toFixed(1)}`).join(' ');
  const area = `M${x(0).toFixed(1)} ${y(hist[0].c).toFixed(1)} `+hist.slice(1).map((p,i)=>`L${x(i+1).toFixed(1)} ${y(p.c).toFixed(1)}`).join(' ')+` L${x(hist.length-1).toFixed(1)} ${h-padB} L${x(0).toFixed(1)} ${h-padB} Z`;
  function sma(arr,period){ const out=[]; for(let i=0;i<arr.length;i++){ if(i<period-1){ out.push(null); continue; } let sum=0; for(let j=i-period+1;j<=i;j++) sum+=arr[j]; out.push(sum/period); } return out; }
  const ma20 = sma(prices,20);
  const firstIdx = ma20.findIndex(x=>x!==null);
  const ma20line = ma20.map((v,i)=>v!==null?`${i===firstIdx?'M':'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`:'').filter(s=>s).join(' ');
  const yLabels = [0,0.25,0.5,0.75,1].map(t=>{ const price=minP+range*(1-t); return `<text x="${padL-6}" y="${(padT+t*(h-padT-padB)).toFixed(1)}" text-anchor="end" fill="#555" font-size="9" dominant-baseline="middle">$${price.toFixed(0)}</text>`; }).join('');
  const xTicks = [0,Math.floor(hist.length*0.33),Math.floor(hist.length*0.66),hist.length-1];
  const xLabels = xTicks.map(i=>`<text x="${x(i).toFixed(1)}" y="${h-8}" text-anchor="middle" fill="#555" font-size="9">${hist[i].d}</text>`).join('');
  const gridLines = [0.25,0.5,0.75].map(t=>{ const yy=padT+t*(h-padT-padB); return `<line x1="${padL}" y1="${yy}" x2="${w-padR}" y2="${yy}" stroke="#1a1a1a" stroke-dasharray="2 4"/>`; }).join('');
  const lastX=x(hist.length-1), lastY=y(hist[hist.length-1].c);
  const trendColor = hist[hist.length-1].c>=hist[0].c?'#d4ff00':'#ff4444';
  
  // === Pivot line ===
  let pivotLine = '';
  if (pivot > 0) {
    const pivotY = y(pivot);
    const pivotColor = '#ffaa00';
    pivotLine = `
      <line x1="${padL}" y1="${pivotY.toFixed(1)}" x2="${w-padR}" y2="${pivotY.toFixed(1)}" 
            stroke="${pivotColor}" stroke-width="1" stroke-dasharray="4 3" opacity="0.7"/>
      <rect x="${w-padR-48}" y="${pivotY-8}" width="46" height="14" fill="${pivotColor}" opacity="0.9" rx="1"/>
      <text x="${w-padR-25}" y="${pivotY+2}" text-anchor="middle" fill="#0a0a0a" font-size="9" font-weight="700" dominant-baseline="middle">PIVOT $${pivot.toFixed(0)}</text>`;
  }
  
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="g-${s.ticker}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="${trendColor}" stop-opacity="0.15"/><stop offset="100%" stop-color="${trendColor}" stop-opacity="0"/></linearGradient></defs>
    ${gridLines}${yLabels}${xLabels}
    <path d="${area}" fill="url(#g-${s.ticker})"/>
    <path d="${ma20line}" fill="none" stroke="#555" stroke-width="1" stroke-dasharray="3 3"/>
    <path d="${path}" fill="none" stroke="${trendColor}" stroke-width="1.5"/>
    ${pivotLine}
    <circle cx="${lastX}" cy="${lastY}" r="3" fill="${trendColor}"/>
    <circle cx="${lastX}" cy="${lastY}" r="6" fill="${trendColor}" opacity="0.3"/>
  </svg>`;
}
document.querySelectorAll('.toggle').forEach(t=>{ t.addEventListener('click',e=>{ e.stopPropagation(); document.querySelectorAll('.toggle').forEach(x=>x.classList.remove('active')); t.classList.add('active'); state.filter=t.dataset.filter; state.expandedTicker=null; renderTable(); }); });
document.getElementById('sectorFilter').addEventListener('change',e=>{ state.sector=e.target.value; state.expandedTicker=null; renderTable(); });
document.getElementById('search').addEventListener('input',e=>{ state.search=e.target.value; state.expandedTicker=null; renderTable(); });
document.querySelectorAll('thead th').forEach(th=>{ th.addEventListener('click',()=>{ const key=th.dataset.sort; if(!key) return; if(state.sortKey===key) state.sortAsc=!state.sortAsc; else { state.sortKey=key; state.sortAsc=false; } state.expandedTicker=null; renderTable(); }); });
initStats(); renderTable();
</script>
</body>
</html>'''


def main():
    with open('reports/latest.json') as f:
        data = json.load(f)
    
    html = HTML_TEMPLATE.replace('__DATA_PLACEHOLDER__', json.dumps(data, separators=(',', ':')))
    html = html.replace('__DATE__', data['date'])
    
    # 输出到 docs/index.html (GitHub Pages默认目录)
    Path('docs').mkdir(exist_ok=True)
    with open('docs/index.html', 'w') as f:
        f.write(html)
    
    # 也归档每日副本
    with open(f'docs/report_{data["date"]}.html', 'w') as f:
        f.write(html)
    
    print(f"✓ Full report generated: docs/index.html ({len(html)//1024} KB)")


if __name__ == '__main__':
    main()
