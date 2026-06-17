#!/bin/bash
# 全量更新：英雄数据 + 海克斯数据
cd "$(dirname "$0")/.."

echo "==================================="
echo "  🔄 海克斯计算器 - 全量数据更新"
echo "==================================="

# 1. 更新英雄数据
echo ""
echo "📦 [1/3] 更新英雄数据..."
bash scripts/update_champions.sh

# 2. 更新海克斯增幅数据
echo ""
echo "📦 [2/3] 更新海克斯增幅数据..."
python3 -c "
import json
from fetcher.ddragon import get_cherry_augments

# 获取中文数据
zh_data = get_cherry_augments('zh_cn')
print(f'CDragon中文增幅数: {len(zh_data)}')

# 获取英文数据（用于补充）
en_data = get_cherry_augments('default')
print(f'CDragon英文增幅数: {len(en_data)}')

# 统计品阶分布
from collections import Counter
tiers = Counter(a.get('rarity', 'unknown') for a in zh_data)
print(f'品阶分布: {dict(tiers)}')
"

# 3. 更新版本时间戳
echo ""
echo "📦 [3/3] 更新版本记录..."
python3 -c "
import json, time
info = {
    'last_full_update': time.strftime('%Y-%m-%d %H:%M:%S'),
    'update_type': 'full',
}
with open('data/version.json', 'r+') as f:
    try:
        existing = json.load(f)
    except:
        existing = {}
    existing['last_full_update'] = info['last_full_update']
    f.seek(0)
    json.dump(existing, f, ensure_ascii=False, indent=2)
    f.truncate()
print('✓ 完成')
"

echo ""
echo "✅ 全量更新完成！"
echo "   时间: $(date)"
echo "   如需重启应用: systemctl restart hextech-calc (如果已配置)"
echo "   或: pkill -f 'python3 app.py'; python3 app.py &"
