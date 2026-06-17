#!/bin/bash
# 更新英雄数据脚本
# 用法: ./update_champions.sh

cd "$(dirname "$0")/.."
echo "🔄 正在更新英雄数据..."
python3 -c "
from fetcher.ddragon import update_all_champions, get_latest_version
v = get_latest_version()
print(f'最新DDragon版本: {v}')
result = update_all_champions(v)
print(f'更新完成: {result[\"success\"]}/{result[\"total\"]} 成功')
if result.get('errors'):
    print(f'错误: {len(result[\"errors\"])}个')
    for e in result['errors'][:5]:
        print(f'  - {e}')
"

# 更新版本文件
python3 -c "
import json, os
from fetcher.ddragon import get_latest_version, get_champion_list
v = get_latest_version()
cl, _ = get_champion_list()
info = {'ddragon_version': v, 'last_updated': __import__('time').strftime('%Y-%m-%d %H:%M:%S'), 'champion_count': len(cl)}
with open('data/version.json', 'w') as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
print(f'版本文件已更新: v{v}, {len(cl)}个英雄')
"
