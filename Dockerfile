# =================================================
# 海克斯增幅计算器 - Docker 镜像
# 所有数据随镜像打包，开箱即用
# =================================================

FROM python:3.12-slim

LABEL maintainer="hextech-calc"
LABEL description="League of Legends Hextech Augment Calculator"
LABEL version="2.0.0"

# 使用默认源安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- 设置工作目录 ---
WORKDIR /app

# 分层优化：先拷贝依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- 复制项目文件 ---
COPY . .

# --- 预填充 SQLite 数据库 ---
RUN python3 scripts/prepare_db.py

# --- 验证数据库完整性 ---
RUN python3 -c "from engine.database import get_champion_count, get_augment_stats; c = get_champion_count(); a = get_augment_stats(); print(f'OK: {c} champs, {a.get(\"total\")} augments, curated {a.get(\"curated\")}, inferred {a.get(\"inferred\")}'); assert c > 0; assert a.get('total',0) > 0"

ENV GUNICORN_WORKERS=4
ENV GUNICORN_TIMEOUT=120
ENV PORT=9001

EXPOSE 9001

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
