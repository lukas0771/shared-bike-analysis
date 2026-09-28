#!/usr/bin/env python3
"""02_build_metrics.py — PySpark 聚合:DWD → ADS 指标层.

产出(warehouse/ads/ 下同名 .json + .csv,供看板/报告/笔记本复用):
  kpi        年度总览指标
  cube       事实立方体 (month, dow, hour, member, bike) → (n, sum_min)
  monthly    月度:骑行量/会员散客/车型/时长均值与中位数
  daily      日粒度:骑行量/会员散客/星期属性
  dur_hist   骑行时长分布 (member × bike × 时长桶)
  stations   站点画像:起骑/还车/净流入/会员占比/坐标
  od         Top OD 流向对(含坐标,供流向图)

用法:
    python 02_build_metrics.py --data-root ./warehouse
"""
import argparse
import json
import os
import sys

os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "--driver-memory 1500m pyspark-shell")

import pandas as pd  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

DURATION_BUCKETS = [
    (5, "0-5"), (10, "5-10"), (15, "10-15"), (20, "15-20"), (30, "20-30"),
    (45, "30-45"), (60, "45-60"), (90, "60-90"), (120, "90-120"),
    (240, "120-240"), (float("inf"), "240+"),
]


def bucket_expr(col):
    """链式 when:按顺序取第一个满足的区间;最后一个上界为 inf,必然命中."""
    expr = None
    for upper, label in DURATION_BUCKETS:
        cond = F.col(col) < upper
        expr = F.when(cond, F.lit(label)) if expr is None else expr.when(cond, F.lit(label))
    return expr


def dump(path_prefix, records):
    """同时写 JSON(records) 与 CSV,统一处理 numpy 类型."""
    pdf = pd.DataFrame(records)
    pdf.to_json(path_prefix + ".json", orient="records", force_ascii=False)
    pdf.to_csv(path_prefix + ".csv", index=False)
    print(f"  {os.path.basename(path_prefix)}: {len(pdf)} 行")


def main():
    ap = argparse.ArgumentParser(description="DWD→ADS 指标计算")
    ap.add_argument("--data-root", default="warehouse")
    args = ap.parse_args()

    dwd_path = os.path.join(args.data_root, "dwd")
    ads_dir = os.path.join(args.data_root, "ads")
    os.makedirs(ads_dir, exist_ok=True)
    if not os.path.isdir(dwd_path):
        sys.exit(f"[error] 找不到 DWD 目录: {dwd_path},请先运行 01_clean_etl.py")

    spark = (SparkSession.builder
             .appName("divvy-metrics")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.sql.adaptive.enabled", "true")
             .config("spark.driver.maxResultSize", "1g")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    dwd = spark.read.parquet(dwd_path)
    n_total = dwd.count()
    print(f"DWD 总行数: {n_total:,}")

    # ---------- 事实立方体 ----------
    cube = (dwd.groupBy("month", "dow", "hour", "member_casual", "rideable_type")
            .agg(F.count("*").alias("n"),
                 F.round(F.sum("duration_min"), 1).alias("sum_min")))
    pdf_cube = (cube.toPandas()
                .rename(columns={"member_casual": "member", "rideable_type": "bike"})
                .sort_values(["month", "dow", "hour"]))
    dump(os.path.join(ads_dir, "cube"), pdf_cube.to_dict("records"))

    # ---------- 月度 ----------
    monthly = dwd.groupBy("month").agg(
        F.count("*").alias("n"),
        F.round(F.avg("duration_min"), 1).alias("avg_min"),
        F.round(F.percentile_approx("duration_min", 0.5, 1000), 1).alias("p50_min"),
    ).toPandas()
    mm = dwd.groupBy("month", "member_casual").count().toPandas() \
        .pivot(index="month", columns="member_casual", values="count").reset_index()
    mb = dwd.groupBy("month", "rideable_type").count().toPandas() \
        .pivot(index="month", columns="rideable_type", values="count").reset_index()
    monthly = monthly.merge(mm, on="month", how="left").merge(mb, on="month", how="left")
    monthly = monthly.rename(columns={
        "member": "n_member", "casual": "n_casual",
        "classic_bike": "n_classic", "electric_bike": "n_electric"})
    for col in ("n_member", "n_casual", "n_classic", "n_electric"):
        if col not in monthly.columns:
            monthly[col] = 0
    monthly = monthly.fillna(0).sort_values("month")
    monthly["electric_share"] = (100 * monthly["n_electric"] / monthly["n"]).round(1)
    dump(os.path.join(ads_dir, "monthly"), monthly.to_dict("records"))

    # ---------- 日粒度 ----------
    daily = dwd.groupBy("date", "dow", "day_type").agg(
        F.count("*").alias("n"),
        F.sum(F.when(F.col("member_casual") == "member", 1).otherwise(0)).alias("n_member"),
        F.sum(F.when(F.col("member_casual") == "casual", 1).otherwise(0)).alias("n_casual"),
    ).toPandas().sort_values("date")
    daily["date"] = daily["date"].astype(str)  # pandas3 下稳定序列化为 "YYYY-MM-DD"
    dump(os.path.join(ads_dir, "daily"), daily.to_dict("records"))

    # ---------- 时长分布(带月份维度,支持看板联动) ----------
    dur = (dwd.withColumn("bucket", bucket_expr("duration_min"))
           .groupBy("month", "member_casual", "rideable_type", "bucket")
           .count().toPandas()
           .rename(columns={"member_casual": "member", "rideable_type": "bike", "count": "n"}))
    order = [label for _, label in DURATION_BUCKETS]
    dur["bucket"] = pd.Categorical(dur["bucket"], categories=order, ordered=True)
    dur = dur.sort_values(["member", "bike", "bucket"])
    dump(os.path.join(ads_dir, "dur_hist"), dur.to_dict("records"))

    # ---------- 站点画像 ----------
    starts = (dwd.filter(F.col("start_station_id").isNotNull())
              .groupBy("start_station_id")
              .agg(F.first("start_station_name").alias("name"),
                   F.round(F.avg("start_lat"), 5).alias("lat"),
                   F.round(F.avg("start_lng"), 5).alias("lng"),
                   F.count("*").alias("starts"),
                   F.sum(F.when(F.col("member_casual") == "member", 1).otherwise(0)).alias("starts_member")))
    ends = (dwd.filter(F.col("end_station_id").isNotNull())
            .groupBy("end_station_id")
            .agg(F.count("*").alias("ends"),
                 F.sum(F.when(F.col("member_casual") == "member", 1).otherwise(0)).alias("ends_member")))
    stations = (starts.join(ends, starts.start_station_id == ends.end_station_id, "left")
                .select("start_station_id", "name", "lat", "lng",
                        "starts", "starts_member", "ends", "ends_member")
                .toPandas()
                .rename(columns={"start_station_id": "station_id"}))
    stations["ends"] = stations["ends"].fillna(0)
    stations["ends_member"] = stations["ends_member"].fillna(0)
    stations["net"] = stations["ends"] - stations["starts"]
    stations["member_share"] = (stations["starts_member"] / stations["starts"]).round(3)
    stations = stations.dropna(subset=["lat", "lng"]).sort_values("starts", ascending=False)
    dump(os.path.join(ads_dir, "stations"), stations.to_dict("records"))

    # ---------- Top OD 流向 ----------
    od = (dwd.filter(F.col("start_station_id").isNotNull() & F.col("end_station_id").isNotNull())
          .groupBy("start_station_id", "end_station_id")
          .agg(F.count("*").alias("n"),
               F.sum(F.when(F.col("member_casual") == "member", 1).otherwise(0)).alias("n_member"),
               F.round(F.avg("duration_min"), 1).alias("avg_min"))
          .filter(F.col("n") >= 100)
          .toPandas())
    st_ref = stations.set_index("station_id")[["name", "lat", "lng"]]
    od = od.join(st_ref.add_prefix("s_"), on="start_station_id") \
           .join(st_ref.add_prefix("e_"), on="end_station_id")
    od = od.dropna(subset=["s_lat", "e_lat"]).sort_values("n", ascending=False).head(1000)
    od = od.rename(columns={"start_station_id": "start_id", "end_station_id": "end_id"})
    dump(os.path.join(ads_dir, "od"), od.to_dict("records"))

    # ---------- KPI ----------
    e_off = dwd.filter((F.col("rideable_type") == "electric_bike") & F.col("end_station_id").isNull()).count()
    e_all = dwd.filter(F.col("rideable_type") == "electric_bike").count()
    peak = daily.loc[daily["n"].idxmax()]
    kpi = {
        "n_rides": int(n_total),
        "n_member": int(dwd.filter(F.col("member_casual") == "member").count()),
        "n_casual": int(dwd.filter(F.col("member_casual") == "casual").count()),
        "n_classic": int(dwd.filter(F.col("rideable_type") == "classic_bike").count()),
        "n_electric": e_all,
        "avg_min": round(float(dwd.agg(F.avg("duration_min")).collect()[0][0]), 1),
        "p50_min": round(float(dwd.agg(F.percentile_approx("duration_min", 0.5, 1000)).collect()[0][0]), 1),
        "active_stations": int(stations[stations["starts"] > 0].shape[0]),
        "electric_offstation_pct": round(100.0 * e_off / e_all, 1) if e_all else 0.0,
        "peak_date": str(peak["date"]),
        "peak_day_rides": int(peak["n"]),
        "n_days": int(daily.shape[0]),
    }
    dump(os.path.join(ads_dir, "kpi"), [kpi])
    print(json.dumps(kpi, ensure_ascii=False, indent=2))
    spark.stop()


if __name__ == "__main__":
    main()
