#!/bin/bash
# =================================================
# 海克斯增幅计算器 - Docker 入口脚本
# =================================================
set -e

echo "============================================"
echo "  🚀 海克斯增幅计算器 v2.0.0"
echo "============================================"

# 确保数据库存在
DB_FILE="/app/data/hextech_calc.db"
if [ ! -f "$DB_FILE" ]; then
    echo "🔧 数据库不存在，正在预填充..."
    python3 /app/scripts/prepare_db.py
    echo "✅ 数据库就绪"
fi

# 启动时检查更新（可选）
if [ "${AUTO_UPDATE:-true}" = "true" ]; then
    echo ""
    echo "🔍 检查数据更新..."
    python3 /app/scripts/update_data.py --status 2>/dev/null || true
    echo ""
fi

# 数据持久化：如果挂载了 /data 目录，复制数据库到持久卷
if [ -d "/data" ] && [ ! -f "/data/hextech_calc.db" ]; then
    echo "💾 复制数据库到持久卷 /data..."
    cp "$DB_FILE" /data/hextech_calc.db
    echo "✅ 已复制"
fi

# 从持久卷恢复数据库
if [ -d "/data" ] && [ -f "/data/hextech_calc.db" ]; then
    echo "🔄 从持久卷加载数据库..."
    cp /data/hextech_calc.db "$DB_FILE"
    echo "✅ 已加载"
fi

# 显示版本信息
echo ""
python3 -c "
from engine.database import get_version_info, get_champion_count, get_augment_stats
vi = get_version_info()
print(f'📊 DDragon版本: {vi.get(\"ddragon_version\", \"-\")}')
print(f'📊 英雄数: {get_champion_count()}')
astats = get_augment_stats()
print(f'📊 增幅数: {astats.get(\"total\", 0)} (手工 {astats.get(\"curated\", 0)} + 推理 {astats.get(\"inferred\", 0)})')
print(f'📊 引擎版本: {vi.get(\"engine_version\", \"2.0.0\")}')
print(f'📊 最后更新: {vi.get(\"last_updated\", \"-\")}')
"

echo ""
echo "============================================"
echo "  ✅ 服务启动中..."
echo "  端口: ${PORT:-9001}"
echo "  工作进程: ${GUNICORN_WORKERS:-4}"
echo "============================================"
echo ""

# 启动 gunicorn
exec gunicorn \
    --workers ${GUNICORN_WORKERS:-4} \
    --bind 0.0.0.0:${PORT:-9001} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app
