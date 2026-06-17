# --- 基础镜像 ---
FROM python:3.12-slim

LABEL maintainer="hextech-calc"
LABEL description="League of Legends Hextech Augment Calculator"
LABEL version="2.0.0"

# 彻底清理所有源文件，锁定系统版本，替换腾讯内网源，杜绝trixie跨版本冲突
RUN rm -rf /etc/apt/sources.list.d/* \
    && truncate -s 0 /etc/apt/sources.list \
    # 强制APT只允许当前系统稳定版，拒绝高版本trixie包
    && echo 'APT::Default-Release "stable";' > /etc/apt/apt.conf.d/00-lock-stable \
    # 腾讯云Debian稳定版内网源
    && echo "deb http://mirrors.tencentyun.com/debian stable main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb http://mirrors.tencentyun.com/debian stable-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    && echo "deb http://mirrors.tencentyun.com/debian-security stable-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list \
    # 缩短外网源超时，避免卡死
    && echo "Acquire::Retries \"2\";" > /etc/apt/apt.conf.d/99-speed \
    && echo "Acquire::http::Timeout \"6\";" >> /etc/apt/apt.conf.d/99-speed \
# --- 安装运行时依赖 ---
    && apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# pip腾讯云加速源
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ENV PIP_NO_CACHE_DIR=1

# --- 设置工作目录 ---
WORKDIR /app

# 分层优化：先拷贝依赖，缓存复用
COPY requirements.txt ./
# --- 安装 Python 依赖 ---
RUN pip install --no-cache-dir -r requirements.txt

# --- 复制项目文件 ---
COPY . .

# --- 预填充 SQLite 数据库 ---
RUN python3 scripts/prepare_db.py

# --- 验证数据库完整性 ---
RUN python3 -c "from engine.database import get_champion_count, get_augment_stats; c = get_champion_count(); a = get_augment_stats(); print(f'OK: {c} champs, {a.get(\"total\")} augments, curated {a.get(\"curated\")}, inferred {a.get(\"inferred\")}'); assert c > 0; assert a.get('total',0) > 0"

# --- 配置 gunicorn ---
ENV GUNICORN_WORKERS=4
ENV GUNICORN_TIMEOUT=120
ENV PORT=9001

# --- 暴露端口 ---
EXPOSE 9001

# --- 入口脚本 ---
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]