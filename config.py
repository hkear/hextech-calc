"""
海克斯增幅计算器 - 配置文件
所有变量参数集中管理，便于版本更新
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 端口
PORT = 9001

# 数据库路径（SQLite 为主数据源）
DB_PATH = os.path.join(BASE_DIR, "data", "hextech_calc.db")

# DDragon 数据源（可随版本切换镜像）
DDragon = {
    "base_url": "https://ddragon.leagueoflegends.com",
    "cdn_url": "https://ddragon.leagueoflegends.com/cdn",
    "region": "zh_CN",          # 语言
    "version_check_url": "https://ddragon.leagueoflegends.com/api/versions.json",
    "timeout": 15,
}

# 社区龙(CDragon)数据源（获取海克斯/游戏模式数据）
CDragon = {
    "base_url": "https://raw.communitydragon.org/latest",
    "region_zh": "zh_cn",
    "region_en": "default",
    "timeout": 15,
}

# 本地数据路径（JSON 文件作为数据源的补充/回退）
DATA_DIR = os.path.join(BASE_DIR, "data")
CHAMPION_CACHE_DIR = os.path.join(DATA_DIR, "champions")
AUGMENTS_FILE = os.path.join(DATA_DIR, "augments_full.json")  # 全量数据库
AUGMENTS_LEGACY_FILE = os.path.join(DATA_DIR, "augments.json")  # 旧版
CALC_RULES_FILE = os.path.join(DATA_DIR, "calc_rules.json")
VERSION_FILE = os.path.join(DATA_DIR, "version.json")
AUGMENT_VERSIONS_FILE = os.path.join(DATA_DIR, "augment_versions.json")
CHAMPION_LIST_CACHE = os.path.join(DATA_DIR, "champion_list.json")

# 确保目录存在
os.makedirs(CHAMPION_CACHE_DIR, exist_ok=True)

# 计算引擎参数
CALC_ENGINE = {
    "max_augments_per_calc": 4,
    "default_skill_level": 5,       # 默认满级技能
    "default_champion_level": 18,   # 默认18级
    "damage_weights": {             # 伤害类型权重
        "ad_physical": 1.0,
        "ap_magic": 1.0,
        "true_damage": 1.3,         # 真伤权重更高
        "hybrid": 1.1,
    },
    "synergy_weights": {            # 评分权重
        "skill_match": 0.35,        # 技能覆盖度
        "stat_boost": 0.30,         # 数值提升幅度
        "special_effect": 0.20,     # 特殊效果价值
        "tier_power": 0.15,         # 品阶基础强度
    },
    "version": "2.0.0",
}

# 更新脚本配置
UPDATE_CONFIG = {
    "auto_update_interval_hours": 24,   # 自动检查更新间隔
    "champion_version_url": "https://ddragon.leagueoflegends.com/api/versions.json",
    "enable_startup_check": True,       # 启动时检查更新
}
