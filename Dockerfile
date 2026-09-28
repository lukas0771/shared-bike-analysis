# Dockerfile — Divvy 共享单车时空分析项目(Python 3.12 + Java 21 + PySpark local)
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jdk-headless procps \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY analysis/ analysis/
COPY data/ data/

# 默认入口:跑完整管道(下载→清洗→指标→看板→报告)
CMD ["bash", "-c", "python src/00_download_data.py --data-root warehouse && python src/01_clean_etl.py --data-root warehouse && python src/02_build_metrics.py --data-root warehouse && python src/03_build_dashboard.py --data-root warehouse --out dashboard/divvy_dashboard_2025.html && python src/04_build_report.py --data-root warehouse --out report/divvy_eda_report.html"]
