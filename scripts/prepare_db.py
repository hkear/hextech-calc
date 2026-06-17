#!/usr/bin/env python3
"""
海克斯增幅计算器 - 数据预填充脚本

从 JSON 文件导入所有数据到 SQLite 数据库。
在 Docker 构建时和启动时调用。

流程：
  1. 初始化数据库表结构
  2. 导入 heroes (来自 champion_list.json + champions/ 目录)
  3. 导入增幅 (来自 augments_full.json)
  4. 导入计算规则 (来自 calc_rules.json)
  5. 导入版本历史 (来自 augment_versions.json)
  6. 保存版本信息
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DATA_DIR, CHAMPION_LIST_CACHE, CHAMPION_CACHE_DIR,
    AUGMENTS_FILE, CALC_RULES_FILE, VERSION_FILE,
    AUGMENT_VERSIONS_FILE, AUGMENTS_LEGACY_FILE,
)
from engine.database import (
    init_db, db_has_data, upsert_champion, upsert_augment,
    save_version_info, save_augment_version, save_calc_rules,
    set_meta, get_augment_count, get_champion_count,
)


def import_champions():
    """从 JSON 文件导入英雄数据到 SQLite"""
    print("\n📦 导入英雄数据...")

    # 1. 加载英雄列表
    if not os.path.exists(CHAMPION_LIST_CACHE):
        print(f"   ⚠️ 未找到英雄列表缓存: {CHAMPION_LIST_CACHE}")
        return 0

    with open(CHAMPION_LIST_CACHE, 'r', encoding='utf-8') as f:
        champ_list = json.load(f)

    print(f"   找到 {len(champ_list)} 个英雄")

    # 2. 逐个导入（优先使用详细缓存文件）
    imported = 0
    for cid, info in champ_list.items():
        # 尝试从 champions/ 目录加载详细数据
        detail_file = os.path.join(CHAMPION_CACHE_DIR, f"{cid}.json")
        skills = {}
        stats = {}
        ddragon_version = ''

        if os.path.exists(detail_file):
            with open(detail_file, 'r', encoding='utf-8') as f:
                detail = json.load(f)
            skills = detail.get('skills', {})
            stats = detail.get('stats', {})
            ddragon_version = detail.get('_version', '')

        upsert_champion(
            champion_id=cid,
            name=info.get('name', cid),
            title=info.get('title', ''),
            tags=info.get('tags', []),
            blurb=info.get('blurb', ''),
            partype=info.get('partype', ''),
            info=info.get('info', {}),
            skills=skills,
            stats=stats,
            ddragon_version=ddragon_version,
        )
        imported += 1

    print(f"   ✅ 导入 {imported} 个英雄")
    return imported


def import_augments():
    """从 augments_full.json 导入增幅数据"""
    print("\n📦 导入增幅数据...")

    if os.path.exists(AUGMENTS_FILE):
        source_file = AUGMENTS_FILE
    elif os.path.exists(AUGMENTS_LEGACY_FILE):
        source_file = AUGMENTS_LEGACY_FILE
    else:
        print(f"   ⚠️ 未找到增幅数据文件")
        return 0, 0, 0

    with open(source_file, 'r', encoding='utf-8') as f:
        db = json.load(f)

    augments = db.get('augments', {})
    meta = db.get('_meta', {})

    print(f"   找到 {len(augments)} 个增幅")

    imported = 0
    curated = 0
    inferred = 0

    for aid, a in augments.items():
        source = a.get('source', meta.get('source', 'inferred'))
        upsert_augment(
            augment_id=aid,
            name=a.get('name', aid),
            tier=a.get('tier', 'silver'),
            description=a.get('description', ''),
            effects=a.get('effects', []),
            calc_vars=a.get('calc_vars', {}),
            ability_affinity=a.get('ability_affinity', []),
            champion_affinity=a.get('champion_affinity', []),
            source=source,
        )
        imported += 1
        if 'curated' in source:
            curated += 1
        elif source == 'inferred':
            inferred += 1

    print(f"   ✅ 导入 {imported} 个增幅 (手工 {curated} + 推理 {inferred})")
    return imported, curated, inferred


def import_calc_rules():
    """导入计算规则"""
    print("\n📦 导入计算规则...")

    if not os.path.exists(CALC_RULES_FILE):
        print(f"   ⚠️ 未找到计算规则文件: {CALC_RULES_FILE}")
        return

    with open(CALC_RULES_FILE, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    save_calc_rules(rules)
    print(f"   ✅ 导入 {len([k for k in rules if k != '_meta'])} 个规则分类")


def import_version_history():
    """导入版本历史"""
    print("\n📦 导入版本历史...")

    if not os.path.exists(AUGMENT_VERSIONS_FILE):
        print(f"   ⚠️ 未找到版本历史文件")
        return 0

    with open(AUGMENT_VERSIONS_FILE, 'r', encoding='utf-8') as f:
        versions = json.load(f)

    count = 0
    for v in versions:
        save_augment_version(
            version_id=v.get('id', f"v_{count}"),
            version=v.get('version', '1.0.0'),
            ddragon_version=v.get('ddragon_version', ''),
            total=v.get('total', 0),
            curated=v.get('curated', 0),
            inferred=v.get('inferred', 0),
            created=v.get('created', ''),
        )
        count += 1

    print(f"   ✅ 导入 {count} 条版本记录")
    return count


def save_meta_info(champ_count, aug_count, curated, inferred):
    """保存版本元信息"""
    print("\n📦 保存版本信息...")

    # 读取版本文件
    ddragon_version = ''
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            vi = json.load(f)
        ddragon_version = vi.get('ddragon_version', '')

    save_version_info(
        ddragon_version=ddragon_version,
        champion_count=champ_count,
        augment_count=aug_count,
        curated_count=curated,
        inferred_count=inferred,
        extra={
            'engine_version': '2.0.0',
            'prepared_at': time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    set_meta('engine_version', '2.0.0')
    set_meta('prepared_at', time.strftime("%Y-%m-%d %H:%M:%S"))
    set_meta('source', 'docker')
    set_meta('auto_update_enabled', 'true')

    print(f"   ✅ 版本: {ddragon_version or 'unknown'}")


def main():
    print("=" * 60)
    print("  海克斯增幅计算器 - 数据预填充")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n🔧 初始化数据库...")
    init_db(force=True)
    print("   ✅ 数据库初始化完成")

    # 2. 导入英雄
    champ_count = import_champions()

    # 3. 导入增幅
    aug_count, curated, inferred = import_augments()

    # 4. 导入计算规则
    import_calc_rules()

    # 5. 导入版本历史
    import_version_history()

    # 6. 保存版本信息
    save_meta_info(champ_count, aug_count, curated, inferred)

    # 7. 总览
    print("\n" + "=" * 60)
    print("  📊 数据总览")
    print("=" * 60)
    print(f"  英雄: {champ_count} 位")
    print(f"  增幅: {aug_count} 个 (手工 {curated} + 推理 {inferred})")
    db_path = os.path.join(DATA_DIR, 'hextech_calc.db')
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    print(f"  数据库: {db_path}")
    print(f"  大小: {db_size / 1024:.1f} KB")
    print(f"\n✅ 数据预填充完成！")


if __name__ == '__main__':
    main()
