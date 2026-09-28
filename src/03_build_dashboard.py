#!/usr/bin/env python3
"""03_build_dashboard.py — 生成交互式 BI 看板(单文件 HTML,离线可打开).

特性:
  - ECharts 库内嵌(无外链,断网可看,可直接发给别人)
  - 四个页签:概览 / 时间规律 / 站点与流向 / 用户与车型
  - 全局筛选:月份(全年/1-12月) × 用户类型(全部/会员/散客)联动大部分图表
  - 数据口径:站点/流向视图为全年汇总,其余图表随筛选联动

用法:
    python 03_build_dashboard.py --data-root ./warehouse --out dashboard/index.html
"""
import argparse
import glob
import json
import os
import re
import sys

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Divvy 共享单车时空分析看板 · 芝加哥 __YEAR__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#F5F7FA;color:#1F2937}
header{background:linear-gradient(120deg,#0F2B5B,#1D4ED8);color:#fff;padding:18px 24px}
header h1{font-size:20px;font-weight:600}
header p{font-size:12px;opacity:.8;margin-top:4px}
.bar{background:#fff;padding:10px 24px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;border-bottom:1px solid #E5E7EB}
.fgroup{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.fgroup b{font-size:12px;color:#6B7280;font-weight:500}
.chip{border:1px solid #D1D5DB;background:#fff;color:#374151;border-radius:999px;padding:3px 12px;font-size:12px;cursor:pointer}
.chip.active{background:#1D4ED8;border-color:#1D4ED8;color:#fff}
nav{display:flex;gap:2px;background:#fff;padding:0 24px;border-bottom:1px solid #E5E7EB;flex-wrap:wrap}
nav button{border:none;background:none;padding:11px 16px;font-size:14px;cursor:pointer;color:#6B7280;border-bottom:2px solid transparent}
nav button.active{color:#1D4ED8;border-bottom-color:#1D4ED8;font-weight:600}
main{padding:18px 24px;max-width:1440px}
section{display:none}
section.show{display:block}
.grid{display:grid;gap:16px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.two{grid-template-columns:repeat(auto-fit,minmax(420px,1fr))}
.card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(15,43,91,.08)}
.card h3{font-size:15px;font-weight:600}
.card p.sub{font-size:12px;color:#6B7280;margin:2px 0 6px}
.kpi .v{font-size:24px;font-weight:700;color:#0F2B5B;margin-top:6px}
.kpi .k{font-size:12px;color:#6B7280}
.kpi .n{font-size:11px;color:#9CA3AF;margin-top:2px}
.chart{width:100%;height:320px}
.chart.tall{height:460px}
footer{padding:16px 24px 28px;font-size:11px;color:#9CA3AF;max-width:1440px;line-height:1.7}
@media (max-width:720px){main,footer,.bar,nav{padding-left:12px;padding-right:12px}.two{grid-template-columns:1fr}.chart{height:280px}}
</style>
</head>
<body>
<header>
<h1>Divvy 共享单车时空分析看板 · 芝加哥 __YEAR__</h1>
<p>数据:Divvy 官方开放数据(全年真实骑行记录)| 管道:Python · PySpark 分层处理 | 可视化:ECharts | 生成日期:__DATE__</p>
</header>

<div class="bar">
<div class="fgroup"><b>月份</b><span id="monthChips"></span></div>
<div class="fgroup"><b>用户类型</b>
<button class="chip active" data-member="all">全部</button>
<button class="chip" data-member="member">会员</button>
<button class="chip" data-member="casual">散客</button>
</div>
<span style="font-size:12px;color:#9CA3AF;margin-left:auto" id="scopeNote"></span>
</div>

<nav>
<button data-tab="overview" class="active">概览</button>
<button data-tab="time">时间规律</button>
<button data-tab="station">站点与流向</button>
<button data-tab="user">用户与车型</button>
</nav>

<main>
<section id="tab-overview" class="show">
<div class="grid kpis" id="kpiCards"></div>
<div class="grid two" style="margin-top:16px">
<div class="card"><h3>月度骑行量与会员结构</h3><p class="sub">柱:会员/散客堆叠(受用户类型筛选)· 折线:电助力车占比</p><div id="cMonthly" class="chart"></div></div>
<div class="card"><h3>日骑行量走势</h3><p class="sub">蓝:工作日 · 橙:周末(受用户类型筛选)</p><div id="cDaily" class="chart"></div></div>
</div>
</section>

<section id="tab-time">
<div class="grid two">
<div class="card"><h3>星期 × 小时 骑行热力</h3><p class="sub">颜色越深骑行量越大 · 通勤双峰清晰可见</p><div id="cHeat" class="chart"></div></div>
<div class="card"><h3>分时骑行曲线:会员 vs 散客</h3><p class="sub">工作日与周末分别成线 · 反映通勤与休闲两种模式</p><div id="cHour" class="chart"></div></div>
<div class="card"><h3>骑行时长分布</h3><p class="sub">会员/散客对比 · 分钟区间的骑行次数</p><div id="cDur" class="chart"></div></div>
<div class="card"><h3>分时平均骑行时长</h3><p class="sub">凌晨与午间时长偏长,通勤时段偏短</p><div id="cHourAvg" class="chart"></div></div>
</div>
</section>

<section id="tab-station">
<div class="grid two">
<div class="card"><h3>起骑量 Top 15 站点</h3><p class="sub">全年汇总 · 受用户类型筛选</p><div id="cTopSt" class="chart"></div></div>
<div class="card"><h3>净流入 / 净流出 Top 站点</h3><p class="sub">还车量-起骑量 · 潮汐调度优先站点</p><div id="cNet" class="chart"></div></div>
</div>
<div class="card" style="margin-top:16px"><h3>站点分布与 Top OD 流向</h3><p class="sub">气泡大小=起骑量 · 颜色=净流入(红) / 净流出(蓝) · 曲线=最热 __ODN__ 条骑行走廊(全年)</p><div id="cMap" class="chart tall"></div></div>
</section>

<section id="tab-user">
<div class="grid two">
<div class="card"><h3>会员 × 车型 月度结构</h3><p class="sub">四段堆叠:会员/散客 × 经典车/电助力车</p><div id="cMemBike" class="chart"></div></div>
<div class="card"><h3>平均骑行时长对比</h3><p class="sub">按用户类型 × 车型(受月份筛选)</p><div id="cAvgGrid" class="chart"></div></div>
</div>
<div class="card" style="margin-top:16px"><h3>业务洞察卡</h3><div id="insight" style="font-size:13px;line-height:2;color:#374151;padding:6px 2px"></div></div>
</section>
</main>

<footer>
口径说明:总骑行量/平均时长等 KPI 与时间规律类图表随顶部「月份 + 用户类型」筛选联动;站点与流向视图为全年汇总(用户类型筛选生效)。<br>
数据处理:PySpark 完成清洗(时长 0~24h、去重、字段补全)与指标聚合;站点坐标取该站全年骑行记录均值;净流入=还车量-起骑量。<br>
数据来源:divvy-tripdata.s3.amazonaws.com(芝加哥市 / Divvy 官方开放数据)。本看板为单文件离线 HTML,可直接双击打开。
</footer>

<script>__ECHARTS__</script>
<script>
var DATA = __DATA__;
var state = { month: 0, member: 'all' };
var charts = {};
var CBLUE = '#1D4ED8', CAMBER = '#F59E0B', CGREEN = '#059669', CPURPLE = '#7C3AED';

function fmtW(n){ return n >= 10000 ? (n/10000).toFixed(1) + ' 万' : String(Math.round(n)); }
function el(id){ return document.getElementById(id); }
function mk(id){ var c = echarts.init(el(id)); charts[id] = c; return c; }

function cubeRows(override){
  var m = override ? override.month : state.month, u = override ? override.member : state.member;
  return DATA.cube.filter(function(r){
    return (m === 0 || r.month === m) && (u === 'all' || r.member === u);
  });
}
function aggHour(rows, weekend){
  var a = new Array(24).fill(0);
  rows.forEach(function(r){
    var wk = (r.dow >= 6);
    if (weekend === undefined || wk === weekend) a[r.hour] += r.n;
  });
  return a;
}
function aggMonthBy(rows, key){
  var map = {};
  rows.forEach(function(r){ map[r[key]] = (map[r[key]] || 0) + r.n; });
  return map;
}

/* ---------- 筛选条 ---------- */
(function(){
  var html = '<button class="chip active" data-month="0">全年</button>';
  for (var i = 1; i <= 12; i++) html += '<button class="chip" data-month="' + i + '">' + i + '月</button>';
  el('monthChips').innerHTML = html;
})();
document.querySelectorAll('.chip').forEach(function(btn){
  btn.addEventListener('click', function(){
    var p = btn.parentNode;
    p.querySelectorAll('.chip').forEach(function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
    if (btn.dataset.month !== undefined) state.month = +btn.dataset.month;
    if (btn.dataset.member !== undefined) state.member = btn.dataset.member;
    render();
  });
});

/* ---------- 页签 ---------- */
document.querySelectorAll('nav button').forEach(function(btn){
  btn.addEventListener('click', function(){
    document.querySelectorAll('nav button').forEach(function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
    document.querySelectorAll('section').forEach(function(s){ s.classList.remove('show'); });
    el('tab-' + btn.dataset.tab).classList.add('show');
    Object.values(charts).forEach(function(c){ c.resize(); });
    fixMapAspect();
  });
});

/* ---------- 概览 KPI ---------- */
function renderKpi(){
  var rows = cubeRows();
  var n = 0, s = 0, nMem = 0, nElec = 0;
  rows.forEach(function(r){ n += r.n; s += r.sum_min; if (r.member === 'member') nMem += r.n; if (r.bike === 'electric_bike') nElec += r.n; });
  var rowsAllMem = cubeRows({ month: state.month, member: 'all' });
  var nAll = 0, nAllMem = 0;
  rowsAllMem.forEach(function(r){ nAll += r.n; if (r.member === 'member') nAllMem += r.n; });
  var k = DATA.kpi[0] || {};
  var daily = DATA.daily;
  var nDays = 0, sumD = 0;
  daily.forEach(function(d){ if (state.month === 0 || +d.date.slice(5,7) === state.month){ nDays++; sumD += (state.member === 'all' ? d.n : (state.member === 'member' ? d.n_member : d.n_casual)); } });
  var cards = [
    ['总骑行量', fmtW(n), '受月份+用户筛选'],
    ['会员占比', nAll ? (100 * nAllMem / nAll).toFixed(1) + '%' : '-', '受月份筛选'],
    ['平均骑行时长', n ? (s / n).toFixed(1) + ' 分钟' : '-', '受月份+用户筛选'],
    ['中位骑行时长(全年)', k.p50_min + ' 分钟', '全年口径'],
    ['电助力车占比', nAll ? (100 * nElec / nAll).toFixed(1) + '%' : '-', '受月份筛选'],
    ['日均骑行量', nDays ? fmtW(Math.round(sumD / nDays)) : '-', '受月份+用户筛选'],
    ['活跃站点(全年)', fmtW(k.active_stations), '有起骑记录的站点'],
    ['峰值单日(全年)', k.peak_day_rides.toLocaleString() + ' 次', k.peak_date]
  ];
  var html = '';
  cards.forEach(function(c){
    html += '<div class="card kpi"><div class="k">' + c[0] + '</div><div class="v">' + c[1] + '</div><div class="n">' + c[2] + '</div></div>';
  });
  el('kpiCards').innerHTML = html;
}

/* ---------- 月度柱+折线 ---------- */
function renderMonthly(){
  var rows = cubeRows();
  var byM = {}, elecM = {}, totM = {};
  for (var m = 1; m <= 12; m++){ byM[m] = { member: 0, casual: 0 }; elecM[m] = 0; totM[m] = 0; }
  rows.forEach(function(r){
    byM[r.month][r.member] += r.n; totM[r.month] += r.n;
    if (r.bike === 'electric_bike') elecM[r.month] += r.n;
  });
  var mem = [], cas = [], share = [];
  for (var m = 1; m <= 12; m++){
    mem.push(byM[m].member); cas.push(byM[m].casual);
    share.push(totM[m] ? +(100 * elecM[m] / totM[m]).toFixed(1) : 0);
  }
  var series = [];
  if (state.member !== 'casual') series.push({ name: '会员', type: 'bar', stack: 'u', data: mem, itemStyle: { color: CBLUE } });
  if (state.member !== 'member') series.push({ name: '散客', type: 'bar', stack: 'u', data: cas, itemStyle: { color: CAMBER } });
  series.push({ name: '电助力占比', type: 'line', yAxisIndex: 1, data: share, itemStyle: { color: CPURPLE }, smooth: true });
  var ch = charts['cMonthly'] || mk('cMonthly');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 50, right: 50, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: MONTHS, axisLabel: { interval: 0 } },
    yAxis: [{ type: 'value', name: '骑行量' }, { type: 'value', name: '%', max: 100 }],
    series: series
  }, true);
}
var MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

/* ---------- 日走势 ---------- */
function renderDaily(){
  var daily = DATA.daily;
  var dates = daily.map(function(d){ return d.date; });
  function col(d){ return state.member === 'all' ? d.n : (state.member === 'member' ? d.n_member : d.n_casual); }
  var wk = daily.map(function(d){ return d.day_type === '工作日' ? col(d) : null; });
  var we = daily.map(function(d){ return d.day_type !== '工作日' ? col(d) : null; });
  var ch = charts['cDaily'] || mk('cDaily');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 50, right: 20, top: 34, bottom: 46 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16 }],
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: '次/日' },
    series: [
      { name: '工作日', type: 'line', data: wk, showSymbol: false, lineStyle: { width: 1.4, color: CBLUE }, itemStyle: { color: CBLUE } },
      { name: '周末', type: 'line', data: we, showSymbol: false, lineStyle: { width: 1.4, color: CAMBER }, itemStyle: { color: CAMBER } }
    ]
  }, true);
}

/* ---------- 热力图 ---------- */
var DOW = ['周一','周二','周三','周四','周五','周六','周日'];
function renderHeat(){
  var rows = cubeRows();
  var map = {};
  rows.forEach(function(r){ var k = r.dow * 100 + r.hour; map[k] = (map[k] || 0) + r.n; });
  var data = [];
  for (var d = 1; d <= 7; d++) for (var h = 0; h < 24; h++) data.push([h, d - 1, map[d * 100 + h] || 0]);
  var maxv = Math.max.apply(null, data.map(function(d){ return d[2]; }));
  var ch = charts['cHeat'] || mk('cHeat');
  ch.setOption({
    tooltip: { formatter: function(p){ return DOW[p.value[1]] + ' ' + p.value[0] + ' 时: ' + p.value[2].toLocaleString() + ' 次'; } },
    grid: { left: 46, right: 16, top: 12, bottom: 60 },
    xAxis: { type: 'category', data: HOURS, splitArea: { show: true } },
    yAxis: { type: 'category', data: DOW, splitArea: { show: true } },
    visualMap: { min: 0, max: maxv, calculable: true, orient: 'horizontal', left: 'center', bottom: 4, inRange: { color: ['#EFF6FF', '#BFDBFE', '#60A5FA', '#1D4ED8', '#1E3A8A'] } },
    series: [{ type: 'heatmap', data: data, label: { show: false } }]
  }, true);
}
var HOURS = []; for (var hh = 0; hh < 24; hh++) HOURS.push(hh + '时');

/* ---------- 分时曲线 ---------- */
function renderHour(){
  var rowsAll = cubeRows({ month: state.month, member: 'all' });
  var rowsMem = rowsAll.filter(function(r){ return r.member === 'member'; });
  var rowsCas = rowsAll.filter(function(r){ return r.member === 'casual'; });
  var series = [];
  function line(name, rows, weekend, color){
    return { name: name, type: 'line', smooth: true, data: aggHour(rows, weekend), itemStyle: { color: color }, lineStyle: { width: 2 } };
  }
  if (state.member !== 'casual'){
    series.push(line('会员·工作日', rowsMem, false, CBLUE));
    series.push(line('会员·周末', rowsMem, true, '#93C5FD'));
  }
  if (state.member !== 'member'){
    series.push(line('散客·工作日', rowsCas, false, CAMBER));
    series.push(line('散客·周末', rowsCas, true, '#FCD34D'));
  }
  var ch = charts['cHour'] || mk('cHour');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 46, right: 16, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: HOURS },
    yAxis: { type: 'value', name: '次' },
    series: series
  }, true);
}

/* ---------- 时长分布 ---------- */
var BUCKETS = DATA.dur_hist.map(function(d){ return d.bucket; }).filter(function(v, i, a){ return a.indexOf(v) === i; });
function renderDur(){
  var rows = DATA.dur_hist.filter(function(r){
    return (state.month === 0 || r.month === state.month) && (state.member === 'all' || r.member === state.member);
  });
  var mem = BUCKETS.map(function(b){ var s = 0; rows.forEach(function(r){ if (r.bucket === b && r.member === 'member') s += r.n; }); return s; });
  var cas = BUCKETS.map(function(b){ var s = 0; rows.forEach(function(r){ if (r.bucket === b && r.member === 'casual') s += r.n; }); return s; });
  var series = [];
  if (state.member !== 'casual') series.push({ name: '会员', type: 'bar', data: mem, itemStyle: { color: CBLUE } });
  if (state.member !== 'member') series.push({ name: '散客', type: 'bar', data: cas, itemStyle: { color: CAMBER } });
  var ch = charts['cDur'] || mk('cDur');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 60, right: 16, top: 34, bottom: 40 },
    xAxis: { type: 'category', data: BUCKETS, name: '分钟' },
    yAxis: { type: 'value', name: '次' },
    series: series
  }, true);
}

/* ---------- 分时均长 ---------- */
function renderHourAvg(){
  var rows = cubeRows();
  var n = new Array(24).fill(0), s = new Array(24).fill(0);
  rows.forEach(function(r){ n[r.hour] += r.n; s[r.hour] += r.sum_min; });
  var avg = HOURS.map(function(_, i){ return n[i] ? +(s[i] / n[i]).toFixed(1) : 0; });
  var ch = charts['cHourAvg'] || mk('cHourAvg');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 46, right: 16, top: 20, bottom: 28 },
    xAxis: { type: 'category', data: HOURS },
    yAxis: { type: 'value', name: '分钟' },
    series: [{ type: 'line', smooth: true, data: avg, areaStyle: { opacity: .12 }, itemStyle: { color: CGREEN } }]
  }, true);
}

/* ---------- 站点类 ---------- */
function stationVal(st){
  if (state.member === 'member') return st.starts_member;
  if (state.member === 'casual') return st.starts - st.starts_member;
  return st.starts;
}
function renderTopSt(){
  var st = DATA.stations.slice().sort(function(a, b){ return stationVal(b) - stationVal(a); }).slice(0, 15).reverse();
  var ch = charts['cTopSt'] || mk('cTopSt');
  ch.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 170, right: 30, top: 10, bottom: 24 },
    xAxis: { type: 'value', name: '次' },
    yAxis: { type: 'category', data: st.map(function(s){ return s.name; }), axisLabel: { width: 160, overflow: 'truncate' } },
    series: [{ type: 'bar', data: st.map(function(s){ return stationVal(s); }), itemStyle: { color: CBLUE }, barMaxWidth: 16 }]
  }, true);
}
function renderNet(){
  var st = DATA.stations.slice();
  st.forEach(function(s){ s.nv = netVal(s); });
  var top = st.sort(function(a, b){ return b.nv - a.nv; }).slice(0, 6);
  var bot = st.slice().sort(function(a, b){ return a.nv - b.nv; }).slice(0, 6);
  var all = top.concat(bot).sort(function(a, b){ return a.nv - b.nv; });
  var ch = charts['cNet'] || mk('cNet');
  ch.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 170, right: 30, top: 10, bottom: 24 },
    xAxis: { type: 'value', name: '净流入' },
    yAxis: { type: 'category', data: all.map(function(s){ return s.name; }), axisLabel: { width: 160, overflow: 'truncate' } },
    series: [{ type: 'bar', data: all.map(function(s){ return { value: s.nv, itemStyle: { color: s.nv >= 0 ? '#DC2626' : CBLUE } }; }), barMaxWidth: 14 }]
  }, true);
}
function netVal(s){
  if (state.member === 'member') return (s.ends_member || 0) - s.starts_member;
  if (state.member === 'casual') return (s.ends - (s.ends_member || 0)) - (s.starts - s.starts_member);
  return s.net;
}
function renderMap(){
  var st = DATA.stations;
  var scatter = st.map(function(s){
    return { value: [s.lng, s.lat, stationVal(s), netVal(s)], name: s.name };
  });
  var netMax = 1;
  st.forEach(function(s){ var v = Math.abs(netVal(s)); if (v > netMax) netMax = v; });
  var odn = Math.min(60, DATA.od.length);
  var pairs = DATA.od.slice(0, odn).map(function(o){
    var v = state.member === 'member' ? o.n_member : (state.member === 'casual' ? o.n - o.n_member : o.n);
    return { coords: [[o.s_lng, o.s_lat], [o.e_lng, o.e_lat]], lineStyle: { width: Math.max(1, Math.log2(v) - 3), opacity: .45, color: '#0F2B5B', curveness: .18 } };
  });
  var ch = charts['cMap'] || mk('cMap');
  ch.setOption({
    tooltip: { formatter: function(p){
      if (p.seriesType === 'scatter') return p.name + '<br>起骑 ' + p.value[2].toLocaleString() + ' 次 · 净流入 ' + p.value[3].toLocaleString();
      return 'OD 走廊';
    } },
    grid: { left: 20, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'value', min: MAPX[0], max: MAPX[1], axisLabel: { show: false }, splitLine: { show: false } },
    yAxis: { type: 'value', min: MAPY[0], max: MAPY[1], axisLabel: { show: false }, splitLine: { show: false } },
    visualMap: { show: false, dimension: 3, min: -netMax, max: netMax, inRange: { color: ['#1D4ED8', '#9CA3AF', '#DC2626'] } },
    series: [
      { type: 'scatter', data: scatter, symbolSize: function(v){ return Math.sqrt(v[2]) / 3; }, itemStyle: { opacity: .75, borderColor: '#fff', borderWidth: .5 } },
      { type: 'lines', coordinateSystem: 'cartesian2d', data: pairs, polyline: false, effect: { show: false } }
    ]
  }, true);
}
var MAPX = [0, 0], MAPY = [0, 0];
(function(){
  var xs = DATA.stations.map(function(s){ return s.lng; }), ys = DATA.stations.map(function(s){ return s.lat; });
  MAPX = [Math.min.apply(null, xs) - .01, Math.max.apply(null, xs) + .01];
  MAPY = [Math.min.apply(null, ys) - .01, Math.max.apply(null, ys) + .01];
})();
function fixMapAspect(){
  var c = charts['cMap']; if (!c) return;
  var w = el('cMap').clientWidth || 900, h = el('cMap').clientHeight || 460;
  var xSpan = MAPX[1] - MAPX[0], ySpan0 = MAPY[1] - MAPY[0];
  var ySpan = xSpan * (h - 60) / (w - 40);
  if (ySpan < ySpan0) ySpan = ySpan0;
  var cy = (MAPY[0] + MAPY[1]) / 2;
  c.setOption({ yAxis: { min: cy - ySpan / 2, max: cy + ySpan / 2 } });
}

/* ---------- 用户与车型 ---------- */
function renderMemBike(){
  var rows = cubeRows({ month: 0, member: 'all' });
  var keys = [['member', 'classic_bike', '会员·经典车', CBLUE], ['member', 'electric_bike', '会员·电助力', '#93C5FD'],
              ['casual', 'classic_bike', '散客·经典车', CAMBER], ['casual', 'electric_bike', '散客·电助力', '#FCD34D']];
  var series = keys.map(function(k){
    var data = new Array(12).fill(0);
    rows.forEach(function(r){ if (r.member === k[0] && r.bike === k[1] && (state.month === 0 || r.month === state.month)) data[r.month - 1] += r.n; });
    return { name: k[2], type: 'bar', stack: 'g', data: data, itemStyle: { color: k[3] } };
  });
  var ch = charts['cMemBike'] || mk('cMemBike');
  ch.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 60, right: 20, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: MONTHS },
    yAxis: { type: 'value', name: '次' },
    series: series
  }, true);
}
function renderAvgGrid(){
  var rows = cubeRows({ month: state.month, member: 'all' });
  var agg = {};
  rows.forEach(function(r){ var k = r.member + '|' + r.bike; agg[k] = agg[k] || [0, 0]; agg[k][0] += r.n; agg[k][1] += r.sum_min; });
  var cats = [], vals = [];
  [['member|classic_bike', '会员·经典车'], ['member|electric_bike', '会员·电助力'],
   ['casual|classic_bike', '散客·经典车'], ['casual|electric_bike', '散客·电助力']].forEach(function(p){
    var a = agg[p[0]] || [0, 0];
    cats.push(p[1]); vals.push(a[0] ? +(a[1] / a[0]).toFixed(1) : 0);
  });
  var ch = charts['cAvgGrid'] || mk('cAvgGrid');
  ch.setOption({
    tooltip: {},
    grid: { left: 60, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: cats, axisLabel: { interval: 0, rotate: 16 } },
    yAxis: { type: 'value', name: '分钟' },
    series: [{ type: 'bar', data: vals, barMaxWidth: 46, itemStyle: { color: function(p){ return cats[p.dataIndex].indexOf('会员') === 0 ? CBLUE : CAMBER; } }, label: { show: true, position: 'top' } }]
  }, true);
}
function renderInsight(){
  var k = DATA.kpi[0] || {};
  var share = 100 * k.n_member / (k.n_member + k.n_casual);
  el('insight').innerHTML =
    '全年 <b>' + k.n_rides.toLocaleString() + '</b> 次骑行中,会员占 <b>' + share.toFixed(1) + '%</b>,电助力车占 <b>' + (100 * k.n_electric / k.n_rides).toFixed(1) + '%</b>。' +
    '散客平均骑行时长显著长于会员(见左下与"时间规律"页签),符合"会员通勤高频短途、散客休闲低频长途"的结构;' +
    '电助力车存在 <b>' + k.electric_offstation_pct + '%</b> 的站外还车,直接推高调度成本。' +
    '运营建议:通勤走廊重点保障经典车供给,热门 OD 走廊按潮汐方向补车;对高频散客站点投放会员转化权益。';
}

/* ---------- 总渲染 ---------- */
function render(){
  el('scopeNote').textContent = '当前口径:' + (state.month === 0 ? '全年' : state.month + '月') + ' · ' + (state.member === 'all' ? '全部用户' : (state.member === 'member' ? '仅会员' : '仅散客'));
  renderKpi(); renderMonthly(); renderDaily(); renderHeat(); renderHour();
  renderDur(); renderHourAvg(); renderTopSt(); renderNet(); renderMap();
  renderMemBike(); renderAvgGrid(); renderInsight();
  fixMapAspect();
}
window.addEventListener('resize', function(){
  Object.values(charts).forEach(function(c){ c.resize(); });
  fixMapAspect();
});
render();
</script>
</body>
</html>
"""


def find_echarts() -> str:
    """优先用本地缓存,其次 pyecharts 内置库."""
    candidates = [
        os.path.join("tmp", "echarts.min.js"),
        os.path.join(".venv", "lib", "python3.12", "site-packages", "pyecharts", "assets", "echarts.min.js"),
    ]
    candidates += glob.glob(os.path.join(".venv", "lib", "python*",
                                         "site-packages", "pyecharts", "assets", "echarts.min.js"))
    for path in candidates:
        if os.path.isfile(path) and os.path.getsize(path) > 500_000:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    sys.exit("[error] 找不到 echarts.min.js(先 pip install pyecharts 或放到 tmp/echarts.min.js)")


def load_json(path):
    if not os.path.exists(path):
        sys.exit(f"[error] 缺少 {path},请先运行 02_build_metrics.py")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="warehouse")
    ap.add_argument("--out", default="dashboard/index.html")
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()

    ads = os.path.join(args.data_root, "ads")
    data = {
        "kpi": load_json(os.path.join(ads, "kpi.json")),
        "cube": load_json(os.path.join(ads, "cube.json")),
        "daily": load_json(os.path.join(ads, "daily.json")),
        "dur_hist": load_json(os.path.join(ads, "dur_hist.json")),
        "stations": load_json(os.path.join(ads, "stations.json")),
        "od": load_json(os.path.join(ads, "od.json")),
    }
    od_n = min(60, len(data["od"]))
    html = (TEMPLATE
            .replace("__YEAR__", str(args.year))
            .replace("__DATE__", "2026-09-27")
            .replace("__ODN__", str(od_n)))
    html = re.sub(r"__DATA__", lambda m: json.dumps(data, ensure_ascii=False, separators=(",", ":")), html)
    html = re.sub(r"__ECHARTS__", lambda m: find_echarts(), html)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"看板已生成: {args.out} ({os.path.getsize(args.out) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
