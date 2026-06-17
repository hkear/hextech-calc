"""
全量海克斯增幅数据管理
1. 从CDragon拉取全量637个增幅（中文名+英文名）
2. 合并已有的74个手工标定数据
3. 对剩余563个进行规则推理效果
4. 保存为全量数据库，带版本信息
"""
import json, os, sys, time, re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR

# ──── 1. 从CDragon获取全量数据 ────

def fetch_cdragon(lang="zh_cn"):
    """从CDragon抓取增幅数据"""
    import urllib.request
    url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/{lang}/v1/cherry-augments.json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())

# ──── 2. 加载已有机库 ────

def load_curated():
    """加载已有的手工标定数据"""
    path = os.path.join(DATA_DIR, "augments.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"augments": {}}

# ──── 3. 推理引擎（方案B） ────

def infer_effects(name_zh, name_en, tier='silver'):
    """基于名称推理增幅效果"""
    text_zh = name_zh.lower()
    text_en = name_en.lower()
    text = text_zh + " " + text_en
    
    effects = []
    calc_vars = {}
    ability_affinity = set()
    champion_affinity = set()
    description_parts = []
    
    # === 伤害类型推理 ===
    ap_keywords = ['法', '魔', '术', '咒', '奥术', 'arcane', 'mage', 'magic', 'sorcery', 'spell', '术士']
    ad_keywords = ['剑', '刃', '刀', '斩', '刺', '击', '弓', '弩', '枪', '剑士', 'blade', 'sword', 'sharpen', 'edge', 'arrow']
    true_dmg_keywords = ['真实', '真', 'true', '纯']
    fire_keywords = ['火', '焰', '爆', '灼', '燃', 'fire', 'flame', 'burn', 'blast', 'explos']
    ice_keywords = ['冰', '霜', '寒', '冻', 'ice', 'frost', 'freeze', 'cold']
    lightning_keywords = ['雷', '电', '闪', 'lightning', 'thunder', 'shock', 'volt']
    dark_keywords = ['暗', '影', '黑', '暗影', 'shadow', 'dark', 'void', 'gloom']
    holy_keywords = ['光', '圣', '神圣', 'light', 'holy', 'bless', 'divine']
    
    # === 技能类型推理 ===
    defense_keywords = ['盾', '甲', '壁', '护', '防', '韧', '钢铁', '盾牌', '坚', '石', 'shield', 'armor', 'defense', 'tough', 'stone', 'iron', 'steel']
    heal_keywords = ['疗', '回', '愈', '血', '命', '魂', '奶', 'heal', 'life', 'vamp', 'siphon', 'regen', 'blood']
    speed_keywords = ['速', '快', '疾', '风', '奔', '跑', 'speed', 'fast', 'quick', 'swift', 'haste', 'wind', 'rush']
    cc_keywords = ['晕', '眩', '冻', '缚', '缠', '困', '恐惧', '沉默', 'stun', 'slow', 'root', 'snare', 'fear', 'silence']
    aoe_keywords = ['范围', '扇', '圆', '爆', '波', '地', 'aoe', 'area', 'wave', 'explosion', 'nova']
    auto_keywords = ['击', '射', '弓', '弩', '枪', 'attack', 'strike', 'shot', 'auto', 'bow', 'gun']
    ultimate_keywords = ['终极', '大招', '大', '最终', 'ult', 'final', 'ultimate']
    
    passive_income_keywords = ['金', '钱', '币', 'gold', 'coin', '赚', '财', '富']
    item_keywords = ['装备', '道具', '商', '卖', '购', 'item', 'shop', 'buy', 'sell', 'discount']
    
    # === 英雄类型推理 ===
    mage_keywords = ['法', '巫', '术士', '奥术', 'magi', 'sorcer']
    assassin_keywords = ['刺', '杀', '暗', '影', 'assassin', 'shadow']
    fighter_keywords = ['战', '斗', '剑', '刃', '拳', 'fighter', 'warrior', 'blade', 'fist']
    tank_keywords = ['盾', '甲', '石', '巨', '牛', '熊', 'tank', 'goliath', 'giant', 'bear']
    marksman_keywords = ['射', '弓', '弩', '枪', 'mark', 'shot', 'sniper', 'gun']
    support_keywords = ['辅', '助', '奶', '护', 'support', 'heal', 'shield', 'protect']
    
    # 推理：伤害类型
    dmg_type = "physical" if any(k in text for k in ad_keywords) else "magic" if any(k in text for k in ap_keywords) else "mixed"
    
    # 推理：能力倾向
    if any(k in text for k in ap_keywords):
        ability_affinity.add('damage_ap')
        champion_affinity.add('mage')
    if any(k in text for k in ad_keywords):
        ability_affinity.add('damage_ad')
        champion_affinity.add('fighter')
    if any(k in text for k in defense_keywords):
        ability_affinity.add('defense')
        champion_affinity.add('tank')
    if any(k in text for k in heal_keywords):
        ability_affinity.add('heal_shield')
        champion_affinity.add('support')
    if any(k in text for k in speed_keywords):
        ability_affinity.add('mobility')
    if any(k in text for k in cc_keywords):
        ability_affinity.add('cc')
    if any(k in text for k in auto_keywords):
        ability_affinity.add('auto_attack')
        champion_affinity.add('marksman')
    if any(k in text for k in ultimate_keywords):
        ability_affinity.add('ultimate')
    if any(k in text for k in aoe_keywords):
        ability_affinity.add('aoe')
    
    # 如果啥都没命中，给默认
    if not ability_affinity:
        ability_affinity.add('damage_ad')
        ability_affinity.add('damage_ap')
    
    if not champion_affinity:
        champion_affinity.add('all')
    elif len(champion_affinity) > 2:
        champion_affinity.add('all')
    
    # 生成效果 - 改进推理引擎
    effect_bonus = 0
    tier_power = {'silver': 0.7, 'gold': 1.0, 'prismatic': 1.5, 'event': 0.8, 'bronze': 0.5}
    power = tier_power.get(tier, 1.0)
    
    # 元素/主题检测
    elemental_dmg = None
    if any(k in text for k in fire_keywords):
        elemental_dmg = 'fire'
    elif any(k in text for k in ice_keywords):
        elemental_dmg = 'ice'
    elif any(k in text for k in lightning_keywords):
        elemental_dmg = 'lightning'
    elif any(k in text for k in dark_keywords):
        elemental_dmg = 'dark'
    elif any(k in text for k in holy_keywords):
        elemental_dmg = 'holy'
    
    # 生成多重效果
    generated = False
    
    # 1) 伤害类效果
    if 'damage_ap' in ability_affinity and 'damage_ad' in ability_affinity:
        # 混合伤害
        dmg_amp = (0.08 + (hash(name_zh) % 8) / 100) * power
        effects.append({"type": "damage_amp", "subtype": "all_damage", "percent": round(dmg_amp, 2)})
        description_parts.append(f"全伤害+{int(dmg_amp*100)}%（推理）")
        generated = True
    elif 'damage_ap' in ability_affinity:
        if elemental_dmg:
            # 元素额外伤害
            base = int((20 + (hash(name_en) % 31)) * power)
            effects.append({
                "type": "attack_modifier", "subtype": f"elemental_{elemental_dmg}",
                "base": base, "damage_type": "magic",
                "description": f"命中时附带{base}点{elemental_dmg}属性魔法伤害（推理）"
            })
            description_parts.append(f"命中附带{base}点元素魔法伤害（推理）")
        else:
            ap_val = int((15 + (hash(name_zh) % 36)) * power)
            effects.append({"type": "flat_stat", "stat": "ap", "value": ap_val, "scaling": None})
            if 'ultimate' in ability_affinity:
                cd_amp = (0.10 + (hash(name_en) % 15) / 100) * power
                effects.append({"type": "cooldown_reduction", "subtype": "global", "target": "ultimate", "percent": round(cd_amp, 2)})
                description_parts.append(f"+{ap_val}AP; 大招CD-{int(cd_amp*100)}%（推理）")
            elif 'mobility' in ability_affinity:
                effects.append({"type": "flat_stat", "stat": "ability_haste", "value": 10 + (hash(name_zh) % 11)})
                description_parts.append(f"+{ap_val}AP（推理）")
            else:
                description_parts.append(f"+{ap_val}法术强度（推理）")
        generated = True
    
    if 'damage_ad' in ability_affinity or 'auto_attack' in ability_affinity:
        if 'auto_attack' in ability_affinity:
            spd = 0.10 + (hash(name_en) % 25) / 100
            effects.append({"type": "flat_stat", "stat": "attack_speed", "value": round(spd, 2)})
            if 'mobility' in ability_affinity:
                ms = 0.03 + (hash(name_zh) % 8) / 100
                effects.append({"type": "flat_stat", "stat": "move_speed", "value": round(ms, 2)})
                description_parts.append(f"+{int(spd*100)}%攻速; +{int(ms*100)}%移速（推理）")
            else:
                # 暴击或攻击特效
                crit = 0.10 + (hash(name_en) % 16) / 100
                effects.append({"type": "flat_stat", "stat": "crit_chance", "value": round(crit, 2)})
                description_parts.append(f"+{int(spd*100)}%攻速; +{int(crit*100)}%暴击（推理）")
        else:
            ad_val = 8 + (hash(name_zh) % 23)  # 8-30
            effects.append({"type": "flat_stat", "stat": "attack_damage", "value": ad_val, "scaling": None})
            description_parts.append(f"+{ad_val}攻击力（推理）")
        generated = True
    
    # 2) 防御类效果
    if 'defense' in ability_affinity:
        if 'cc' in ability_affinity:
            tenacity = 0.10 + (hash(name_zh) % 16) / 100
            effects.append({"type": "flat_stat", "stat": "tenacity", "value": round(tenacity, 2)})
            description_parts.append(f"韧性+{int(tenacity*100)}%（推理）")
        else:
            hp_val = 100 + (hash(name_zh) % 301)  # 100-400
            effects.append({"type": "flat_stat", "stat": "hp", "value": hp_val})
            description_parts.append(f"+{hp_val}生命值（推理）")
        generated = True
    
    # 3) 治疗/护盾类
    if 'heal_shield' in ability_affinity:
        heal_amp = 0.15 + (hash(name_en) % 20) / 100
        effects.append({"type": "heal_shield_boost", "subtype": "self", "value": round(heal_amp, 2)})
        if 'defense' in ability_affinity:
            shield = 50 + (hash(name_zh) % 101)
            effects.append({"type": "flat_stat", "stat": "hp", "value": shield})
            description_parts.append(f"治疗+{int(heal_amp*100)}%; +{shield}护盾（推理）")
        else:
            description_parts.append(f"治疗与护盾效果+{int(heal_amp*100)}%（推理）")
        generated = True
    
    # 4) 冷却缩减类
    if 'ultimate' in ability_affinity and not generated:
        cd_amp = 0.15 + (hash(name_zh) % 20) / 100
        effects.append({"type": "cooldown_reduction", "subtype": "global", "target": "ultimate", "percent": round(cd_amp, 2)})
        description_parts.append(f"大招冷却-{int(cd_amp*100)}%（推理）")
        generated = True
    
    # 5) 移速/机动类
    if 'mobility' in ability_affinity and not generated:
        ms = 0.05 + (hash(name_zh) % 10) / 100
        effects.append({"type": "flat_stat", "stat": "move_speed", "value": round(ms, 2)})
        description_parts.append(f"移动速度+{int(ms*100)}%（推理）")
        generated = True
    
    # 6) 特殊主题（任务型/特殊机制）
    if 'event' in [tier]:
        effects.append({"type": "special_effect", "subtype": "event", "description": "活动特殊增幅（推理）"})
        description_parts.append("活动特殊增幅效果（推理）")
        generated = True
    
    # 7) 兜底：通用技能急速
    if not generated:
        haste = 8 + (hash(name_zh) % 13)  # 8-20
        effects.append({"type": "flat_stat", "stat": "ability_haste", "value": haste})
        description_parts.append(f"+{haste}技能急速（推理）")
    
    # 生成描述文本
    if not description_parts:
        description = "效果待确认（AI推理）"
    else:
        description = "；".join(description_parts)
    
    return {
        "effects": effects,
        "calc_vars": {},
        "ability_affinity": list(ability_affinity),
        "champion_affinity": list(champion_affinity),
        "description": description,
        "source": "inferred",
    }


def tier_normalize(rarity):
    """标准化品阶"""
    mapping = {
        'kSilver': 'silver', 'kGold': 'gold', 'kPrismatic': 'prismatic',
        'kEventChoice': 'event', 'kBronze': 'bronze',
    }
    return mapping.get(rarity, rarity.lower())


# ──── 4. 主流程 ────

def build_full_database():
    """构建全量数据库"""
    print("=" * 60)
    print("  构建全量海克斯增幅数据库")
    print("=" * 60)
    
    # 拉取CDragon
    print("\n📡 从CDragon拉取数据...")
    zh_data = fetch_cdragon("zh_cn")
    en_data = fetch_cdragon("default")
    
    # 组织成 dict
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
    
    print(f"   CDragon中文: {len(zh_data)}个")
    print(f"   CDragon英文: {len(en_data)}个")
    print(f"   合并后: {len(cd_augments)}个唯一ID")
    
    # 加载已有数据
    curated = load_curated()
    curated_augments = curated.get('augments', {})
    print(f"   已有手工标定: {len(curated_augments)}个")
    
    # 统计
    tier_count = Counter()
    source_count = Counter()
    
    # 构建完整数据库
    full_augments = {}
    curated_by_name = {}
    for aid, a in curated_augments.items():
        curated_by_name[a.get('name', '')] = (aid, a)
    
    missing_curated = []
    
    for aid, info in cd_augments.items():
        name_zh = info['name_zh']
        name_en = info['name_en']
        tier = info['tier']
        
        if not name_zh and not name_en:
            continue
        
        tier_count[tier] += 1
        
        # 按中文名匹配手工数据（兼容CDragon ID不一致）
        matched_curated = curated_by_name.get(name_zh)
        
        if matched_curated:
            orig_id, curated_a = matched_curated
            entry = {
                "name": name_zh or name_en,
                "tier": tier,
                "description": curated_a.get('description', ''),
                "effects": curated_a.get('effects', []),
                "calc_vars": curated_a.get('calc_vars', {}),
                "ability_affinity": curated_a.get('ability_affinity', []),
                "champion_affinity": curated_a.get('champion_affinity', []),
                "source": "curated",
            }
            source_count['curated'] += 1
        else:
            # 推理
            if name_zh and name_en:
                inferred = infer_effects(name_zh, name_en, tier)
            elif name_zh:
                inferred = infer_effects(name_zh, name_zh, tier)
            else:
                inferred = infer_effects(name_en, name_en, tier)
            
            entry = {
                "name": name_zh or name_en,
                "tier": tier,
                "description": inferred['description'],
                "effects": inferred['effects'],
                "calc_vars": inferred['calc_vars'],
                "ability_affinity": inferred['ability_affinity'],
                "champion_affinity": inferred['champion_affinity'],
                "source": "inferred",
            }
            source_count['inferred'] += 1
        
        full_augments[aid] = entry
    
    # 添加手工库中CDragon没有的条目
    for name_zh, (orig_id, curated_a) in curated_by_name.items():
        if name_zh not in {info['name_zh'] for info in cd_augments.values()}:
            entry = {
                "name": name_zh,
                "tier": curated_a.get('tier', 'silver'),
                "description": curated_a.get('description', ''),
                "effects": curated_a.get('effects', []),
                "calc_vars": curated_a.get('calc_vars', {}),
                "ability_affinity": curated_a.get('ability_affinity', []),
                "champion_affinity": curated_a.get('champion_affinity', []),
                "source": "curated_extra",
            }
            full_augments[orig_id] = entry
            source_count['curated_extra'] = source_count.get('curated_extra', 0) + 1
    
    # 版本信息
    from fetcher.ddragon import get_latest_version
    ddragon_v = get_latest_version()
    
    db = {
        "_meta": {
            "version": "2.0.0",
            "ddragon_version": ddragon_v or "unknown",
            "cdragon_version": "latest",
            "total_augments": len(full_augments),
            "curated_count": source_count.get('curated', 0) + source_count.get('curated_extra', 0),
            "inferred_count": source_count.get('inferred', 0),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tier_distribution": dict(tier_count),
        },
        "augments": full_augments,
    }
    
    # 保存
    path = os.path.join(DATA_DIR, "augments_full.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 数据库已保存: {path}")
    print(f"   总计: {db['_meta']['total_augments']}个")
    print(f"   手工标定: {db['_meta']['curated_count']}个")
    print(f"   AI推理: {db['_meta']['inferred_count']}个")
    print(f"   品阶分布: {db['_meta']['tier_distribution']}")
    print(f"   DDragon版本: {db['_meta']['ddragon_version']}")
    
    # 同时生成版本列表文件
    versions = []
    versions_path = os.path.join(DATA_DIR, "augment_versions.json")
    if os.path.exists(versions_path):
        with open(versions_path, 'r', encoding='utf-8') as f:
            versions = json.load(f)
    
    # 用时间戳做版本号
    ver_id = time.strftime("%Y%m%d_%H%M%S")
    versions.append({
        "id": ver_id,
        "version": db['_meta']['version'],
        "ddragon_version": db['_meta']['ddragon_version'],
        "total": db['_meta']['total_augments'],
        "curated": db['_meta']['curated_count'],
        "inferred": db['_meta']['inferred_count'],
        "created": db['_meta']['last_updated'],
    })
    # 保留最近5个版本
    versions = versions[-5:]
    with open(versions_path, 'w', encoding='utf-8') as f:
        json.dump(versions, f, ensure_ascii=False, indent=2)
    
    print(f"   版本记录: {len(versions)}条")
    
    return db


if __name__ == "__main__":
    db = build_full_database()
    
    # 打印一些推理样本
    print(f"\n📋 推理样本（随机5个）:")
    import random
    inferred_items = [(aid, a) for aid, a in db['augments'].items() if a.get('source') == 'inferred']
    random.shuffle(inferred_items)
    for aid, a in inferred_items[:5]:
        print(f"  {a['name']:20s} ({a['tier']:10s}) → {a['description'][:60]}")
