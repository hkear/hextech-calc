# 海克斯增幅计算器 - Hextech Augment Calculator

分析英雄联盟海克斯增幅（Hextech Augments）对每个英雄技能的增益效果。
## 镜像源
### 默认使用了腾讯云，自行修改Dockerfile的apt源即可
## 快速启动

### Docker（推荐）

```bash
# 构建并启动
docker compose up -d

# 构建单次
docker build -t hextech-calc .
docker run -d -p 9001:9001 --name hextech-calc hextech-calc

# 访问
open http://localhost:9001
```

### 直接运行

```bash
pip install -r requirements.txt
python3 scripts/prepare_db.py   # 填充数据库
python3 app.py                  # 启动服务
```

## 数据更新

```bash
# 更新所有数据
python3 scripts/update_data.py

# 仅更新英雄
python3 scripts/update_data.py --champions

# 仅更新增幅
python3 scripts/update_data.py --augments

# 查看数据状态
python3 scripts/update_data.py --status
```

## 项目结构

```
hextech-calc/
├── app.py                     # Flask 主应用
├── config.py                  # 配置
├── Dockerfile                 # Docker 构建
├── docker-compose.yml         # Docker 编排
├── requirements.txt           # Python 依赖
├── engine/
│   ├── calculator.py          # 计算引擎
│   └── database.py            # SQLite 数据层
├── fetcher/
│   └── ddragon.py             # DDragon API 抓取
├── scripts/
│   ├── prepare_db.py          # 数据库预填充
│   ├── update_data.py         # 数据更新
│   ├── docker-entrypoint.sh   # Docker 入口
│   ├── fetch_full_augments.py # 增幅全量抓取
│   └── *.sh                   # 旧版更新脚本
├── data/
│   ├── hextech_calc.db        # SQLite 数据库
│   ├── augments_full.json     # 增幅全量数据
│   ├── augment_versions.json  # 版本历史
│   ├── calc_rules.json        # 计算规则
│   ├── champion_list.json     # 英雄列表
│   └── champions/             # 英雄详情缓存
├── static/
│   ├── css/style.css
│   └── js/app.js
└── templates/
    └── index.html
```

## 数据源

- **英雄数据**: [DDragon API](https://developer.riotgames.com/docs/lol#data-dragon) (Riot 官方)
- **增幅数据**: [CommunityDragon API](https://raw.communitydragon.org/) (CDragon)
- **本地存储**: SQLite 数据库（所有数据预填充，脱机可用）

## 数据规模

| 数据项 | 数量 |
|-------|:---:|
| 英雄 | 172 位 |
| 增幅 | 640 个 |
| ├ 手工标定 | 115 个 |
| └ AI推理 | 525 个 |

## 导出镜像

```bash
# 导出 Docker 镜像
docker save hextech-calc:latest | gzip > hextech-calc.tar.gz

# 在目标机器加载
docker load < hextech-calc.tar.gz
docker compose up -d
```
