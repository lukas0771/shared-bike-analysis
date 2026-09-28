#!/usr/bin/env python3
"""05_make_notebook.py — 构建并执行 EDA 分析笔记本(输出已运行的 .ipynb).

笔记本加载 ADS 指标层 + 两个样本月(1月/7月)的 DWD 明细,
复现报告的核心图表并给出分析结论;输出包含全部运行结果。

用法:
    DATA_ROOT=./warehouse python 05_make_notebook.py --out analysis/divvy_eda.ipynb
"""
import argparse
import os
import sys

import nbformat as nbf
from nbclient import NotebookClient


def code(src):
    return nbf.v4.new_code_cell(src)


def md(src):
    return nbf.v4.new_markdown_cell(src)


def build():
    cells = []
    cells.append(md("""# Divvy 共享单车时空分析(芝加哥 __YEAR__)

**数据**:Divvy 官方开放数据(全年真实骑行记录,PySpark 清洗后的 DWD 明细 + ADS 指标层)
**工具**:pandas · PySpark(离线管道)· matplotlib

本笔记本聚焦 **探索性分析(EDA)**:数据质量 → 季节性 → 分时规律 → 站点与流向 → 用户与车型。
大数据量的清洗与聚合由 PySpark 脚本(`01_clean_etl.py` / `02_build_metrics.py`)完成,
笔记本负责交互式探索与结论产出。"""))
    cells.append(code("""\
import os, json, glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager

YEAR = __YEAR__
DATA_ROOT = Path(os.environ.get("DATA_ROOT", "./warehouse"))
ADS = DATA_ROOT / "ads"

for f in glob.glob("/usr/share/fonts/**/*.tt[fc]", recursive=True):
    try: font_manager.fontManager.addfont(f)
    except Exception: pass
avail = {f.name for f in font_manager.fontManager.ttflist}
for name in ["Noto Sans SC", "WenQuanYi Zen Hei", "Noto Serif SC", "LXGW WenKai"]:
    if name in avail:
        plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]; break
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["axes.grid"] = True; plt.rcParams["grid.color"] = "#E5E7EB"

CBLUE, CAMBER, CGREEN, CPURPLE = "#1D4ED8", "#F59E0B", "#059669", "#7C3AED"
DOW = ["周一","周二","周三","周四","周五","周六","周日"]
def load(name): return pd.read_json(ADS / f"{name}.json")
kpi, cube, monthly, daily = load("kpi").iloc[0], load("cube"), load("monthly"), load("daily")
stations, od, dur = load("stations"), load("od"), load("dur_hist")
print(f"ADS 指标层加载完成:cube {len(cube)} 行,stations {len(stations)} 站,od {len(od)} 对")"""))
    cells.append(md("## 1. 数据质量(PySpark ETL 输出)"))
    cells.append(code("""\
quality = json.load(open(DATA_ROOT / "dwd" / "_quality.json", encoding="utf-8"))
pd.Series(quality).to_frame("value")"""))
    cells.append(md("""清洗规则:时长 ∈ (0, 1440] 分钟、关键字段非空、`ride_id` 去重;
站点/坐标缺失保留(站点级分析时过滤)。**原始 → 干净**的记录数变化即上表。"""))
    cells.append(md("## 2. 明细样本:1 月 vs 7 月"))
    cells.append(code("""\
DWD_PATH = DATA_ROOT / "dwd"
if DWD_PATH.exists():
    detail = pd.read_parquet(DWD_PATH, filters=[("month", "in", [1, 7])])
    print(f"已加载 DWD 全量明细(1月/7月): {detail.shape[0]:,} 行 × {detail.shape[1]} 列")
else:
    detail = pd.read_parquet("data/sample/dwd_sample.parquet")
    print("未找到 warehouse/dwd,使用仓库自带样本(data/sample/dwd_sample.parquet)")
detail.head(3)"""))
    cells.append(code("""\
detail["duration_min"].describe().to_frame("duration_min").round(2)"""))
    cells.append(code("""\
detail.groupby("member_casual")["duration_min"].agg(["count", "mean", "median"]).round(1)"""))
    cells.append(md("""**观察**:散客的中位/平均时长都明显高于会员——会员通勤高频短途,散客休闲低频长途。这是全年结构在样本月中的体现。"""))
    cells.append(md("## 3. 季节性"))
    cells.append(code("""\
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(monthly.month, monthly.n_member, color=CBLUE, label="会员")
ax.bar(monthly.month, monthly.n_casual, bottom=monthly.n_member, color=CAMBER, label="散客")
ax2 = ax.twinx(); ax2.plot(monthly.month, monthly.electric_share, color=CPURPLE, marker="o", label="电助力占比")
ax2.set_ylabel("电助力占比 (%)"); ax2.set_ylim(0, 100)
ax.set_xlabel("月份"); ax.set_ylabel("骑行次数"); ax.set_xticks(monthly.month)
ax.set_title(f"{YEAR} 年月度骑行量与会员结构"); ax.legend(loc="upper left", fontsize=9)
plt.show()"""))
    cells.append(code("""\
peak = monthly.loc[monthly.n.idxmax()]
low = monthly.loc[monthly.n.idxmin()]
print(f"峰值 {int(peak.month)} 月 {peak.n:,.0f} 次;低谷 {int(low.month)} 月 {low.n:,.0f} 次,比值 {peak.n/low.n:.1f}")"""))
    cells.append(md("## 4. 分时规律:通勤双峰 vs 周末单峰"))
    cells.append(code("""\
hm = np.zeros((7, 24))
for r in cube.itertuples(): hm[r.dow-1, r.hour] += r.n
fig, ax = plt.subplots(figsize=(9, 3.8))
im = ax.imshow(hm, aspect="auto", cmap="Blues")
ax.set_xticks(range(24)); ax.set_yticks(range(7), DOW)
ax.set_xlabel("小时"); ax.set_title("星期 × 小时 骑行热力(全年合计)")
fig.colorbar(im, ax=ax, shrink=.85); plt.show()"""))
    cells.append(code("""\
hc = cube.groupby(["member","dow","hour"], as_index=False).n.sum()
hc["weekend"] = hc.dow >= 6
piv = hc.pivot_table(index="hour", columns=["member","weekend"], values="n", aggfunc="sum")
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.plot(piv.index, piv[("member",False)], color=CBLUE, label="会员·工作日")
ax.plot(piv.index, piv[("member",True)], color="#93C5FD", label="会员·周末")
ax.plot(piv.index, piv[("casual",False)], color=CAMBER, label="散客·工作日")
ax.plot(piv.index, piv[("casual",True)], color="#FCD34D", label="散客·周末")
ax.set_xlabel("小时"); ax.set_ylabel("骑行次数(全年)")
ax.set_title("分时骑行曲线"); ax.legend(fontsize=9); plt.show()"""))
    cells.append(md("## 5. 站点与流向"))
    cells.append(code("""\
fig, ax = plt.subplots(figsize=(8, 4))
st = stations.sort_values("starts", ascending=False).head(12).iloc[::-1]
ax.barh(st.name, st.starts, color=CBLUE); ax.set_xlabel("起骑次数(全年)")
ax.set_title("起骑量 Top 12 站点"); plt.setp(ax.get_yticklabels(), fontsize=8); plt.show()"""))
    cells.append(code("""\
fig, ax = plt.subplots(figsize=(8, 5))
sc = ax.scatter(stations.lng, stations.lat, s=np.sqrt(stations.starts)*.7,
                c=stations.net, cmap="coolwarm", alpha=.7, linewidths=0)
for r in od.head(34).itertuples():
    ax.annotate("", xy=(r.e_lng, r.e_lat), xytext=(r.s_lng, r.s_lat),
                arrowprops=dict(arrowstyle="-", color="#0F2B5B", alpha=.35, lw=.8,
                                connectionstyle="arc3,rad=0.15"))
ax.set_xlabel("经度"); ax.set_ylabel("纬度")
ax.set_title("站点分布(气泡=起骑量,红/蓝=净流入/流出)与 Top OD 走廊")
fig.colorbar(sc, ax=ax, shrink=.8, label="净流入"); plt.show()"""))
    cells.append(code("""\
inflow = stations.nlargest(3, "net")[["name","net","starts","ends"]]
outflow = stations.nsmallest(3, "net")[["name","net","starts","ends"]]
print("净流入 Top3(还车 > 起骑):"); display(inflow)
print("净流出 Top3(起骑 > 还车):"); display(outflow)"""))
    cells.append(md("## 6. 用户与车型"))
    cells.append(code("""\
piv = cube.groupby(["month","member","bike"]).n.sum().unstack(["member","bike"]).fillna(0)
labels = {("member","classic_bike"):("会员·经典车",CBLUE), ("member","electric_bike"):("会员·电助力","#93C5FD"),
          ("casual","classic_bike"):("散客·经典车",CAMBER), ("casual","electric_bike"):("散客·电助力","#FCD34D")}
fig, ax = plt.subplots(figsize=(9, 3.8))
bottom = np.zeros(len(piv))
for key,(lab,c) in labels.items():
    if key in piv.columns: ax.bar(piv.index, piv[key], bottom=bottom, color=c, label=lab); bottom += piv[key].values
ax.set_xticks(piv.index); ax.set_xlabel("月份"); ax.set_ylabel("骑行次数")
ax.set_title("会员 × 车型 月度结构"); ax.legend(fontsize=8, ncol=2); plt.show()"""))
    cells.append(code("""\
g = cube.groupby(["member","bike"]).agg(n=("n","sum"), s=("sum_min","sum"))
avg = g.s / g.n
display(avg.round(1).to_frame("平均时长(分钟)"))
print(f"电助力车站外还车比例: {kpi.electric_offstation_pct}%")"""))
    cells.append(md("""## 7. 结论

1. **通勤主导**:工作日 8/17 时双峰 + 会员短时长结构,说明 Divvy 承载大量通勤需求;
2. **休闲需求**:散客周末 12–17 时单峰、时长更长,集中在滨湖与旅游走廊;
3. **空间潮汐**:净流入/流出站点固定,早晚高峰间需要定向调度;电助力站外还车进一步推高调度成本;
4. **局限**:无用户 ID(不能算留存/复购),无天气与事件数据(季节性归因待交叉验证);
5. **展望**:Structured Streaming 实时大屏、结合天气/POI 的需求预测与调度优化。

> 复现:先运行 `00_download_data.py` → `01_clean_etl.py` → `02_build_metrics.py`,
> 然后 `DATA_ROOT=./warehouse` 重新执行本笔记本。"""))
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="analysis/divvy_eda.ipynb")
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()

    nb = nbf.v4.new_notebook()
    src_cells = build()
    for c in src_cells:
        c.source = c.source.replace("__YEAR__", str(args.year))
    nb.cells = src_cells
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata["language_info"] = {"name": "python"}

    print("开始执行笔记本 ...")
    client = NotebookClient(nb, timeout=900, kernel_name="python3",
                            resources={"metadata": {"path": os.getcwd()}})
    client.execute()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    nbf.write(nb, args.out)
    n_exec = sum(1 for c in nb.cells if c.cell_type == "code")
    n_err = sum(1 for c in nb.cells if c.cell_type == "code"
                and any(o.get("output_type") == "error" for o in c.get("outputs", [])))
    print(f"笔记本已生成: {args.out}(code cells {n_exec},errors {n_err})")
    if n_err:
        sys.exit(1)


if __name__ == "__main__":
    main()
