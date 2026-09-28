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
│   ├── 00_download_data.py   # 官方数据下载(断点续传 + zip完整性校验)
│   ├── 01_clean_etl.py       # PySpark 清洗:ODS → DWD(规则可追溯)
│   ├── 02_build_metrics.py   # PySpark 聚合:DWD → ADS 指标层
│   ├── 03_build_dashboard.py # 生成交互式 BI 看板(单文件 HTML)
│   ├── 04_build_report.py    # 生成 EDA 分析报告(自包含 HTML)
│   └── 05_make_notebook.py   # 构建并执行 EDA 笔记本
├── analysis/
│   └── divvy_eda.ipynb       # 已执行的 EDA 笔记本(含全部输出)
├── dashboard/
│   └── divvy_dashboard_2025.html   # 交互看板(双击即看,离线可用)
├── report/
│   └── divvy_eda_report.html       # EDA 分析报告(图文自包含)
└── data/
    ├── ads/                  # 指标层结果(JSON+CSV,看板/报告的离线数据源)
    └── dwd/_quality.json   # 清洗质量报告(口径可追溯)
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
```

> 需要 Java 17/21（Spark 4.x）。数据与中间结果在 `warehouse/` 下生成（ods/dwd/ads 三层），默认不随仓库分发。

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

## 6. 简历写法参考

> - 基于芝加哥 Divvy 官方全年 555 万条骑行数据，设计并实现 PySpark 数据管道（ODS/DWD/ADS 三层，Parquet 按月分区），清洗规则可追溯，管道一键复现
> - 构建事实立方体（月×星期×小时×会员×车型）支撑 ECharts 交互看板的二级联动筛选；看板与数据全部内嵌为单文件离线 HTML
> - 产出运营级洞察：通勤双峰、5.7 倍季节性波动、会员/散客时长差 2 倍、站点潮汐与站外还车率等，并给出调运与会员转化建议

## 7. 面试 FAQ

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

## 8. 数据来源与许可

数据来自 [Divvy System Data](https://divvybikes.com/system-data)（Lyft 与芝加哥市交通局 CDOT 发布的开放数据），按其许可条款用于非商业学习分析；本项目对数据做了清洗与聚合，结论仅供学习参考。

## 9. 环境说明

Python 3.12 · PySpark 4.2(Spark SQL) · pandas · matplotlib · ECharts 5.5；本地开发用 `local[2]`，提交集群仅需改 `master`。看板/报告/笔记本均为自包含文件，仓库不含原始数据（复现跑 `00` 即可重新获取）。
