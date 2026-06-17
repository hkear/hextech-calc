"""
海克斯增幅计算器 - SQLite 数据库层

所有数据读写统一通过此模块访问。
支持 JSON 回退：如果数据库不存在或无数据，自动从 JSON 文件读取。
"""
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR, DB_PATH, CHAMPION_CACHE_DIR


# ──── 连接管理 ────

@contextmanager
def get_db():
    """获取数据库连接（上下文管理器，自动提交关闭）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──── 表结构 ────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ddragon_version TEXT,
    engine_version TEXT DEFAULT '2.0.0',
    champion_count INTEGER DEFAULT 0,
    augment_count INTEGER DEFAULT 0,
    curated_count INTEGER DEFAULT 0,
    inferred_count INTEGER DEFAULT 0,
    last_updated TEXT,
    extra TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS champions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    blurb TEXT DEFAULT '',
    partype TEXT DEFAULT '',
    info TEXT DEFAULT '{}',
    skills_json TEXT DEFAULT '{}',
    stats_json TEXT DEFAULT '{}',
    ddragon_version TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS augments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'silver',
    description TEXT DEFAULT '',
    effects_json TEXT DEFAULT '[]',
    calc_vars_json TEXT DEFAULT '{}',
    ability_affinity_json TEXT DEFAULT '[]',
    champion_affinity_json TEXT DEFAULT '[]',
    source TEXT DEFAULT 'inferred',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS augment_versions (
    id TEXT PRIMARY KEY,
    version TEXT,
    ddragon_version TEXT,
    total INTEGER,
    curated INTEGER,
    inferred INTEGER,
    created TEXT
);

CREATE TABLE IF NOT EXISTS calc_rules (
    section TEXT,
    key TEXT,
    value_json TEXT,
    PRIMARY KEY (section, key)
);

CREATE INDEX IF NOT EXISTS idx_augments_tier ON augments(tier);
CREATE INDEX IF NOT EXISTS idx_augments_name ON augments(name);
CREATE INDEX IF NOT EXISTS idx_augments_source ON augments(source);
CREATE INDEX IF NOT EXISTS idx_champions_name ON champions(name);
"""


# ──── 初始化 ────

def init_db(force=False):
    """初始化数据库表结构"""
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    with get_db() as db:
        for stmt in SCHEMA_SQL.split(';'):
            stmt = stmt.strip()
            if stmt:
                db.execute(stmt)
    return True


def db_has_data():
    """检查数据库是否已有数据"""
    try:
        with get_db() as db:
            row = db.execute("SELECT COUNT(*) as c FROM champions").fetchone()
            return row['c'] > 0
    except Exception:
        return False


# ──── 版本信息 ────

def get_version_info():
    """获取版本信息"""
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM version_info ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return dict(row)
    except Exception:
        pass
    return {}


def save_version_info(ddragon_version=None, champion_count=0, augment_count=0,
                      curated_count=0, inferred_count=0, extra=None):
    """保存版本信息"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("""
            INSERT INTO version_info
                (ddragon_version, champion_count, augment_count,
                 curated_count, inferred_count, last_updated, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ddragon_version or '',
            champion_count,
            augment_count,
            curated_count,
            inferred_count,
            now,
            json.dumps(extra or {}, ensure_ascii=False),
        ))
    return True


# ──── 英雄 ────

def upsert_champion(champion_id, name, title='', tags=None, blurb='',
                    partype='', info=None, skills=None, stats=None,
                    ddragon_version=''):
    """插入或更新英雄数据"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO champions
                (id, name, title, tags, blurb, partype, info,
                 skills_json, stats_json, ddragon_version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            champion_id, name, title,
            json.dumps(tags or [], ensure_ascii=False),
            blurb, partype or '',
            json.dumps(info or {}, ensure_ascii=False),
            json.dumps(skills or {}, ensure_ascii=False),
            json.dumps(stats or {}, ensure_ascii=False),
            ddragon_version or '',
            now,
        ))
    return True


def get_champion(champion_id):
    """获取单个英雄数据（含技能JSON解析）"""
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM champions WHERE id = ?", (champion_id,)
            ).fetchone()
            if row:
                return _row_to_champion(row)
    except Exception:
        pass
    return None


def get_champion_list_db():
    """获取英雄列表"""
    try:
        with get_db() as db:
            rows = db.execute(
                "SELECT id, name, title, tags, partype FROM champions ORDER BY name"
            ).fetchall()
            result = {}
            for row in rows:
                result[row['id']] = {
                    'id': row['id'],
                    'name': row['name'],
                    'title': row['title'],
                    'tags': json.loads(row['tags'] or '[]'),
                    'partype': row['partype'] or '',
                }
            return result
    except Exception:
        return {}


def get_champion_count():
    """英雄总数"""
    try:
        with get_db() as db:
            row = db.execute("SELECT COUNT(*) as c FROM champions").fetchone()
            return row['c']
    except Exception:
        return 0


def _row_to_champion(row):
    """将数据库行转为英雄字典"""
    skills = json.loads(row['skills_json'] or '{}')
    stats = json.loads(row['stats_json'] or '{}')
    return {
        'id': row['id'],
        'name': row['name'],
        'title': row['title'],
        'tags': json.loads(row['tags'] or '[]'),
        'blurb': row['blurb'] or '',
        'partype': row['partype'] or '',
        'info': json.loads(row['info'] or '{}'),
        'skills': skills,
        'stats': stats,
        'ddragon_version': row['ddragon_version'] or '',
    }


# ──── 增幅 ────

def upsert_augment(augment_id, name, tier='silver', description='',
                   effects=None, calc_vars=None,
                   ability_affinity=None, champion_affinity=None,
                   source='inferred'):
    """插入或更新增幅数据"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO augments
                (id, name, tier, description, effects_json, calc_vars_json,
                 ability_affinity_json, champion_affinity_json, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            augment_id, name, tier, description,
            json.dumps(effects or [], ensure_ascii=False),
            json.dumps(calc_vars or {}, ensure_ascii=False),
            json.dumps(ability_affinity or [], ensure_ascii=False),
            json.dumps(champion_affinity or [], ensure_ascii=False),
            source, now,
        ))
    return True


def get_augment(augment_id):
    """获取单个增幅"""
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM augments WHERE id = ?", (augment_id,)
            ).fetchone()
            if row:
                return _row_to_augment(row)
    except Exception:
        pass
    return None


def get_all_augments():
    """获取所有增幅（dict格式）"""
    try:
        with get_db() as db:
            rows = db.execute("SELECT * FROM augments").fetchall()
            result = {}
            for row in rows:
                result[row['id']] = _row_to_augment(row)
            return result
    except Exception:
        return {}


def get_augment_list_db(tier_filter=None):
    """获取增幅列表"""
    try:
        with get_db() as db:
            if tier_filter:
                rows = db.execute(
                    "SELECT id, name, tier, description, ability_affinity_json, champion_affinity_json FROM augments WHERE tier = ? ORDER BY name",
                    (tier_filter,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id, name, tier, description, ability_affinity_json, champion_affinity_json FROM augments ORDER BY name"
                ).fetchall()
            result = []
            for row in rows:
                result.append({
                    'id': row['id'],
                    'name': row['name'],
                    'tier': row['tier'],
                    'description': row['description'] or '',
                    'ability_affinity': json.loads(row['ability_affinity_json'] or '[]'),
                    'champion_affinity': json.loads(row['champion_affinity_json'] or '[]'),
                })
            return result
    except Exception:
        return []


def get_augment_count():
    """增幅总数"""
    try:
        with get_db() as db:
            row = db.execute("SELECT COUNT(*) as c FROM augments").fetchone()
            return row['c']
    except Exception:
        return 0


def get_augment_stats():
    """增幅统计信息"""
    try:
        with get_db() as db:
            total = db.execute("SELECT COUNT(*) as c FROM augments").fetchone()['c']
            curated = db.execute("SELECT COUNT(*) as c FROM augments WHERE source = 'curated' OR source = 'curated_extra'").fetchone()['c']
            inferred = db.execute("SELECT COUNT(*) as c FROM augments WHERE source = 'inferred'").fetchone()['c']
            tiers = {}
            for tier_name in ['silver', 'gold', 'prismatic', 'event', 'bronze']:
                row = db.execute(
                    "SELECT COUNT(*) as c FROM augments WHERE tier = ?", (tier_name,)
                ).fetchone()
                if row['c'] > 0:
                    tiers[tier_name] = row['c']
            return {
                'total': total,
                'curated': curated,
                'inferred': inferred,
                'tier_distribution': tiers,
            }
    except Exception:
        return {'total': 0, 'curated': 0, 'inferred': 0, 'tier_distribution': {}}


def search_augments_db(keyword, limit=20):
    """搜索增幅"""
    try:
        with get_db() as db:
            like = f"%{keyword}%"
            rows = db.execute("""
                SELECT id, name, tier, description, ability_affinity_json, champion_affinity_json
                FROM augments
                WHERE name LIKE ? OR description LIKE ?
                ORDER BY
                    CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                    name
                LIMIT ?
            """, (like, like, like, limit)).fetchall()
            result = []
            for row in rows:
                result.append({
                    'id': row['id'],
                    'name': row['name'],
                    'tier': row['tier'],
                    'description': row['description'] or '',
                    'ability_affinity': json.loads(row['ability_affinity_json'] or '[]'),
                    'champion_affinity': json.loads(row['champion_affinity_json'] or '[]'),
                })
            return result
    except Exception:
        return []


def _row_to_augment(row):
    """将数据库行转为增幅字典"""
    return {
        'id': row['id'],
        'name': row['name'],
        'tier': row['tier'],
        'description': row['description'] or '',
        'effects': json.loads(row['effects_json'] or '[]'),
        'calc_vars': json.loads(row['calc_vars_json'] or '{}'),
        'ability_affinity': json.loads(row['ability_affinity_json'] or '[]'),
        'champion_affinity': json.loads(row['champion_affinity_json'] or '[]'),
        'source': row['source'] or 'inferred',
    }


# ──── 增幅版本历史 ────

def save_augment_version(version_id, version, ddragon_version='', total=0,
                         curated=0, inferred=0, created=''):
    """保存增幅版本历史"""
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO augment_versions
                (id, version, ddragon_version, total, curated, inferred, created)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (version_id, version, ddragon_version, total, curated, inferred, created))


def get_augment_versions_db():
    """获取所有版本历史"""
    try:
        with get_db() as db:
            rows = db.execute(
                "SELECT * FROM augment_versions ORDER BY created DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


# ──── 计算规则 ────

def save_calc_rules(rules_dict):
    """保存计算规则（递归摊平存储）"""
    with get_db() as db:
        db.execute("DELETE FROM calc_rules")
        _flatten_rules(db, '', rules_dict)


def _flatten_rules(db, prefix, data):
    """递归将规则存入数据库"""
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                _flatten_rules(db, key, v)
            else:
                db.execute(
                    "INSERT OR REPLACE INTO calc_rules (section, key, value_json) VALUES (?, ?, ?)",
                    (key.split('.')[0] if '.' in key else '', key, json.dumps(v))
                )
    else:
        db.execute(
            "INSERT OR REPLACE INTO calc_rules (section, key, value_json) VALUES (?, ?, ?)",
            (prefix, prefix, json.dumps(data))
        )


def get_calc_rules():
    """获取计算规则（还原为嵌套字典）"""
    try:
        with get_db() as db:
            rows = db.execute("SELECT key, value_json FROM calc_rules").fetchall()
            result = {}
            for row in rows:
                keys = row['key'].split('.')
                val = json.loads(row['value_json'])
                d = result
                for k in keys[:-1]:
                    if k not in d:
                        d[k] = {}
                    d = d[k]
                d[keys[-1]] = val
            return result
    except Exception:
        return {}


# ──── 数据库元信息 ────

def set_meta(key, value):
    """设置元数据"""
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?)",
            (key, str(value))
        )


def get_meta(key, default=None):
    """获取元数据"""
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT value FROM db_meta WHERE key = ?", (key,)
            ).fetchone()
            return row['value'] if row else default
    except Exception:
        return default


# ──── 数据库统计信息 ────

def get_db_stats():
    """获取数据库完整统计"""
    return {
        'champions': get_champion_count(),
        'augments': get_augment_stats(),
        'version': get_version_info(),
        'db_size': os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
    }
