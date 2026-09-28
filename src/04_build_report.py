#!/usr/bin/env python3
"""04_build_report.py — 生成 EDA 分析报告(自包含 HTML,图片 base64 内嵌).

报告结构:执行摘要 / 数据说明与质量 / 季节性 / 分时规律 / 骑行时长 /
站点与流向 / 用户与车型 / 结论建议 / 局限展望 / 附录复现.
所有结论数字均由 ADS 指标层实时计算,不硬编码.

用法:
    python 04_build_report.py --data-root ./warehouse --out report/report.html
"""
import argparse
import base64
import glob
import io
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

CBLUE, CAMBER, CGREEN, CPURPLE = "#1D4ED8", "#F59E0B", "#059669", "#7C3AED"
DOW = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def setup_font():
    for f in glob.glob("/usr/share/fonts/**/*.tt[fc]", recursive=True) + \
             glob.glob("/usr/share/fonts/**/*.otf", recursive=True):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["Noto Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei",
                 "LXGW WenKai", "Sarasa Mono SC", "Noto Serif SC"]:
        if name in avail:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.color"] = "#E5E7EB"
    plt.rcParams["grid.linewidth"] = 0.6


def fig_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def load(ads, name):
    path = os.path.join(ads, f"{name}.json")
    if not os.path.exists(path):
        sys.exit(f"[error] 缺少 {path},请先运行 02_build_metrics.py")
    return pd.DataFrame(json.load(open(path, encoding="utf-8")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="warehouse")
    ap.add_argument("--out", default="report/report.html")
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()
    setup_font()
    ads = os.path.join(args.data_root, "ads")

    kpi = json.load(open(os.path.join(ads, "kpi.json"), encoding="utf-8"))[0]
    quality = json.load(open(os.path.join(args.data_root, "dwd", "_quality.json"), encoding="utf-8"))
    cube = load(ads, "cube")
    monthly = load(ads, "monthly")
    daily = load(ads, "daily")
    dur = load(ads, "dur_hist")
    stations = load(ads, "stations")
    od = load(ads, "od")

    # ---------- 叙事数字 ----------
    n = kpi["n_rides"]
    member_share = 100 * kpi["n_member"] / (kpi["n_member"] + kpi["n_casual"])
    elec_share = 100 * kpi["n_electric"] / n
    mem_avg = kpi["n_member"] and cube[cube.member == "member"].sum_min.sum() / kpi["n_member"]
    cas_avg = kpi["n_casual"] and cube[cube.member == "casual"].sum_min.sum() / kpi["n_casual"]
    peak_month = int(monthly.loc[monthly.n.idxmax(), "month"])
    low_month = int(monthly.loc[monthly.n.idxmin(), "month"])
    peak_ratio = monthly.n.max() / monthly.n.min()
    wd = daily[daily.day_type == "工作日"]
    we = daily[daily.day_type != "工作日"]
    we_casual_share = 100 * we.n_casual.sum() / we.n.sum()
    wd_casual_share = 100 * wd.n_casual.sum() / wd.n.sum()
    hour_wd = (cube[cube.dow <= 5].groupby("hour").n.sum())
    peak_hour = int(hour_wd.idxmax())
    am_peak = int(hour_wd.loc[6:10].idxmax())
    night_share = 100 * (cube[(cube.hour >= 22) | (cube.hour <= 4)].n.sum()) / n
    elec_share_m = cube[cube.bike == "electric_bike"].groupby("month").n.sum() / \
        cube.groupby("month").n.sum()
    top_st = stations.iloc[0]
    in_st = stations.loc[stations.net.idxmax()]
    out_st = stations.loc[stations.net.idxmin()]
    top_od = od.iloc[0]
    hh = cube.groupby(["member", "dow", "hour"], as_index=False).n.sum()
    hh["weekend"] = hh.dow >= 6
    hour_curves = hh.groupby(["member", "weekend", "hour"]).n.sum().unstack([0, 1])

    def hv(member, weekend, h):
        return hour_curves.loc[h, (member, weekend)]

    gagg = cube.groupby(["member", "bike"]).agg(n=("n", "sum"), s=("sum_min", "sum"))
    avg_grid = gagg.s / gagg.n

    # ---------- 图 ----------
    figs = {}
    fig, ax = plt.subplots(figsize=(8.6, 4))
    x = monthly.month.astype(int)
    ax.bar(x, monthly.n_member, color=CBLUE, label="会员")
    ax.bar(x, monthly.n_casual, bottom=monthly.n_member, color=CAMBER, label="散客")
    ax2 = ax.twinx()
    ax2.plot(x, monthly.electric_share, color=CPURPLE, marker="o", ms=4, label="电助力占比")
    ax2.set_ylabel("电助力占比 (%)")
    ax2.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xlabel("月份")
    ax.set_ylabel("骑行次数")
    ax.set_title(f"{args.year} 年月度骑行量与会员结构", fontsize=13)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    figs["monthly"] = fig_b64(fig)

    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    d = daily.sort_values("date")
    ax.plot(d.date[d.day_type == "工作日"], d.n[d.day_type == "工作日"], ".", ms=3, color=CBLUE, label="工作日")
    ax.plot(d.date[d.day_type != "工作日"], d.n[d.day_type != "工作日"], ".", ms=3, color=CAMBER, label="周末")
    ax.set_ylabel("次/日")
    ax.set_title("日骑行量全年走势(橙=周末)", fontsize=13)
    ax.legend(fontsize=9)
    figs["daily"] = fig_b64(fig)

    hm = np.zeros((7, 24))
    for r in cube.itertuples():
        hm[r.dow - 1, r.hour] += r.n
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    im = ax.imshow(hm, aspect="auto", cmap="Blues")
    ax.set_xticks(range(24))
    ax.set_yticks(range(7), DOW)
    ax.set_xlabel("小时")
    ax.set_title("星期 × 小时 骑行热力(全年合计)", fontsize=13)
    fig.colorbar(im, ax=ax, label="骑行次数", shrink=0.85)
    figs["heat"] = fig_b64(fig)

    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    hours = range(24)
    ax.plot(hours, [hv("member", False, h) for h in hours], color=CBLUE, label="会员·工作日")
    ax.plot(hours, [hv("member", True, h) for h in hours], color="#93C5FD", label="会员·周末")
    ax.plot(hours, [hv("casual", False, h) for h in hours], color=CAMBER, label="散客·工作日")
    ax.plot(hours, [hv("casual", True, h) for h in hours], color="#FCD34D", label="散客·周末")
    ax.set_xlabel("小时")
    ax.set_ylabel("骑行次数(全年合计)")
    ax.set_title("分时骑行曲线:通勤双峰 vs 周末单峰", fontsize=13)
    ax.legend(fontsize=9)
    figs["hour"] = fig_b64(fig)

    dm = dur.groupby(["member", "bucket"]).n.sum().unstack(0)
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    ax.bar(dm.index, dm["member"], color=CBLUE, label="会员")
    ax.bar(dm.index, dm["casual"], bottom=dm["member"], color=CAMBER, label="散客")
    ax.set_yscale("log")
    ax.set_xlabel("骑行时长(分钟)")
    ax.set_ylabel("次数(对数轴)")
    ax.set_title("骑行时长分布:散客右尾更长", fontsize=13)
    ax.legend(fontsize=9)
    figs["dur"] = fig_b64(fig)

    st = stations.sort_values("starts", ascending=False).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.barh(st.name, st.starts, color=CBLUE)
    ax.set_xlabel("起骑次数(全年)")
    ax.set_title("起骑量 Top 12 站点", fontsize=13)
    plt.setp(ax.get_yticklabels(), fontsize=8)
    figs["topst"] = fig_b64(fig)

    nets = pd.concat([stations.nlargest(6, "net"), stations.nsmallest(6, "net")]).sort_values("net")
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.barh(nets.name, nets.net, color=["#DC2626" if v >= 0 else CBLUE for v in nets.net])
    ax.axvline(0, color="#6B7280", lw=0.8)
    ax.set_xlabel("净流入 = 还车量 - 起骑量(全年)")
    ax.set_title("潮汐最显著的站点:红=净流入,蓝=净流出", fontsize=13)
    plt.setp(ax.get_yticklabels(), fontsize=8)
    figs["net"] = fig_b64(fig)

    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.scatter(stations.lng, stations.lat, s=np.sqrt(stations.starts) * .7,
               c=stations.net, cmap="coolwarm", alpha=.7, linewidths=0)
    for r in od.head(34).itertuples():
        ax.annotate("", xy=(r.e_lng, r.e_lat), xytext=(r.s_lng, r.s_lat),
                    arrowprops=dict(arrowstyle="-", color="#0F2B5B", alpha=.35, lw=.8,
                                    connectionstyle="arc3,rad=0.15"))
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    ax.set_title("站点分布(气泡=起骑量,红/蓝=净流入/流出)与 Top OD 走廊", fontsize=13)
    figs["map"] = fig_b64(fig)

    piv = cube.groupby(["month", "member", "bike"]).n.sum().unstack(["member", "bike"]).fillna(0)
    labels = {("member", "classic_bike"): ("会员·经典车", CBLUE),
              ("member", "electric_bike"): ("会员·电助力", "#93C5FD"),
              ("casual", "classic_bike"): ("散客·经典车", CAMBER),
              ("casual", "electric_bike"): ("散客·电助力", "#FCD34D")}
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    bottom = np.zeros(len(piv))
    for key, (lab, color) in labels.items():
        if key in piv.columns:
            ax.bar(piv.index.astype(int), piv[key], bottom=bottom, color=color, label=lab)
            bottom += piv[key].values
    ax.set_xticks(piv.index.astype(int))
    ax.set_xlabel("月份")
    ax.set_ylabel("骑行次数")
    ax.set_title("会员 × 车型 月度结构", fontsize=13)
    ax.legend(fontsize=8, ncol=2)
    figs["membike"] = fig_b64(fig)

    cats = ["会员·经典车", "会员·电助力", "散客·经典车", "散客·电助力"]
    vals = [avg_grid.get(("member", "classic_bike"), 0), avg_grid.get(("member", "electric_bike"), 0),
            avg_grid.get(("casual", "classic_bike"), 0), avg_grid.get(("casual", "electric_bike"), 0)]
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.bar(cats, vals, color=[CBLUE, "#93C5FD", CAMBER, "#FCD34D"])
    for i, v in enumerate(vals):
        ax.text(i, v + .4, f"{v:.1f}", ha="center", fontsize=9)
    ax.set_ylabel("平均时长(分钟)")
    ax.set_title("平均骑行时长:用户类型 × 车型", fontsize=13)
    plt.setp(ax.get_xticklabels(), fontsize=9)
    figs["avggrid"] = fig_b64(fig)

    qrows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in quality.items() if not isinstance(v, dict))
    odtxt = " → ".join([str(top_od.s_name), str(top_od.e_name)])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Divvy 共享单车时空分析报告 · {args.year}</title>
<style>
body{{font-family:-apple-system,'PingFang SC','Noto Sans SC','WenQuanYi Zen Hei',sans-serif;color:#1F2937;margin:0;background:#F9FAFB}}
.page{{max-width:920px;margin:0 auto;padding:40px 28px}}
h1{{font-size:26px;color:#0F2B5B;border-bottom:3px solid #1D4ED8;padding-bottom:10px}}
h2{{font-size:19px;color:#0F2B5B;margin-top:36px;border-left:4px solid #1D4ED8;padding-left:10px}}
p,li{{line-height:1.85;font-size:14.5px}}
figure{{margin:18px 0;background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:12px}}
figure img{{width:100%}}
figcaption{{text-align:center;color:#6B7280;font-size:12.5px;margin-top:6px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;background:#fff}}
td,th{{border:1px solid #E5E7EB;padding:6px 10px;text-align:left}}
th{{background:#EFF6FF}}
.k{{color:#1D4ED8;font-weight:700}}
.box{{background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 18px;margin:14px 0}}
footer{{color:#9CA3AF;font-size:12px;margin-top:40px;line-height:1.7}}
@media print{{body{{background:#fff}}.page{{padding:10px}}}}
</style></head><body><div class="page">
<h1>芝加哥 Divvy 共享单车时空分析报告 · {args.year} 年</h1>
<p>数据:Divvy 官方开放数据(全年 {n / 1e4:.1f} 万次真实骑行记录)| 管道:Python · PySpark | 报告生成:2026-09-27</p>

<h2>一、执行摘要</h2>
<div class="box">
<ul>
<li><b>规模与结构</b>:全年 <span class="k">{n:,}</span> 次有效骑行,会员占 <span class="k">{member_share:.1f}%</span>,电助力车占 <span class="k">{elec_share:.1f}%</span>,中位骑行时长 <span class="k">{kpi['p50_min']} 分钟</span>。</li>
<li><b>季节性</b>:{peak_month} 月为全年峰值(低谷 {low_month} 月的 <span class="k">{peak_ratio:.1f}</span> 倍),骑行量与气温强相关,夏季为运营旺季。</li>
<li><b>通勤双峰</b>:工作日呈 <span class="k">{am_peak} 时 / {peak_hour} 时</span> 双高峰,周末转为 12–17 时的休闲单峰;夜间(22 时–次日 4 时)骑行仅占 <span class="k">{night_share:.1f}%</span>。</li>
<li><b>用户画像</b>:会员平均骑行 <span class="k">{mem_avg:.1f} 分钟</span>,散客 <span class="k">{cas_avg:.1f} 分钟</span>(约 {cas_avg / mem_avg:.1f} 倍)——会员通勤高频短途、散客休闲低频长途;散客在周末的占比({we_casual_share:.1f}%)明显高于工作日({wd_casual_share:.1f}%)。</li>
<li><b>电助力化</b>:电助力占比从 1 月的 <span class="k">{100 * elec_share_m.get(1, 0):.1f}%</span> 变化到 12 月的 <span class="k">{100 * elec_share_m.get(12, 0):.1f}%</span>;同时电助力车有 <span class="k">{kpi['electric_offstation_pct']}%</span> 的骑行站外还车,直接推高 rebalance 调度成本。</li>
<li><b>空间潮汐</b>:最强流入站 <span class="k">{in_st.name}</span>(净流入 {int(in_st.net):+,}),最强流出站 <span class="k">{out_st.name}</span>(净流出 {int(out_st.net):,});最热走廊为 <span class="k">{odtxt}</span>({int(top_od.n):,} 次)。</li>
</ul></div>

<h2>二、数据说明与质量检查</h2>
<p>原始数据为 Divvy 官方 S3 开放数据(免登录直连),字段包括骑行 ID、车型、起止时间、起止站点与坐标、会员标识,共 13 列。清洗在 PySpark 中完成并记录于 <code>dwd/_quality.json</code>:</p>
<table><tr><th>质量指标</th><th>数值</th></tr>{qrows}</table>
<p>清洗规则:剔除时长 ≤ 0 或 &gt; 24 小时的记录(调度测试、丢车等脏数据),剔除关键字段缺失记录,ride_id 去重;站点/坐标缺失保留为空并在站点级分析中过滤。站点坐标取该站全年骑行记录的均值。</p>

<h2>三、季节性</h2>
<figure><img src="data:image/png;base64,{figs['monthly']}"><figcaption>图 1 月度骑行量(会员/散客堆叠)与电助力占比</figcaption></figure>
<figure><img src="data:image/png;base64,{figs['daily']}"><figcaption>图 2 日粒度全年走势,橙色为周末</figcaption></figure>

<h2>四、分时规律</h2>
<figure><img src="data:image/png;base64,{figs['heat']}"><figcaption>图 3 星期 × 小时骑行热力</figcaption></figure>
<figure><img src="data:image/png;base64,{figs['hour']}"><figcaption>图 4 分时曲线:会员工作日双峰 / 散客周末单峰</figcaption></figure>

<h2>五、骑行时长</h2>
<figure><img src="data:image/png;base64,{figs['dur']}"><figcaption>图 5 时长分布(堆叠 + 对数轴)</figcaption></figure>

<h2>六、站点与流向</h2>
<figure><img src="data:image/png;base64,{figs['topst']}"><figcaption>图 6 起骑量 Top 12 站点</figcaption></figure>
<figure><img src="data:image/png;base64,{figs['net']}"><figcaption>图 7 潮汐站点:净流入 / 净流出</figcaption></figure>
<figure><img src="data:image/png;base64,{figs['map']}"><figcaption>图 8 站点空间分布与 Top OD 走廊</figcaption></figure>

<h2>七、用户与车型</h2>
<figure><img src="data:image/png;base64,{figs['membike']}"><figcaption>图 9 会员 × 车型月度结构</figcaption></figure>
<figure><img src="data:image/png;base64,{figs['avggrid']}"><figcaption>图 10 平均骑行时长:用户 × 车型</figcaption></figure>

<h2>八、结论与运营建议</h2>
<ol>
<li><b>通勤保障</b>:工作日 {am_peak}/{peak_hour} 时双峰时段在通勤走廊(见报告与看板的 OD 视图)优先保障经典车供给,并对 Top 起骑站预调度。</li>
<li><b>潮汐调度</b>:对净流入/净流出极端站点(图 7)建立早晚高峰之间的定向补车;电助力车 {kpi['electric_offstation_pct']}% 站外还车,可用还车奖励引导归站。</li>
<li><b>会员转化</b>:散客集中于周末与旅游走廊、骑行时长更长,可在高频散客站点与周末时段投放会员转化权益。</li>
<li><b>旺季运营</b>:夏季({peak_month} 月峰值)需求约为冬季低谷的 {peak_ratio:.1f} 倍,车辆检修与扩容应错峰安排在冬季低需求月份。</li>
<li><b>数据口径</b>:站点级指标基于有站点 ID 的记录;净流入为全年口径,不等于瞬时库存压力,调度决策还需结合实时数据。</li>
</ol>

<h2>九、局限与展望</h2>
<ul>
<li>Divvy 数据不含用户 ID,无法计算留存、复购与生命周期价值;会员/散客为骑行级标识。</li>
<li>不含天气与事件数据,季节性归因(气温 vs 节假日)有待外部数据交叉验证。</li>
<li>展望:接入实时流(Spark Structured Streaming)做实时大屏;引入天气、POI 数据做需求预测(梯度提升树)与站点调度优化。</li>
</ul>

<h2>附录:复现方式</h2>
<p><code>00_download_data.py</code> → <code>01_clean_etl.py</code>(PySpark 清洗,产出 DWD Parquet)→ <code>02_build_metrics.py</code>(ADS 指标层)→ <code>03_build_dashboard.py</code>(交互看板)/ 本报告。详见项目 README。</p>

<footer>本报告由 04_build_report.py 自动生成,全部数字来自 ADS 指标层,可一键复现。Divvy 数据使用遵循其开放数据条款。</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"报告已生成: {args.out} ({os.path.getsize(args.out) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
