#!/bin/bash
# 海克斯增幅计算器 - 启动脚本
# Docker: docker compose up -d
# 本地: bash start.sh

cd "$(dirname "$0")"

# 判断是否在 Docker 内
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "🐳 Docker 环境"
    # 数据库已在构建时预填充
    exec python3 app.py
    exit
fi

echo "============================================"
echo "  海克斯增幅计算器 v2.0.0"
echo "============================================"
echo ""
echo "📌 Docker 启动（推荐）:"
echo "   docker build -t hextech-calc ."
echo "   docker compose up -d"
echo ""
echo "📌 本地启动:"
echo "   python3 scripts/prepare_db.py"
echo "   python3 app.py"
echo ""
echo "📌 数据更新:"
echo "   python3 scripts/update_data.py"
echo ""

# 检查数据库
if [ ! -f "data/hextech_calc.db" ]; then
    echo "🔧 预填充数据库..."
    python3 scripts/prepare_db.py
fi

# 启动
echo "🚀 启动服务..."
python3 app.py
