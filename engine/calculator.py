"""
海克斯增幅计算引擎

核心计算逻辑：
1. 技能分类器 → 将英雄技能归入各类别
2. 增幅匹配器 → 将增幅效果映射到技能类别
3. 数值计算器 → 计算具体数值增益
4. 契合度评分 → 综合评分
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR, CHAMPION_CACHE_DIR, CALC_ENGINE, AUGMENTS_FILE, CALC_RULES_FILE
from engine.database import (
    get_all_augments as db_get_all_augments,
    get_augment_list_db as db_get_augment_list,
    search_augments_db as db_search_augments,
    get_augment_stats,
    get_augment_versions_db,
    get_calc_rules,
    get_version_info,
)


# ──── 数据加载（优先数据库，回退 JSON） ────

_loaded_augments = None
_loaded_augments_meta = None
_loaded_rules = None

def _load_augments(version_id=None):
    """加载增幅数据：优先数据库，回退 JSON 文件"""
    global _loaded_augments, _loaded_augments_meta
    if _loaded_augments is not None:
        return _loaded_augments

    # 优先从数据库加载
    try:
        augs = db_get_all_augments()
        if augs:
            stats = get_augment_stats()
            _loaded_augments = augs
            _loaded_augments_meta = {
                'total_augments': stats.get('total', len(augs)),
                'curated_count': stats.get('curated', 0),
                'inferred_count': stats.get('inferred', 0),
                'tier_distribution': stats.get('tier_distribution', {}),
            }
            # 补全版本信息
            vi = get_version_info()
            if vi:
                _loaded_augments_meta['version'] = vi.get('engine_version', '2.0.0')
                _loaded_augments_meta['ddragon_version'] = vi.get('ddragon_version', '')
                _loaded_augments_meta['last_updated'] = vi.get('last_updated', '')
            return _loaded_augments
    except Exception:
        pass

    # 回退：从 JSON 文件加载
    if os.path.exists(AUGMENTS_FILE):
        with open(AUGMENTS_FILE, 'r', encoding='utf-8') as f:
            db = json.load(f)
        _loaded_augments = db.get('augments', {})
        _loaded_augments_meta = db.get('_meta', {})
        return _loaded_augments

    _loaded_augments = {}
    _loaded_augments_meta = {}
    return _loaded_augments

def get_augment_meta():
    global _loaded_augments_meta
    if _loaded_augments_meta is None:
        _load_augments()
    return _loaded_augments_meta or {}

def get_augment_versions():
    """获取所有可用版本"""
    try:
        versions = get_augment_versions_db()
        if versions:
            return versions
    except Exception:
        pass
    # 回退 JSON
    versions_file = os.path.join(DATA_DIR, "augment_versions.json")
    if os.path.exists(versions_file):
        with open(versions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [{"id": "v1", "version": "1.0.0", "total": 0, "curated": 0, "inferred": 0, "created": "legacy"}]

def _load_rules():
    global _loaded_rules
    if _loaded_rules is not None:
        return _loaded_rules
    # 优先数据库
    try:
        rules = get_calc_rules()
        if rules:
            _loaded_rules = rules
            return _loaded_rules
    except Exception:
        pass
    # 回退 JSON
    if os.path.exists(CALC_RULES_FILE):
        with open(CALC_RULES_FILE, 'r', encoding='utf-8') as f:
            _loaded_rules = json.load(f)
    else:
        _loaded_rules = {}
    return _loaded_rules


# ──── 1. 技能分类器 ────

def classify_skill(name, description, tooltip="", is_ultimate=False, is_passive=False):
    """
    根据技能名称和描述，自动分类技能的属性
    返回技能特征向量
    """
    text = (name + " " + description + " " + tooltip).lower()
    tags = []

    # 伤害类型检测
    dmg_type = None
    if any(k in text for k in ['魔法伤害', 'ap伤害', '法术强度', 'ap']):
        dmg_type = 'magic'
        tags.append('damage_ap')
    if any(k in text for k in ['物理伤害', 'ad伤害', '攻击力', 'ad']):
        if dmg_type:
            dmg_type = 'hybrid'
        else:
            dmg_type = 'physical'
        tags.append('damage_ad')

    # 真实伤害
    if any(k in text for k in ['真实伤害', 'true damage']):
        tags.append('damage_true')

    # 技能类型
    if any(k in text for k in ['治疗', '回复', '恢复', 'heal', '生命值']):
        tags.append('heal_shield')
    if any(k in text for k in ['护盾', 'shield']):
        tags.append('heal_shield')
    if any(k in text for k in ['眩晕', 'stun', '减速', 'slow', '禁锢', 'root', '击飞', 'knock', '魅惑', 'charm', '恐惧', 'fear', '沉默', 'silence']):
        tags.append('cc')
    if any(k in text for k in ['位移', '冲刺', 'dash', '突进', '跳跃', '跳']):
        tags.append('mobility')
    if any(k in text for k in ['加速', '移速', 'move speed', '移动速度']):
        tags.append('mobility')
    if any(k in text for k in ['护甲', '魔抗', '双抗', '减伤', '伤害减免']):
        tags.append('defense')
    if any(k in text for k in ['范围', 'aoe', '扇形', '圆形', '所有敌人']):
        tags.append('aoe')

    if is_ultimate:
        tags.append('ultimate')

    # 默认从描述中提取
    if not tags and not is_passive:
        # 看是否有基础伤害描述
        if any(k in text for k in ['伤害', 'damage', '攻击']):
            tags.append('damage_ad')

    return list(set(tags))


def get_champion_skill_types(champion_data):
    """获取英雄所有技能的分类标签"""
    result = {}
    skills = champion_data.get('skills', {})

    skill_order = ['passive', 'q', 'w', 'e', 'r']
    for key in skill_order:
        sk = skills.get(key)
        if not sk:
            continue
        is_ult = (key == 'r')
        is_pas = (key == 'passive')
        tags = classify_skill(
            sk.get('name', ''),
            sk.get('description', ''),
            sk.get('tooltip', ''),
            is_ultimate=is_ult,
            is_passive=is_pas
        )
        result[key] = {
            'name': sk.get('name', key.upper()),
            'tags': tags,
            'icon': sk.get('icon', ''),
            'is_ultimate': is_ult,
            'is_passive': is_pas,
            'cooldown': sk.get('cooldown', []),
        }

    return result


# ──── 2. 增幅匹配器 ────

def get_augment_data():
    """获取所有增幅数据"""
    return _load_augments()


def get_augment_list(tier_filter=None):
    """获取增幅列表，可选按品阶过滤"""
    # 优先数据库
    try:
        db_list = db_get_augment_list(tier_filter)
        if db_list:
            return db_list
    except Exception:
        pass
    # 回退内存/JSON
    augments = get_augment_data()
    result = []
    for aid, a in augments.items():
        if tier_filter and a.get('tier') != tier_filter:
            continue
        result.append({
            'id': aid,
            'name': a.get('name', aid),
            'tier': a.get('tier', 'silver'),
            'description': a.get('description', ''),
            'champion_affinity': a.get('champion_affinity', []),
            'ability_affinity': a.get('ability_affinity', []),
        })
    return result


def match_augment_to_skills(augment_id, skill_types):
    """
    计算特定增幅对英雄各个技能的匹配度
    返回: {skill_key: match_score} (0-1)
    """
    augments = get_augment_data()
    augment = augments.get(augment_id)
    if not augment:
        return {k: 0.0 for k in skill_types}

    ability_affinity = augment.get('ability_affinity', [])
    effects = augment.get('effects', [])
    calc_vars = augment.get('calc_vars', {})

    # 如果 ability_affinity 包含 'all'，匹配所有技能
    if 'all' in ability_affinity:
        return {k: 0.8 for k in skill_types}

    scores = {}
    for sk_key, sk_info in skill_types.items():
        sk_tags = sk_info.get('tags', [])
        if not sk_tags:
            scores[sk_key] = 0.0
            continue

        # 计算重叠度
        common = set(ability_affinity) & set(sk_tags)
        if common:
            # 重叠度 = 公共标签数 / 最大标签数
            max_tags = max(len(ability_affinity), len(sk_tags))
            if max_tags == 0:
                scores[sk_key] = 0.0
            else:
                base_score = len(common) / max_tags

                # 特殊标签加权
                bonus = 0.0
                if sk_info.get('is_ultimate') and 'ultimate' in common:
                    bonus += 0.15
                if sk_info.get('is_passive') and any(t in ability_affinity for t in ['auto_attack']):
                    bonus += 0.1

                scores[sk_key] = min(base_score + bonus, 1.0)
        else:
            # 部分效果也可能间接辅助
            indirect = 0.0
            if any(e.get('type') in ['flat_stat', 'percent_stat'] for e in effects):
                # 属性增幅可能间接影响所有技能
                indirect = 0.15
            scores[sk_key] = indirect

    return scores


# ──── 3. 数值计算器 ────

def estimate_stat_boost(augment_id, champion_data):
    """
    估算增幅提供的属性提升
    返回: {stat_name: value_or_formula}
    """
    augments = get_augment_data()
    augment = augments.get(augment_id)
    if not augment:
        return {}

    effects = augment.get('effects', [])
    calc_vars = augment.get('calc_vars', {})
    boosts = {}

    for effect in effects:
        etype = effect.get('type', '')
        if etype == 'flat_stat':
            stat = effect.get('stat', '')
            value = effect.get('value', 0)
            scaling = effect.get('scaling', None)

            if scaling == 'per_level':
                level = CALC_ENGINE.get('default_champion_level', 18)
                value = value * level
            elif scaling == 'per_kill_assist':
                # 假设约15击杀/助攻
                value = value * 15

            boosts[stat] = boosts.get(stat, 0) + value

        elif etype == 'percent_stat':
            stat = effect.get('stat', '')
            value = effect.get('value', 0)
            boosts[f"{stat}_pct"] = boosts.get(f"{stat}_pct", 0) + value

        elif etype == 'damage_amp':
            subtype = effect.get('subtype', '')
            percent = effect.get('percent', 0)
            boosts[f"dmg_amp_{subtype}"] = percent

        elif etype == 'damage_conversion':
            percent = effect.get('percent', 0)
            frm = effect.get('from', '')
            to = effect.get('to', '')
            boosts[f"convert_{frm}_to_{to}"] = percent

        elif etype == 'cooldown_reduction':
            subtype = effect.get('subtype', '')
            target = effect.get('target', '')
            value = effect.get('value', 0)
            percent = effect.get('percent', 0)
            if percent:
                boosts[f"cdr_{target}_pct"] = percent
            else:
                boosts[f"cdr_{target}_flat"] = value

        elif etype == 'attack_modifier':
            subtype = effect.get('subtype', '')
            boosts[f"attack_{subtype}"] = True

    return boosts


def calculate_skill_damage_boost(augment_id, skill_key, skill_types, champion_data):
    """
    计算增幅对特定技能的数值增益
    返回: {boost_percent, description, details}
    """
    augments = get_augment_data()
    augment = augments.get(augment_id)
    if not augment:
        return {'boost_percent': 0, 'description': '无效果', 'details': {}}

    effects = augment.get('effects', [])
    calc_vars = augment.get('calc_vars', {})

    skill_info = skill_types.get(skill_key, {})
    skill_tags = skill_info.get('tags', [])

    # 匹配度（从匹配器获取）
    match_scores = match_augment_to_skills(augment_id, skill_types)
    match_score = match_scores.get(skill_key, 0)

    total_boost = 0.0
    descriptions = []
    details = {}

    for effect in effects:
        etype = effect.get('type', '')

        # 直接属性增益（通过技能加成间接提升）
        if etype == 'flat_stat':
            stat = effect.get('stat', '')
            value = effect.get('value', 0)

            if stat == 'ap' and 'damage_ap' in skill_tags:
                # 假设60%平均AP加成 + 技能基准伤害300
                avg_ratio = 0.6
                scaling = effect.get('scaling', None)
                if scaling == 'per_level':
                    value = value * CALC_ENGINE.get('default_champion_level', 18)
                elif scaling == 'per_kill_assist':
                    value = value * 15  # 假设15个击杀/助攻
                skill_dmg_boost = value * avg_ratio / 300
                total_boost += skill_dmg_boost
                descriptions.append(f"+{value}AP")

            elif stat == 'attack_damage' and 'damage_ad' in skill_tags:
                avg_ratio = 0.7
                skill_dmg_boost = value * avg_ratio / 200
                total_boost += skill_dmg_boost
                descriptions.append(f"+{value}AD")

            elif stat == 'attack_speed' and ('auto_attack' in skill_tags or 'damage_ad' in skill_tags):
                pct = value * 100
                damage_boost = value * 0.6  # 攻速转dps估算
                total_boost += damage_boost
                descriptions.append(f"+{pct:.0f}%攻速")

            elif stat == 'ability_haste' and skill_key != 'passive':
                cdr_boost = value / (value + 100) * 0.5  # 冷却转伤害频率估算
                total_boost += cdr_boost * 0.3
                descriptions.append(f"+{value}技能急速")

            elif stat == 'hp':
                if 'defense' in skill_tags:
                    total_boost += 0.15
                descriptions.append(f"+{value}HP")

        # 伤害增幅
        elif etype == 'damage_amp':
            percent = effect.get('percent', 0)
            subtype = effect.get('subtype', '')
            penalty = effect.get('penalty', '')

            if subtype == 'all_damage':
                total_boost += percent
                descriptions.append(f"全伤害+{percent*100:.0f}%")
            elif subtype == 'basic_skills' and not skill_info.get('is_ultimate'):
                total_boost += percent
                if penalty == 'no_ultimate':
                    descriptions.append(f"QWE+{percent*100:.0f}%(大招禁用)")
                else:
                    descriptions.append(f"基础技能+{percent*100:.0f}%")
            elif subtype == 'ultimate_only' and skill_info.get('is_ultimate'):
                total_boost += percent
                descriptions.append(f"大招+{percent*100:.0f}%")
            elif subtype == 'specific_skill':
                target = effect.get('target', '')
                if target == skill_key:
                    total_boost += percent
                    descriptions.append(f"此技能+{percent*100:.0f}%")
            elif subtype == 'vs_larger_enemy':
                total_boost += percent * 0.5  # 条件触发估半
                descriptions.append(f"打大体积最多+{percent*100:.0f}%")

        # 伤害转换
        elif etype == 'damage_conversion':
            percent = effect.get('percent', 0)
            frm = effect.get('from', '')
            to = effect.get('to', '')
            convert_label = {'physical': '物理', 'magic': '魔法', 'true': '真伤'}
            frm_label = convert_label.get(frm, frm)
            to_label = convert_label.get(to, to)

            total_boost += percent * 0.35  # 混合伤害收益
            descriptions.append(f"{percent*100:.0f}%{frm_label}→{to_label}")

        # 冷却缩减
        elif etype == 'cooldown_reduction':
            target = effect.get('target', '')
            value = effect.get('value', 0)
            percent = effect.get('percent', 0)

            if target == skill_key or (target == 'ultimate' and skill_info.get('is_ultimate')):
                if percent:
                    total_boost += percent * 0.5
                    descriptions.append(f"冷却-{percent*100:.0f}%")
                elif value:
                    total_boost += min(value * 0.05, 1.0) * 0.3
                    descriptions.append(f"CD-{value}秒")

        # 攻击特效
        elif etype == 'attack_modifier':
            if 'auto_attack' in skill_tags or 'damage_ad' in skill_tags:
                subtype = effect.get('subtype', '')
                if subtype == 'extra_projectile':
                    dmg_pct = effect.get('damage_percent', 0.75)
                    total_boost += dmg_pct * 0.5
                    descriptions.append(f"普攻+{dmg_pct*100:.0f}%额外弹体")
                elif subtype == 'dual_wield':
                    hits = effect.get('hit_count', 2)
                    dmg_per = effect.get('damage_per_hit', 0.6)
                    effective = hits * dmg_per - 1
                    total_boost += effective * 0.4
                    descriptions.append(f"双持普攻({hits}×{dmg_per*100:.0f}%)")
                elif subtype == 'bounce':
                    bounces = effect.get('bounce_count', 2)
                    dmg_pct = effect.get('bounce_damage_percent', 0.4)
                    total_boost += bounces * dmg_pct * 0.2
                    descriptions.append(f"弹射{bounces}个(+{dmg_pct*100:.0f}%)")
                elif subtype == 'max_hp_true_damage':
                    hp_pct = effect.get('percent', 0.04)
                    total_boost += hp_pct * 300 * 0.01  # 假设3000血目标
                    descriptions.append(f"+{hp_pct*100:.1f}%最大生命值真伤")
                else:
                    total_boost += 0.1
                    descriptions.append(f"触发{effect.get('subtype', '特效')}")

        # 大招特化
        elif etype == 'ultimate_boost' and skill_info.get('is_ultimate'):
            total_boost += 0.3
            descriptions.append(f"大招强化")
            subtype = effect.get('subtype', '')
            if subtype == 'unstoppable':
                descriptions.append(f"不可阻挡{effect.get('duration', 3)}秒")

        # 攻防增益
        elif etype == 'defense_boost' and 'defense' in skill_tags:
            descriptions.append(f"防御强化")

    # 应用匹配度加权
    final_boost = total_boost * match_score

    if not descriptions:
        descriptions = ['无明显增益']

    return {
        'boost_percent': round(final_boost * 100, 1),
        'raw_boost': round(total_boost, 3),
        'match_score': round(match_score, 2),
        'description': '; '.join(descriptions),
        'details': descriptions,
    }


# ──── 4. 综合评分 ────

def calculate_synergy_score(augment_id, skill_types, champion_data):
    """
    计算增幅与英雄的综合契合度
    返回: {total_score (0-10), breakdown, recommendation}
    """
    augments = get_augment_data()
    augment = augments.get(augment_id)
    if not augment:
        return {'total_score': 0, 'breakdown': {}, 'recommendation': '不推荐'}

    match_scores = match_augment_to_skills(augment_id, skill_types)
    tier = augment.get('tier', 'silver')
    ability_affinity = augment.get('ability_affinity', [])
    champion_affinity = augment.get('champion_affinity', [])

    champion_tags = [t.lower() for t in champion_data.get('tags', [])]
    champion_affinity_lower = [t.lower() for t in champion_affinity]
    champion_tags_lower = [t.lower() for t in champion_tags]

    # 维度1: 技能覆盖度
    skill_match = sum(match_scores.values()) / max(len(match_scores), 1)
    skill_match_score = skill_match * 10

    # 维度2: 数值增幅幅度
    total_stat_boost = 0
    for sk in skill_types:
        calc = calculate_skill_damage_boost(augment_id, sk, skill_types, champion_data)
        total_stat_boost += calc.get('raw_boost', 0)
    # 平均增幅 × 10 换算，最高10分
    avg_boost = total_stat_boost / max(len(skill_types), 1)
    stat_boost_score = min(avg_boost * 20, 10)

    # 维度3: 特殊效果价值
    effect_count = len(augment.get('effects', []))
    special_score = min(effect_count * 0.5, 5)
    if tier == 'prismatic':
        special_score += 2
    elif tier == 'gold':
        special_score += 1

    # 维度4: 品阶基础强度
    tier_scores = {'silver': 3, 'gold': 6, 'prismatic': 9}
    tier_score = tier_scores.get(tier, 5)

    # 维度5: 英雄契合度
    affinity_score = 5
    if champion_affinity:
        common_affinity = set(champion_affinity_lower) & set(champion_tags_lower)
        if 'all' in champion_affinity_lower:
            affinity_score = 7
        elif common_affinity:
            affinity_score = 5 + min(len(common_affinity) * 1.5, 5)
        else:
            affinity_score = 2

    # 加权总分
    weights = CALC_ENGINE.get('synergy_weights', {
        'skill_match': 0.35,
        'stat_boost': 0.30,
        'special_effect': 0.20,
        'tier_power': 0.15,
    })

    total = (
        skill_match_score * weights['skill_match'] +
        stat_boost_score * weights['stat_boost'] +
        special_score * weights['special_effect'] +
        tier_score * weights['tier_power']
    )

    # 额外：英雄契合度加权
    total = total * (affinity_score / 5)

    total = round(min(total, 10), 1)

    # 推荐等级
    if total >= 8:
        rec = '🏆 强烈推荐！完美契合'
    elif total >= 6:
        rec = '✅ 推荐，效果不错'
    elif total >= 4:
        rec = '⚠️ 可用，但非最优'
    else:
        rec = '❌ 不推荐，效果微弱'

    return {
        'total_score': total,
        'breakdown': {
            'skill_match': round(skill_match_score, 1),
            'stat_boost': round(stat_boost_score, 1),
            'special_effect': round(special_score, 1),
            'tier': round(tier_score, 1),
            'affinity': round(affinity_score, 1),
        },
        'recommendation': rec,
    }


# ──── 5. 全计算入口 ────

def calculate_full(champion_data, augment_ids):
    """
    完整计算：英雄 + 4个增幅 → 全部分析结果
    """
    # 1. 分类英雄技能
    skill_types = get_champion_skill_types(champion_data)

    # 2. 获取增幅数据
    augments = get_augment_data()

    # 3. 对每个增幅进行计算
    results = {}
    for aid in augment_ids[:4]:  # 最多4个
        augment = augments.get(aid)
        if not augment:
            continue

        # 每个技能的增益
        skill_boosts = {}
        for sk_key in skill_types:
            skill_boosts[sk_key] = calculate_skill_damage_boost(
                aid, sk_key, skill_types, champion_data
            )

        # 总分
        synergy = calculate_synergy_score(aid, skill_types, champion_data)

        results[aid] = {
            'augment_name': augment.get('name', aid),
            'augment_tier': augment.get('tier', 'silver'),
            'augment_description': augment.get('description', ''),
            'effects': augment.get('effects', []),
            'calc_vars': augment.get('calc_vars', {}),
            'stat_boosts': estimate_stat_boost(aid, champion_data),
            'skill_boosts': skill_boosts,
            'synergy': synergy,
            'match_scores': match_augment_to_skills(aid, skill_types),
        }

    # 4. 排序推荐
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1]['synergy']['total_score'],
        reverse=True
    )

    return {
        'champion': {
            'id': champion_data.get('id', ''),
            'name': champion_data.get('name', ''),
            'title': champion_data.get('title', ''),
            'tags': champion_data.get('tags', []),
        },
        'skills': {
            sk: {
                'name': info['name'],
                'tags': info['tags'],
                'icon': info.get('icon', ''),
                'is_ultimate': info.get('is_ultimate', False),
                'is_passive': info.get('is_passive', False),
            }
            for sk, info in skill_types.items()
        },
        'results': results,
        'ranking': [{
            'id': aid,
            'name': r['augment_name'],
            'tier': r['augment_tier'],
            'total_score': r['synergy']['total_score'],
            'recommendation': r['synergy']['recommendation'],
            'breakdown': r['synergy']['breakdown'],
        } for aid, r in sorted_results],
        'engine_version': CALC_ENGINE.get('version', '1.0.0'),
        'engine_config': {
            'default_level': CALC_ENGINE.get('default_champion_level', 18),
            'default_skill_level': CALC_ENGINE.get('default_skill_level', 5),
        }
    }


def get_random_augments(count=4, tier_filter=None):
    """随机获取几个增幅"""
    import random
    all_aug = get_augment_list(tier_filter)
    if len(all_aug) <= count:
        return all_aug
    return random.sample(all_aug, count)


def search_augments(keyword, limit=20):
    """搜索增幅"""
    # 优先数据库
    try:
        db_results = db_search_augments(keyword, limit)
        if db_results:
            return db_results
    except Exception:
        pass
    # 回退内存
    all_aug = get_augment_list()
    keyword = keyword.lower()
    matches = [
        a for a in all_aug
        if keyword in a['name'].lower() or keyword in a.get('description', '').lower()
    ]
    return matches[:limit]
