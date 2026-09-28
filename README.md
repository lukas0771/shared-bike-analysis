# Divvy 共享单车时空数据分析 · 芝加哥 2025

基于芝加哥 Divvy 共享单车**官方开放数据**（2025 全年 12 个月、约 555 万条真实骑行记录）完成的端到端数据分析项目：

```
数据获取(官方S3直连) → PySpark 清洗(ODS/DWD 分层,Parquet 分区存储)
→ ADS 指标层(事实立方体 + 7 张指标表) → ECharts 交互式 BI 看板 + EDA 报告 + 可执行笔记本
```

## 1. 目录结构

```
├── README.md                 # 本文件
├── src/                      # 全流程代码(按编号即执行顺序)
│   ├── 00_download_data.py   # 官方数据下载(失败重试 + zip完整性校验)
│   ├── 01_clean_etl.py       # PySpark 清洗:ODS → DWD(规则可追溯)
│   ├── 02_build_metrics.py   # PySpark 聚合:DWD → ADS 指标层
│   ├── 03_build_dashboard.py # 生成交互式 BI 看板(单文件 HTML)
│   ├── 04_build_report.py    # 生成 EDA 分析报告(自包含 HTML)
│   ├── 05_make_notebook.py   # 构建并执行 EDA 笔记本
│   └── 06_ab_analysis.py     # 构建并执行「统计检验与 A/B 实验」笔记本
├── analysis/
│   ├── divvy_eda.ipynb       # 已执行的 EDA 笔记本(含全部输出)
│   └── ab_testing_analysis.ipynb   # 已执行的统计检验与 A/B 实验笔记本
├── dashboard/
│   └── divvy_dashboard_2025.html   # 交互看板(双击即看,离线可用)
├── report/
│   └── divvy_eda_report.html       # EDA 分析报告(图文自包含)
└── data/
    ├── ads/                  # 指标层结果(JSON+CSV,看板/报告的离线数据源,含 ab_tests.json)
    ├── dwd/_quality.json     # 清洗质量报告(口径可追溯)
    └── sample/               # DWD 明细样本(免下载预览用)
```

## 2. 快速开始(一键复现)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 免下载快速预览(用仓库自带指标层与样本):
python src/03_build_dashboard.py --data-root ./data --out dashboard/divvy_dashboard_2025.html
python src/04_build_report.py    --data-root ./data --out report/divvy_eda_report.html

# 完整复现(下载官方全量数据 ~350MB 后重建):
python src/00_download_data.py --year 2025 --data-root ./warehouse
python src/01_clean_etl.py      --data-root ./warehouse
python src/02_build_metrics.py  --data-root ./warehouse
python src/03_build_dashboard.py --data-root ./warehouse --out dashboard/divvy_dashboard_2025.html
python src/04_build_report.py   --data-root ./warehouse --out report/divvy_eda_report.html
DATA_ROOT=./warehouse python src/05_make_notebook.py --out analysis/divvy_eda.ipynb
DATA_ROOT=./warehouse python src/06_ab_analysis.py   --out analysis/ab_testing_analysis.ipynb
```

> 需要 Java 17/21（Spark 4.x）。数据与中间结果在 `warehouse/` 下生成（ods/dwd/ads 三层），默认不随仓库分发。
> Windows 本机跑 Spark 需先准备 winutils.exe + hadoop.dll（并设 `HADOOP_HOME`），或直接用仓库自带的 Docker 方案；
> 本机内存紧张时可用 `PYSPARK_SUBMIT_ARGS="--driver-memory 3g pyspark-shell"` 覆盖默认堆大小。

## 3. 分层设计与数据口径

| 层 | 内容 | 存储 |
|---|---|---|
| ODS | 官方 CSV 原样落地，按 `year=/month=` 分区 | CSV |
| DWD | 清洗后的明细：时长派生、星期/小时派生、脏数据剔除 | Parquet（按月分区） |
| ADS | 面向分析的指标表：KPI、事实立方体、月/日/站点/OD/时长分布 | JSON + CSV |

**清洗规则（全部记录于 `data/dwd/_quality.json`）**：时长 ∈ (0, 1440] 分钟；时间字段可解析；`member_casual`/`rideable_type` 非空；`ride_id` 去重；站点/坐标缺失**保留为空**（电助力车支持站外还车，是分析对象而非脏数据）。

**核心指标口径**：

| 指标 | 口径 |
|---|---|
| 总骑行量 | DWD 有效记录数（清洗后） |
| 会员占比 | `member` 记录 / 总记录 |
| 平均/中位时长 | `ended_at - started_at`，分钟；中位数用 `percentile_approx` |
| 站点起骑量 | `start_station_id` 非空记录按站点计数 |
| 净流入 | 站点全年还车数 − 起骑数（正=净流入，负=净流出） |
| 站外还车率 | 电助力车中 `end_station_id` 为空的占比 |
| 事实立方体 | (month × 星期 × hour × 会员 × 车型) → (记录数, 时长和)，支撑看板联动筛选 |

## 4. 看板功能

- **四个页签**：概览（KPI+月度/日趋势）、时间规律（星期×小时热力、分时曲线）、站点与流向（Top 站点、坐标散点+OD 走廊、潮汐净流入）、用户与车型（会员×车型结构、时长对比）
- **全局筛选联动**：月份（全年/各月）× 用户类型（全部/会员/散客）
- **工程特性**：ECharts 与数据全部内嵌，单文件离线可用；站点/流向页签为全年汇总口径（页面内有说明）

## 5. 核心发现（2025 年）

- **通勤双峰**：工作日 8 时与 17 时为全天需求双峰，17 时最高；周末呈 12–17 时单峰休闲形态
- **季节性**：夏季（8 月峰值 789,475 次）约为冬季低谷的 5.7 倍
- **用户结构**：会员占 64.0%，平均骑行 12.0 分钟；散客平均 19.1 分钟——时长差异是通勤型 vs 休闲型的典型特征
- **观光环线**：全年最热 OD 是 Navy Pier → Navy Pier（同站还车）8,657 次，其中 92% 为散客——典型的景区观光环线骑行
- **站点潮汐**：St. Clair St & Erie St / Franklin St & Monroe St（通勤终点，白天净流入）与 Columbus Dr & Randolph St / Field Museum（通勤起点）呈镜像分布
- **车型结构**：电助力车占 65.0%，且 34.3% 的电助力骑行站外还车（无桩归还特征）

## 6. 统计检验与 A/B 实验模块（src/06 · ab_testing_analysis.ipynb）

在描述性分析之上回答两个进阶问题：**观测到的差异统计上成立吗？业务假设该如何用实验验证？**
全部统计量来自全量 555 万条 DWD 明细与真实历史方差，结果落盘 `data/ads/ab_tests.json`。

### Part A · 假设检验（全量明细）

| 业务问题 | 方法 | 结论 |
|---|---|---|
| 会员 vs 散客时长差异真实存在吗？ | Welch t + Mann-Whitney + Cohen's d + bootstrap CI | p≈0 但 **d 仅 0.25（小效应）**；均值差 7.2 分钟（95% CI [7.12, 7.24]）——大样本下结论看效应量，不看 p 值 |
| 工作日/周末的小时分布不同吗？ | 卡方独立性 + Cramér's V | χ²(23)≈3.1×10⁵，**V=0.235（中等效应）**：双峰 vs 单峰是结构性差异 |
| 电助力真的比经典车"短很多"吗？ | 总体 vs 分层口径对比 | 总体差 6.9 分钟，会员层内仅 2.6、散客层内 15.2——**构成偏差使总体口径失真 2.6 倍**，既不代表任何一层 |

A3 是 Part B 的引子：混杂变量让观测结论失真——**随机化是唯一能同时均衡已观测与未观测混杂的手段**。

### Part B · A/B 实验设计（基于真实数据的模拟演练）

> **诚实边界**：没有真实上线过实验。方差、站点池、功效计算全部来自真实历史数据；"处理组效应"为按预设 uplift 注入。方法论真实，结果为模拟，两者不混淆。

业务假设："高需求站点**优先补充电助力车**能否提升站点日均起骑量"。按真实实验流程走完全程：

| 步骤 | 做法 | 结果 |
|---|---|---|
| 预注册设计 | 北极星=站点 30 日均起骑量；护栏=时长( │DiD│≤0.5 分)、电助力站外还车率(恶化≤5%)；随机化单元=站点（讨论 SUTVA 溢出→真实 uplift 被低估） | — |
| 选池与实验窗分离 | 6 月数据选池（391 站，日均≥10）、8 月为实验窗 | 避免"用结果选样本" |
| 功效分析 | σ/μ≈0.8，检出 5% 需每组 4090 站（不可行）→ **CUPED** 用 6 月水平降噪（6/7 月 ρ=0.994） | MDE 从 **23.9% 压到 2.8%**（每组 180 站可行） |
| AA 检验 | 2000 次无处理随机分组跑完整分析 | 假阳性率 **4.5%**（期望 5%）、p 值中位数 0.46 → 管线无偏 |
| 分流 | **分层块随机化**（按 6 月水平配对+对内掷硬币）+ SRM 卡方 | 纯随机基线差极端可达 μ 的 23%；块随机化仅 **-0.08 次/日**；SRM 通过 |
| 注入实验 | uplift=MDE×1.25=3.5%，同时注入 -2% 时长效应 | 北极星 **+3.55%（CI [+1.2%, +5.9%]，p=0.003）**——朴素口径 +3.4% 但 p=0.66，CUPED 方差缩减是检出关键 |
| 上线决策 | 护栏①时长 DiD -0.46 分（阈值内）、护栏②+0.5%（方向有利） | **三项全过 → 建议上线**（附溢出偏差与局限讨论） |

一个值得展开的细节：护栏①的 DiD 统计显著（p=0.007）但幅度仍在业务阈值内——**统计显著 ≠ 业务显著**，护栏是否"违反"由预注册阈值决定，不由 p 值决定。



## 7. 简历写法参考

> - 基于芝加哥 Divvy 官方全年 555 万条骑行数据，设计并实现 PySpark 数据管道（ODS/DWD/ADS 三层，Parquet 按月分区），清洗规则可追溯，管道一键复现
> - 构建事实立方体（月×星期×小时×会员×车型）支撑 ECharts 交互看板的二级联动筛选；看板与数据全部内嵌为单文件离线 HTML
> - 产出运营级洞察：通勤双峰、5.7 倍季节性波动、会员/散客时长差 2 倍、站点潮汐与站外还车率等，并给出调运与会员转化建议
> - 新增统计检验与 A/B 实验模块：对全量明细完成 Welch t / Mann-Whitney / 卡方检验与效应量、bootstrap 置信区间分析；以真实历史方差做功效分析与 CUPED 降噪，完成 AA 检验、SRM 校验与注入效应的模拟实验及上线决策（详见第 6 节）

## 8. 面试 FAQ

**Q1 为什么用 Spark，pandas 不行吗？**
555 万条（约 1.4GB CSV）pandas 也能跑，但全量载入内存 ~2GB 已接近单机舒适上限；Spark 分区流式处理 + 并行聚合在本地即验证了代码正确性，且同一份代码可零改动提交到集群处理多城市/多年（亿级）数据。这是"为规模预留路径"，而不是为了用而用。

**Q2 做了哪些 Spark 优化？**
手动 Schema 避免双次扫描（省一次全量推断）；`shuffle.partitions` 从默认 200 调到 8 匹配 local[2]；按 `month` repartition 控制小文件；多项异常计数合并为单次 `agg`（一遍扫描拿到全部质量指标）；`percentile_approx` 近似中位数避免全量排序。

**Q3 数据质量怎么保证？**
下载层 zip 完整性校验（曾实测拦截到半截文件）；清洗层 5 条规则 + 剔除率全部落 `_quality.json`；站点/坐标缺失**不剔除**而是保留分析（电助力站外还车本身就是洞察）。

**Q4 看板为什么不用 Superset / Tableau？**
ADS 层有标准 CSV/JSON，接任何 BI 都行；选单文件 HTML 是为了**零部署分发**——面试官双击就能看，断网也能看。工程权衡本身也是面试谈资。

**Q5 下一步演进？**
实时链路（Kafka 回放 + Structured Streaming 实时大屏）；接入天气/POI 做需求预测（GBDT）；站点级潮汐调度优化（线性规划）。

**Q6 统计检验与 A/B 模块为什么是"模拟"的？个人项目拿不到线上流量吧？**
拿不到，这是客观限制，所以 README 里写明"模拟演练"而不是假装跑过真实实验。但模块里每个环节都是真实方法、真实数据：假设检验跑在全量 555 万条明细上；功效分析的方差、站点池、实验窗全部来自真实历史数据；AA 检验、SRM 校验、CUPED、护栏阈值都是业界标准流程。唯一模拟的是"注入的 uplift"。把方法边界说清楚，比含糊其辞更有说服力。

**Q7 为什么要做 CUPED？不做会怎样？**
站点级指标的方差主要由"站点固有水平差异"贡献，与处理无关，但会淹没效应信号：朴素口径下检出 5% 提升 需要的站点数远超芝加哥站点总量（算出来不可行）。CUPED 用实验前（6 月）站点水平作协变量扣除这部分方差，把可检出的 MDE 从 ~24% 压到 ~3%。它的两个前提在本数据中都成立：协变量与实验期指标高度相关（6/7 月站点水平相关 ρ≈0.99），且协变量不受处理影响——这也是"选池用 6 月、实验窗用 8 月"的原因。

**Q8 AA 检验和 SRM 校验分别防什么错？**
AA 检验防"分析管线本身有偏"：对无处理的随机分组反复跑检验，p 值应服从均匀分布、假阳性率 ≈ α；显著率异常说明指标计算或分组有 bug。SRM（样本比例失配）防"分流实现有错"：拿到实验数据第一件事是校验分组比例是否符合设计，比例失配时任何指标结论都不可信。两者都是"先证明量尺没坏，再读数"。

## 9. 数据来源与许可

数据来自 [Divvy System Data](https://divvybikes.com/system-data)（Lyft 与芝加哥市交通局 CDOT 发布的开放数据），按其许可条款用于非商业学习分析；本项目对数据做了清洗与聚合，结论仅供学习参考。

## 10. 环境说明

Python 3.12 · PySpark 4.2(Spark SQL) · pandas · scipy / statsmodels（统计检验与功效分析）· matplotlib · ECharts 5.5；本地开发用 `local[2]`，提交集群仅需改 `master`。看板/报告/笔记本均为自包含文件，仓库不含原始数据（复现跑 `00` 即可重新获取）。
