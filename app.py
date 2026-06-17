"""
海克斯增幅计算器 - Flask主应用
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
from config import PORT, CHAMPION_LIST_CACHE, AUGMENTS_FILE, CHAMPION_CACHE_DIR, DATA_DIR
from fetcher.ddragon import get_champion_list, get_champion_detail, get_latest_version
from engine.calculator import (
    calculate_full, get_augment_list, get_augment_data,
    search_augments, get_random_augments,
    get_augment_meta, get_augment_versions
)
from engine.database import (
    get_champion_list_db, get_champion, get_version_info,
    get_champion_count, get_augment_count, get_augment_stats,
)

app = Flask(__name__)

# 启动时缓存版本
_cached_version = None
_db_init_checked = False


def get_version():
    global _cached_version
    if not _cached_version:
        # 优先从数据库读取
        vi = get_version_info()
        if vi and vi.get('ddragon_version'):
            _cached_version = vi['ddragon_version']
        else:
            _cached_version = get_latest_version() or "unknown"
    return _cached_version


def _load_champion_list():
    """加载英雄列表：优先数据库，回退 API/JSON"""
    try:
        db_list = get_champion_list_db()
        if db_list:
            return db_list
    except Exception:
        pass
    # 回退
    cl, _ = get_champion_list()
    return cl


def _load_champion_detail(champion_id, version):
    """加载英雄详情：优先数据库，回退 API"""
    # 尝试数据库
    try:
        db_champ = get_champion(champion_id)
        if db_champ and db_champ.get('skills') and len(db_champ.get('skills', {})) > 0:
            return db_champ
    except Exception:
        pass
    # 回退 API/缓存
    return get_champion_detail(champion_id, version)


# ──── API 路由 ────

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/api/champions')
def api_champions():
    """英雄列表"""
    force = request.args.get('refresh', '0') == '1'

    if force or not get_champion_count():
        # 强制刷新：从 API 拉取
        cl, v = get_champion_list(force_refresh=True)
    else:
        # 从数据库读取
        cl = _load_champion_list()

    # 转为数组，方便前端搜索
    items = []
    for cid, cinfo in cl.items():
        items.append({
            'id': cid,
            'name': cinfo['name'],
            'title': cinfo['title'],
            'tags': cinfo.get('tags', []),
            'search_key': f"{cinfo['name']} {cinfo['title']} {cid}",
        })
    return jsonify({
        'count': len(items),
        'version': get_version(),
        'champions': items,
    })


@app.route('/api/champion/<champion_id>')
def api_champion_detail(champion_id):
    """英雄详情（含技能数据）"""
    version = get_version()
    force = request.args.get('refresh', '0') == '1'
    try:
        if force:
            detail = get_champion_detail(champion_id, version, force_refresh=True)
        else:
            detail = _load_champion_detail(champion_id, version)
        # 精简返回
        result = {
            'id': detail['id'],
            'name': detail['name'],
            'title': detail['title'],
            'tags': detail.get('tags', []),
            'stats': detail.get('stats', {}),
            'skills': detail['skills'],
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/augments')
def api_augments():
    """增幅列表"""
    tier = request.args.get('tier')
    search = request.args.get('search', '')
    limit = int(request.args.get('limit', 100))

    if search:
        items = search_augments(search, limit)
    else:
        tier_key = None
        tier_map = {'silver': 'kSilver', 'gold': 'kGold', 'prismatic': 'kPrismatic'}
        if tier in tier_map:
            tier_key = tier_map[tier]
        items = get_augment_list(tier_key)

    return jsonify({
        'count': len(items),
        'augments': items[:limit],
    })


@app.route('/api/augment/<augment_id>')
def api_augment_detail(augment_id):
    """单个增幅详情"""
    augments = get_augment_data()
    a = augments.get(augment_id)
    if not a:
        return jsonify({'error': '未找到该增幅'}), 404
    return jsonify({
        'id': augment_id,
        **a,
    })


@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    """核心计算接口"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请提供JSON数据'}), 400

    champion_id = data.get('champion_id', '')
    augment_ids = data.get('augment_ids', [])

    if not champion_id:
        return jsonify({'error': '请选择英雄'}), 400
    if len(augment_ids) < 1:
        return jsonify({'error': '请选择至少1个增幅'}), 400

    # 获取英雄数据
    version = get_version()
    if not version:
        return jsonify({'error': '无法获取数据版本'}), 500

    try:
        champion_data = _load_champion_detail(champion_id, version)
    except Exception as e:
        return jsonify({'error': f'英雄数据获取失败: {str(e)}'}), 404

    # 执行计算
    try:
        result = calculate_full(champion_data, augment_ids)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'计算失败: {str(e)}'}), 500


@app.route('/api/random-augments')
def api_random_augments():
    """随机获取几个增幅"""
    count = int(request.args.get('count', 4))
    tier = request.args.get('tier')
    tier_map = {'silver': 'kSilver', 'gold': 'kGold', 'prismatic': 'kPrismatic'}
    items = get_random_augments(count, tier_map.get(tier))
    return jsonify({
        'count': len(items),
        'augments': items,
    })


@app.route('/api/version')
def api_version():
    """版本信息"""
    meta = get_augment_meta()
    vi = get_version_info()
    db_version = vi.get('engine_version', '2.0.0') if vi else '2.0.0'
    # 统计优先数据库
    try:
        champ_count = get_champion_count()
        astats = get_augment_stats()
        augment_total = astats.get('total', 0)
        curated = astats.get('curated', 0)
        inferred = astats.get('inferred', 0)
        tiers = astats.get('tier_distribution', {})
    except Exception:
        champ_count = meta.get('champion_count', len(get_champion_list()[0]) if get_champion_list()[0] else 0)
        augment_total = meta.get('total_augments', len(get_augment_data()))
        curated = meta.get('curated_count', 0)
        inferred = meta.get('inferred_count', 0)
        tiers = meta.get('tier_distribution', {})
    # 获取游戏版本（从 extra 字段）
    game_version = get_version()
    if vi and vi.get('extra'):
        try:
            extra = json.loads(vi['extra']) if isinstance(vi['extra'], str) else vi['extra']
            if extra.get('game_version'):
                game_version = extra['game_version']
        except:
            pass
    return jsonify({
        'ddragon_version': get_version(),
        'game_version': game_version,
        'engine_version': db_version,
        'champion_count': champ_count,
        'augment_count': augment_total,
        'augment_curated': curated,
        'augment_inferred': inferred,
        'augment_db_version': meta.get('version', db_version),
        'augment_last_updated': meta.get('last_updated', vi.get('last_updated', '-') if vi else '-'),
        'augment_tiers': tiers,
    })


@app.route('/api/augment-versions')
def api_augment_versions():
    """增幅数据版本历史"""
    return jsonify({
        'versions': get_augment_versions(),
        'current': get_augment_meta().get('version', '1.0.0'),
    })


@app.route('/api/update', methods=['POST'])
def api_update_data():
    """手动触发数据更新"""
    from fetcher.ddragon import update_all_champions
    result = update_all_champions()
    return jsonify(result)


# ──── 启动 ────

if __name__ == '__main__':
    print(f"🚀 海克斯增幅计算器启动中...")
    print(f"   DDragon版本: {get_version()}")

    # 检查数据库是否有数据
    try:
        champ_count = get_champion_count()
        astats = get_augment_stats()
        print(f"   英雄数: {champ_count}")
        print(f"   增幅数: {astats.get('total', 0)} (手工 {astats.get('curated', 0)} + 推理 {astats.get('inferred', 0)})")
    except Exception:
        cl, _ = get_champion_list()
        print(f"   英雄数: {len(cl) if cl else 0}")
        augs = get_augment_data()
        print(f"   增幅数: {len(augs)}")
    print(f"   端口: {PORT}")
    print(f"   访问: http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
