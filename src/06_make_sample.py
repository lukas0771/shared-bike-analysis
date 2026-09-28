#!/usr/bin/env python3
"""06_make_sample.py — 从 DWD 层抽取样本数据入库(供无全量数据时快速体验).

抽取 1 月与 7 月各 10% 骑行记录,写出 data/sample/dwd_sample.parquet。
仓库自带该样本,克隆后无需下载 1.4GB 全量数据即可运行笔记本的降级模式。

用法:
    python 06_make_sample.py --data-root ./warehouse
"""
import argparse
import os
import sys

os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "--driver-memory 1500m pyspark-shell")

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="生成 DWD 样本数据")
    ap.add_argument("--data-root", default="warehouse")
    ap.add_argument("--sample-frac", type=float, default=0.1)
    args = ap.parse_args()

    dwd_path = os.path.join(args.data_root, "dwd")
    if not os.path.isdir(dwd_path):
        sys.exit(f"[error] 找不到 DWD 目录: {dwd_path},请先运行 01_clean_etl.py")

    spark = (SparkSession.builder
             .appName("divvy-sample")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    dwd = spark.read.parquet(dwd_path)
    sample = (dwd.filter(F.col("month").isin(1, 7))
              .sample(withReplacement=False, fraction=args.sample_frac, seed=42))
    n = sample.count()

    out = os.path.join("data", "sample")
    os.makedirs(out, exist_ok=True)
    tmp_out = os.path.join(out, "_tmp")
    sample.coalesce(1).write.mode("overwrite").parquet(tmp_out)
    part = [f for f in os.listdir(tmp_out) if f.endswith(".parquet")][0]
    os.replace(os.path.join(tmp_out, part), os.path.join(out, "dwd_sample.parquet"))
    for f in os.listdir(tmp_out):
        os.remove(os.path.join(tmp_out, f))
    os.rmdir(tmp_out)

    print(f"样本已生成: data/sample/dwd_sample.parquet({n:,} 行,约 {os.path.getsize(os.path.join(out, 'dwd_sample.parquet')) / 1e6:.1f} MB)")
    spark.stop()


if __name__ == "__main__":
    main()
