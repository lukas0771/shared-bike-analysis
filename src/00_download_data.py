#!/usr/bin/env python3
"""00_download_data.py — 下载 Divvy 官方骑行数据并解压到 ODS 层.

数据源:芝加哥交通局/Divvy 官方 S3 开放数据(免登录直连)
  https://divvy-tripdata.s3.amazonaws.com/{YYYYMM}-divvy-tripdata.zip

用法:
    python 00_download_data.py --year 2025 --data-root ./warehouse

输出目录结构(ODS,保持原始数据不动):
    {data-root}/ods/year=2025/month=01/202501-divvy-tripdata.csv
    {data-root}/ods/year=2025/month=02/...
"""
import argparse
import concurrent.futures
import os
import time
import urllib.request
import zipfile

BASE_URL = "https://divvy-tripdata.s3.amazonaws.com/{ym}-divvy-tripdata.zip"

# 2020Q2 之后的官方表结构;若上游改版,这里会显式报 MISSING
EXPECTED_HEADER = {
    "ride_id", "rideable_type", "started_at", "ended_at",
    "start_station_name", "start_station_id",
    "end_station_name", "end_station_id",
    "start_lat", "start_lng", "end_lat", "end_lng",
    "member_casual",
}


def zip_intact(zip_path: str) -> bool:
    """校验 zip 完整性(可打开且含 CSV),防止半截文件被误判为完整."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            return any(n.endswith(".csv") for n in z.namelist())
    except Exception:
        return False


def download_one(ym: str, raw_dir: str):
    """下载单月 zip,失败自动重试 3 次;已存在且完整则跳过."""
    zip_path = os.path.join(raw_dir, f"{ym}.zip")
    url = BASE_URL.format(ym=ym)
    for attempt in range(1, 5):
        try:
            if not (os.path.exists(zip_path) and zip_intact(zip_path)):
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                urllib.request.urlretrieve(url, zip_path)
            return ym, zip_path, os.path.getsize(zip_path)
        except Exception as exc:  # noqa: BLE001 网络重试
            print(f"[warn] {ym} 第{attempt}次下载失败: {exc}", flush=True)
            time.sleep(2 * attempt)
    return ym, None, 0


def extract_and_verify(ym: str, zip_path: str, year: int, ods_root: str):
    """解压到 ODS 分区目录,并校验表头/行数."""
    month = ym[-2:]
    dest = os.path.join(ods_root, f"year={year}", f"month={month}")
    os.makedirs(dest, exist_ok=True)
    if any(f.endswith(".csv") for f in os.listdir(dest)):
        return f"[skip] {ym} 已解压过"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    csv_name = next(f for f in os.listdir(dest) if f.endswith(".csv"))
    csv_path = os.path.join(dest, csv_name)
    with open(csv_path, "r", encoding="utf-8") as fh:
        header = set(fh.readline().strip().split(","))
        n_rows = sum(1 for _ in fh)
    missing = EXPECTED_HEADER - header
    status = "表头OK" if not missing else f"表头缺失: {sorted(missing)}"
    return f"[ok] {ym}: {n_rows:,} 行, {csv_name}, {status}"


def main():
    ap = argparse.ArgumentParser(description="下载 Divvy 官方月度数据到 ODS 层")
    ap.add_argument("--year", type=int, default=2025, help="下载哪一年的 12 个月")
    ap.add_argument("--data-root", default="warehouse", help="数据仓库根目录")
    args = ap.parse_args()

    ods_root = os.path.join(args.data_root, "ods")
    raw_dir = os.path.join(args.data_root, "raw")
    os.makedirs(ods_root, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)

    months = [f"{args.year}{m:02d}" for m in range(1, 13)]
    print(f"开始下载 {len(months)} 个月的数据文件...", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda ym: download_one(ym, raw_dir), months))

    n_ok = sum(1 for _, zp, _ in results if zp)
    print(f"下载完成: {n_ok}/{len(months)}", flush=True)
    for ym, zip_path, size in results:
        if zip_path is None:
            print(f"[FAIL] {ym} 下载失败,请重跑本脚本(支持断点续传)", flush=True)
            continue
        print(f"  {ym}.zip {size / 1e6:.1f} MB", flush=True)
        print("  " + extract_and_verify(ym, zip_path, args.year, ods_root), flush=True)


if __name__ == "__main__":
    main()
