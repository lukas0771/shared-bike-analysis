#!/usr/bin/env python3
"""01_clean_etl.py — PySpark 清洗:ODS(CSV) → DWD(Parquet,按月分区).

清洗规则(口径可追溯,全部记录到 _quality.json):
  1. 时间字段解析失败/为空            → 剔除
  2. 骑行时长 <= 0 分钟 或 > 24 小时   → 剔除(调度测试/丢失车辆等脏数据)
  3. member_casual / rideable_type 缺失 → 剔除
  4. ride_id 重复                     → 去重保留一条
  5. 站点/坐标缺失                    → 保留(标记为空,站点级分析时再过滤)

派生维度: duration_min, date, hour, dow(1=周一..7=周日), day_type(工作日/周六/周日)

用法:
    python 01_clean_etl.py --data-root ./warehouse --year 2025
"""
import argparse
import json
import os
import sys

os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "--driver-memory 1200m pyspark-shell")

from pyspark import StorageLevel  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from pyspark.sql import types as T  # noqa: E402

SCHEMA = T.StructType([
    T.StructField("ride_id", T.StringType(), True),
    T.StructField("rideable_type", T.StringType(), True),
    T.StructField("started_at", T.StringType(), True),
    T.StructField("ended_at", T.StringType(), True),
    T.StructField("start_station_name", T.StringType(), True),
    T.StructField("start_station_id", T.StringType(), True),
    T.StructField("end_station_name", T.StringType(), True),
    T.StructField("end_station_id", T.StringType(), True),
    T.StructField("start_lat", T.DoubleType(), True),
    T.StructField("start_lng", T.DoubleType(), True),
    T.StructField("end_lat", T.DoubleType(), True),
    T.StructField("end_lng", T.DoubleType(), True),
    T.StructField("member_casual", T.StringType(), True),
])

MAX_DURATION_MIN = 1440.0  # 24h


def build_spark(app: str) -> SparkSession:
    return (SparkSession.builder
            .appName(app)
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.driver.maxResultSize", "1g")
            .config("spark.ui.enabled", "false")
            .getOrCreate())


def main():
    ap = argparse.ArgumentParser(description="ODS→DWD 清洗")
    ap.add_argument("--data-root", default="warehouse")
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()

    ods_root = os.path.join(args.data_root, "ods")
    dwd_path = os.path.join(args.data_root, "dwd")
    if not os.path.isdir(ods_root):
        sys.exit(f"[error] 找不到 ODS 目录: {ods_root},请先运行 00_download_data.py")

    spark = build_spark("divvy-clean-etl")
    spark.sparkContext.setLogLevel("WARN")

    # 分区发现: ods/year=2025/month=01/*.csv → 自动带出 year/month 分区列
    raw = (spark.read
           .option("basePath", ods_root)
           .option("header", "true")
           .schema(SCHEMA)
           .csv(ods_root))
    raw = raw.withColumn("month", F.col("month").cast("int")) \
             .withColumn("year", F.col("year").cast("int"))

    df = (raw
          .withColumn("started_ts", F.to_timestamp("started_at"))
          .withColumn("ended_ts", F.to_timestamp("ended_at"))
          .withColumn("duration_min",
                      (F.unix_timestamp("ended_ts") - F.unix_timestamp("started_ts")) / 60.0))

    bad_time = df.started_ts.isNull() | df.ended_ts.isNull()
    bad_duration = df.duration_min.isNull() | (df.duration_min <= 0) | (df.duration_min > MAX_DURATION_MIN)
    bad_enum = df.member_casual.isNull() | df.rideable_type.isNull()

    qa = df.agg(
        F.count("*").alias("n_raw"),
        F.sum(F.when(bad_time, 1).otherwise(0)).alias("n_bad_time"),
        F.sum(F.when(~bad_time & bad_duration, 1).otherwise(0)).alias("n_bad_duration"),
        F.sum(F.when(~bad_time & ~bad_duration & bad_enum, 1).otherwise(0)).alias("n_bad_enum"),
        F.countDistinct("ride_id").alias("n_distinct_ride_id"),
    ).toPandas().iloc[0]

    dwd = (df
           .filter(~bad_time & ~bad_duration & ~bad_enum)
           .dropDuplicates(["ride_id"])
           .withColumn("date", F.to_date("started_ts"))
           .withColumn("hour", F.hour("started_ts"))
           .withColumn("dow", ((F.dayofweek("started_ts") + 5) % 7) + 1)  # 1=周一..7=周日
           .withColumn("day_type", F.when(F.col("dow") == 6, "周六")
                       .when(F.col("dow") == 7, "周日").otherwise("工作日"))
           .select("ride_id", "rideable_type", "member_casual",
                   "started_ts", "ended_ts", "duration_min",
                   "date", "hour", "dow", "day_type", "month", "year",
                   "start_station_id", "start_station_name", "start_lat", "start_lng",
                   "end_station_id", "end_station_name", "end_lat", "end_lng")
           .persist(StorageLevel.DISK_ONLY))  # 一遍扫描,写盘缓存,后续动作直接读

    (dwd.write.mode("overwrite")
     .partitionBy("year", "month")
     .parquet(dwd_path))

    n_out = dwd.count()
    dwd.unpersist()
    quality = {
        "year": args.year,
        "n_raw": int(qa["n_raw"]),
        "n_distinct_ride_id": int(qa["n_distinct_ride_id"]),
        "dropped_bad_time": int(qa["n_bad_time"]),
        "dropped_bad_duration": int(qa["n_bad_duration"]),
        "dropped_bad_enum": int(qa["n_bad_enum"]),
        "n_duplicate_rides": int(qa["n_raw"] - qa["n_distinct_ride_id"]),
        "n_clean": int(n_out),
        "drop_rate_pct": round(100.0 * (qa["n_raw"] - n_out) / qa["n_raw"], 3) if qa["n_raw"] else 0,
        "rules": {
            "duration": f"(0, {MAX_DURATION_MIN:.0f}] 分钟",
            "dup": "ride_id 去重",
            "null_station_keep": "站点/坐标缺失保留为空",
        },
    }
    qpath = os.path.join(args.data_root, "dwd", "_quality.json")
    with open(qpath, "w", encoding="utf-8") as fh:
        json.dump(quality, fh, ensure_ascii=False, indent=2)

    print(json.dumps(quality, ensure_ascii=False, indent=2))
    spark.stop()


if __name__ == "__main__":
    main()
