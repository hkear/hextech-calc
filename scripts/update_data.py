#!/usr/bin/env python3
"""
海克斯增幅计算器 - 统一数据更新脚本

在 Docker 容器内运行时使用，从 API 获取最新数据并写入数据库。

用法：
  python3 scripts/update_data.py                     # 更新所有数据
  python3 scripts/update_data.py --champions         # 仅更新英雄
  python3 scripts/update_data.py --augments          # 仅更新增幅
  python3 scripts/update_data.py --status            # 查看数据状态
"""
import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATA_DIR, VERSION_FILE, AUGMENTS_FILE
from engine.database import (
    init_db, get_champion_count, get_augment_count,
    get_augment_stats, get_version_info,
    upsert_augment, save_version_info as db_save_version,
)


def status():
    """查看当前数据状态"""
    print("\n📊 数据状态")
    print("-" * 40)

    vi = get_version_info()
    if vi:
        print(f"  DDragon版本: {vi.get('ddragon_version', '-')}")
        print(f"  引擎版本: {vi.get('engine_version', '-')}")
        print(f"  最后更新: {vi.get('last_updated', '-')}")

    try:
        champ_count = get_champion_count()
        print(f"\n  英雄: {champ_count} 位")
    except Exception:
        print(f"\n  英雄: 未知")

    try:
        astats = get_augment_stats()
        tiers = astats.get('tier_distribution', {})
        print(f"  增幅: {astats.get('total', 0)} 个")
        print(f"    手工: {astats.get('curated', 0)}")
        print(f"    推理: {astats.get('inferred', 0)}")
        print(f"    品阶: {tiers}")
    except Exception:
        print(f"  增幅: 未知")

    # 数据库文件大小
    from config import DB_PATH
    if os.path.exists(DB_PATH):
        size_kb = os.path.getsize(DB_PATH) / 1024
        print(f"\n  数据库: {DB_PATH}")
        print(f"  大小: {size_kb:.1f} KB")


def update_champions():
    """更新英雄数据"""
    print("\n🔄 更新英雄数据...")
    from fetcher.ddragon import update_all_champions, get_latest_version, get_champion_list

    v = get_latest_version()
    if not v:
        print("  ❌ 无法获取版本号，网络可能不通")
        return False

    print(f"  最新DDragon版本: {v}")
    result = update_all_champions(v)

    success = result.get('success', 0)
    total = result.get('total', 0)
    errors = result.get('errors', [])

    print(f"  ✅ 更新完成: {success}/{total}")
    if errors:
        print(f"  ⚠️  {len(errors)} 个错误:")
        for e in errors[:3]:
            print(f"     - {e['champion']}: {e['error']}")

    return len(errors) == 0


def update_augments():
    """更新海克斯增幅数据"""
    print("\n🔄 更新海克斯增幅数据...")

    from fetcher.ddragon import get_cherry_augments
    from scripts.fetch_full_augments import infer_effects, tier_normalize

    # 拉取 CDragon 数据
    print("  📡 从CDragon拉取...")
    zh_data = get_cherry_augments('zh_cn')
    en_data = get_cherry_augments('default')

    if not zh_data:
        print("  ❌ CDragon 数据拉取失败")
        return False

    # 组织数据
    cd_augments = {}
    for a in zh_data:
        aid = a.get('augmentNameId', '')
        cd_augments[aid] = {
            'name_zh': a.get('nameTRA', '').strip(),
            'name_en': '',
            'tier': tier_normalize(a.get('rarity', '')),
        }
    for a in en_data:
        aid = a.get('augmentNameId', '')
        if aid in cd_augments:
            cd_augments[aid]['name_en'] = a.get('nameTRA', '').strip()

    print(f"  CDragon: {len(zh_data)} 中文 + {len(en_data)} 英文 = {len(cd_augments)} 唯一ID")

    # 加载手工标定
    curated_path = os.path.join(DATA_DIR, "augments.json")
    curated_augments = {}
    if os.path.exists(curated_path):
        with open(curated_path, 'r', encoding='utf-8') as f:
            curated_data = json.load(f)
        curated_augments = curated_data.get('augments', {})

    curated_by_name = {}
    for aid, a in curated_augments.items():
        curated_by_name[a.get('name', '')] = (aid, a)

    # 导入或推理每条数据
    curated_count = 0
    inferred_count = 0

    for aid, info in cd_augments.items():
        name_zh = info['name_zh']
        name_en = info['name_en']
        tier = info['tier']

        if not name_zh and not name_en:
            continue

        # 尝试匹配手工数据
        matched = curated_by_name.get(name_zh)

        if matched:
            _, curated_a = matched
            upsert_augment(
                augment_id=aid,
                name=name_zh or name_en,
                tier=tier,
                description=curated_a.get('description', ''),
                effects=curated_a.get('effects', []),
                calc_vars=curated_a.get('calc_vars', {}),
                ability_affinity=curated_a.get('ability_affinity', []),
                champion_affinity=curated_a.get('champion_affinity', []),
                source='curated',
            )
            curated_count += 1
        else:
            # AI推理
            if name_zh and name_en:
                inferred = infer_effects(name_zh, name_en, tier)
            elif name_zh:
                inferred = infer_effects(name_zh, name_zh, tier)
            else:
                inferred = infer_effects(name_en, name_en, tier)

            upsert_augment(
                augment_id=aid,
                name=name_zh or name_en,
                tier=tier,
                description=inferred['description'],
                effects=inferred['effects'],
                calc_vars=inferred.get('calc_vars', {}),
                ability_affinity=inferred['ability_affinity'],
                champion_affinity=inferred['champion_affinity'],
                source='inferred',
            )
            inferred_count += 1

    total = curated_count + inferred_count
    print(f"  ✅ 导入完成:")
    print(f"    手工: {curated_count}")
    print(f"    推理: {inferred_count}")
    print(f"    总计: {total}")

    # 保存版本记录
    print(f"\n  📝 保存版本记录...")
    from engine.database import save_augment_version
    ver_id = time.strftime("%Y%m%d_%H%M%S")
    save_augment_version(
        version_id=ver_id,
        version="2.0.0",
        ddragon_version=get_version_info().get('ddragon_version', ''),
        total=total,
        curated=curated_count,
        inferred=inferred_count,
        created=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    print(f"    版本: {ver_id}")

    # 同时保存 JSON（保持向后兼容）
    print(f"  💾 同步保存 JSON...")
    full_db = {
        "_meta": {
            "version": "2.0.0",
            "total_augments": total,
            "curated_count": curated_count,
            "inferred_count": inferred_count,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "augments": {},
    }
    from engine.database import get_all_augments
    for aid, a in get_all_augments().items():
        full_db['augments'][aid] = {
            'name': a.get('name', aid),
            'tier': a.get('tier', 'silver'),
            'description': a.get('description', ''),
            'effects': a.get('effects', []),
            'calc_vars': a.get('calc_vars', {}),
            'ability_affinity': a.get('ability_affinity', []),
            'champion_affinity': a.get('champion_affinity', []),
            'source': a.get('source', 'inferred'),
        }
    with open(AUGMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_db, f, ensure_ascii=False, indent=2)
    print(f"    JSON: {AUGMENTS_FILE} ({os.path.getsize(AUGMENTS_FILE)/1024:.0f} KB)")

    return True


def update_all():
    """全量更新"""
    print("=" * 50)
    print("  海克斯计算器 - 全量数据更新")
    print("=" * 50)

    init_db()

    ok1 = update_champions()
    ok2 = update_augments()

    # 更新版本信息
    from fetcher.ddragon import get_latest_version
    v = get_latest_version()
    if v:
        try:
            champ_count = get_champion_count()
            astats = get_augment_stats()
            db_save_version(
                ddragon_version=v,
                champion_count=champ_count,
                augment_count=astats.get('total', 0),
                curated_count=astats.get('curated', 0),
                inferred_count=astats.get('inferred', 0),
                extra={'last_full_update': time.strftime("%Y-%m-%d %H:%M:%S")},
            )
        except Exception:
            pass

    print("\n" + "=" * 50)
    if ok1 and ok2:
        print("  ✅ 全量更新完成！")
    else:
        print("  ⚠️ 更新完成（部分可能有错误）")
    print("=" * 50)

    return ok1 and ok2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='海克斯计算器数据更新')
    parser.add_argument('--champions', action='store_true', help='仅更新英雄数据')
    parser.add_argument('--augments', action='store_true', help='仅更新增幅数据')
    parser.add_argument('--status', action='store_true', help='查看数据状态')
    args = parser.parse_args()

    if args.status:
        status()
    elif args.champions:
        init_db()
        update_champions()
    elif args.augments:
        init_db()
        update_augments()
    else:
        update_all()
