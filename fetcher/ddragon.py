"""
DDragon 数据抓取器
负责从Riot DDragon API获取英雄数据、技能数值
支持版本检测和缓存更新
将数据同时写入 JSON 缓存和 SQLite 数据库
"""
import json
import os
import time
import urllib.request
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DDragon, CDragon, CHAMPION_CACHE_DIR, DATA_DIR, CHAMPION_LIST_CACHE, VERSION_FILE
from engine.database import (
    upsert_champion, save_version_info as db_save_version,
    init_db, db_has_data, get_champion_count
)


def fetch_json(url, timeout=15, retries=2):
    """获取JSON数据，带重试"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            raise e


def get_latest_version():
    """获取DDragon最新版本号"""
    try:
        versions = fetch_json(DDragon["version_check_url"])
        return versions[0]  # 最新正式版本
    except:
        return None


def load_cached_version():
    """读取缓存的版本信息"""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {"ddragon_version": None, "last_updated": None, "champion_count": 0}


def save_version_info(version, count):
    """保存版本信息到 JSON 和数据库"""
    info = {
        "ddragon_version": version,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "champion_count": count,
    }
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    # 同时写入数据库
    try:
        init_db()
        db_save_version(
            ddragon_version=version,
            champion_count=count,
        )
    except Exception:
        pass
    return info


def get_champion_list(force_refresh=False):
    """获取英雄列表，优先使用缓存"""
    version_info = load_cached_version()
    current_version = get_latest_version()

    # 如果缓存存在且版本匹配，直接读缓存
    if (not force_refresh and os.path.exists(CHAMPION_LIST_CACHE)
            and version_info.get("ddragon_version") == current_version):
        with open(CHAMPION_LIST_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f), current_version

    # 否则重新拉取
    if current_version:
        url = f'{DDragon["cdn_url"]}/{current_version}/data/{DDragon["region"]}/champion.json'
        data = fetch_json(url)
        champ_list = {k: {
            "id": k,
            "name": v["name"],
            "title": v["title"],
            "blurb": v.get("blurb", ""),
            "tags": v.get("tags", []),
            "partype": v.get("partype", ""),
            "info": v.get("info", {}),
        } for k, v in data["data"].items()}

        # 按名称排序
        champ_list = dict(sorted(champ_list.items(), key=lambda x: x[1]["name"]))

        with open(CHAMPION_LIST_CACHE, 'w', encoding='utf-8') as f:
            json.dump(champ_list, f, ensure_ascii=False, indent=2)

        save_version_info(current_version, len(champ_list))
        return champ_list, current_version

    # 降级：返回缓存
    if os.path.exists(CHAMPION_LIST_CACHE):
        with open(CHAMPION_LIST_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f), version_info.get("ddragon_version", "unknown")
    return {}, None


def get_champion_detail(champion_id, version, force_refresh=False):
    """获取单个英雄的详细数据（技能、数值）"""
    cache_file = os.path.join(CHAMPION_CACHE_DIR, f"{champion_id}.json")

    if not force_refresh and os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
            if cached.get("_version") == version:
                return cached

    url = f'{DDragon["cdn_url"]}/{version}/data/{DDragon["region"]}/champion/{champion_id}.json'
    data = fetch_json(url)
    champ = data["data"][champion_id]

    # 解析并标准化技能数据
    result = {
        "_version": version,
        "_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "id": champion_id,
        "name": champ["name"],
        "title": champ["title"],
        "tags": champ.get("tags", []),
        "stats": champ.get("stats", {}),  # 基础属性
        "skills": {
            "passive": {
                "name": champ["passive"]["name"],
                "description": champ["passive"].get("description", ""),
                "icon": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/passive/{champ['passive']['image']['full']}" if 'image' in champ['passive'] else "",
            }
        }
    }

    # 解析4个基础技能
    spell_keys = ["Q", "W", "E", "R"]
    for i, spell in enumerate(champ.get("spells", [])[:4]):
        key = spell_keys[i]
        result["skills"][key.lower()] = {
            "name": spell["name"],
            "key": key,
            "description": spell.get("description", ""),
            "tooltip": spell.get("tooltip", ""),
            "icon": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/spell/{spell['image']['full']}" if 'image' in spell else "",
            "cooldown": spell.get("cooldown", []),
            "cost": spell.get("cost", []),
            "range": spell.get("range", []) if isinstance(spell.get("range"), list) else [spell.get("range", 0)],
            "maxrank": spell.get("maxrank", 5),
        }

    # 缓存到本地
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 同时写入数据库
    try:
        upsert_champion(
            champion_id=champion_id,
            name=result['name'],
            title=result['title'],
            tags=result['tags'],
            skills=result['skills'],
            stats=result.get('stats', {}),
            ddragon_version=version,
        )
    except Exception:
        pass

    return result


def get_cherry_augments(lang="zh_cn"):
    """从CDragon获取海克斯增幅数据"""
    url = f'{CDragon["base_url"]}/plugins/rcp-be-lol-game-data/global/{lang}/v1/cherry-augments.json'
    try:
        data = fetch_json(url, timeout=CDragon["timeout"])
        return data
    except:
        # 降级到英文
        try:
            url = f'{CDragon["base_url"]}/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json'
            return fetch_json(url, timeout=CDragon["timeout"])
        except:
            return []


def update_all_champions(version=None):
    """批量更新所有英雄数据"""
    if not version:
        version = get_latest_version()
    if not version:
        return {"error": "无法获取最新版本号"}

    champ_list, _ = get_champion_list(force_refresh=True)
    total = len(champ_list)
    success = 0
    errors = []

    for i, (cid, _) in enumerate(champ_list.items()):
        try:
            get_champion_detail(cid, version, force_refresh=True)
            success += 1
            if (i + 1) % 20 == 0:
                print(f"  进度: {i+1}/{total}")
        except Exception as e:
            errors.append({"champion": cid, "error": str(e)})

    return {
        "version": version,
        "total": total,
        "success": success,
        "errors": errors,
    }


if __name__ == "__main__":
    # 命令行测试
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        result = update_all_champions()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        v = get_latest_version()
        print(f"最新版本: {v}")
        cl, v2 = get_champion_list()
        print(f"英雄数: {len(cl)}")
        if cl:
            sample = list(cl.keys())[0]
            print(f"示例: {sample} -> {cl[sample]['name']}")
