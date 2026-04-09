# 棒球队管理系统

一个基于 Flask 的棒球队管理系统，用于管理球员资料、单场比赛记录、累计打击/投球统计、对局查询，以及历年比赛 PDF 数据导入。

当前版本已经完成一轮比较重要的底层整理：

- 数据库统一为 SQLite
- 球员基础信息、打击汇总、投球汇总拆分存储
- 支持多守位
- `is_pitcher` 改为独立业务标记，而不是和野手互斥的身份

## 当前版本重点

- 球员可以拥有多个守备位置
- 如果球员勾选“是否为投手”，系统会自动把 `投手` 加入守备位置
- 投手仍然可以同时选择 `捕手 / 内野 / 外野` 等其他位置
- 投手的主位置不必固定为 `投手`
- 每个球员都保留打击档案
- 只有可投球球员才有投手档案
- 投手可以录入打击记录
- 对局信息统计支持：
  - 只按球员查询
  - 只按对手查询
  - 同时按球员 + 对手查询
- 对局信息页面会分开展示打击记录和投球记录
- 没有实际录入内容的空记录不会在对局统计中展示
- 添加比赛记录时，“对手球队”可以直接复用历史对手列表，也可以手动输入新对手

## 技术栈

- 后端：Flask
- ORM：Flask-SQLAlchemy
- 数据迁移辅助：Flask-Migrate
- 数据库：SQLite
- 数据分析：pandas
- 图表：matplotlib / seaborn / plotly
- PDF 解析：pdfplumber
- 前端：Bootstrap 5 + 原生 JavaScript + jQuery + DataTables

## 数据结构

### 核心表

- `players`
  - 球员主档案
  - 保存姓名、背号、主位置、是否为投手等基础信息
- `positions`
  - 守备位置字典表
- `player_positions`
  - 球员和守备位置的多对多关系
- `fielder_profiles`
  - 打击与守备汇总
- `pitcher_profiles`
  - 投球汇总
- `game_records`
  - 单场原始比赛记录

### 当前业务规则

- `is_pitcher` 表示“这个球员可以投球”
- `is_pitcher = true` 时：
  - 球员会自动拥有 `投手` 位置
  - 仍然可以同时拥有其他守备位置
  - 主位置可以是 `投手`，也可以是其他已选位置
- `is_pitcher = false` 时：
  - 系统会自动移除 `投手` 位置
- 每个球员都会保留 `fielder_profile`
- 系统会根据 `is_pitcher` 在投球统计场景中使用 `pitcher_profile`
- 单场记录写入 `game_records` 后，会同步更新汇总档案

## 页面入口

- `/`
  - 首页
- `/players`
  - 球员列表
- `/add_player`
  - 添加球员
- `/game_stats`
  - 比赛数据总览
- `/add_game_record`
  - 添加比赛记录
- `/stats`
  - 综合统计与图表
- `/matchup_stats`
  - 对局信息统计
- `/pdf_viewer`
  - 历年比赛 PDF 查看
- `/import_pdf`
  - PDF 批量导入

## 常用 API

### 球员

- `GET /api/players`
- `POST /api/players`
- `PUT /api/players/<player_id>`
- `DELETE /api/players/<player_id>`
- `GET /api/players/batters`
- `GET /api/players/pitchers`

### 比赛记录

- `POST /api/game_records`

### 统计

- `GET /api/stats/batting`
- `GET /api/stats/pitching`
- `GET /api/stats/visualization`
- `GET /api/stats/batting_leaderboard`
- `GET /api/stats/pitching_leaderboard`
- `GET /api/visualization/batting`
- `GET /api/visualization/pitching`
- `GET /api/export/csv`

### 对局信息

- `GET /api/matchup/opponents`
- `GET /api/matchup/search_records`
- `GET /api/matchup/all_game_records`
- `DELETE /api/matchup/game_record/<record_id>`

说明：

- `search_records` 是当前推荐使用的对局查询接口
- 旧的 `player_vs_opponent`、`player_game_records` 仍保留，主要用于兼容旧逻辑

### PDF

- `GET /api/pdf/files`
- `GET /api/pdf/view/<path:filepath>`
- `GET /api/pdf/parse/<path:filepath>`
- `POST /api/pdf/import_all`
- `POST /api/pdf/import_one`

## 环境要求

建议环境：

- Python 3.11 或 3.12
- pip

说明：

- 运行 Flask 项目主要依赖 Python

## 安装步骤

### 1. 进入项目目录

```bash
cd 文件夹目录
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

## 启动项目

### 1. 启动 Flask

直接启动即可，程序会自动创建缺失的数据表和位置字典：

```bash
python app.py
```

默认地址：

```text
http://127.0.0.1:5000
```

默认数据库文件位于：

- `instance/baseball_players.db`

### 2. 初始化带示例数据的数据库

如果你希望额外写入一批示例球员数据，可以执行：

```bash
python init_db.py
```

说明：

- `app.py` 本身就会自动建表
- `init_db.py` 适合“新建数据库 + 初始化位置 + 添加示例数据”的场景

## 旧数据库迁移

如果你的项目里已经存在旧版本数据库，并且旧数据主要写在 `players` 大表中，可以执行：

```bash
python migrate_profiles_sqlite.py
```

这个脚本会：

- 自动备份原数据库
- 创建 `fielder_profiles` / `pitcher_profiles`
- 尝试把旧累计统计迁移到新档案表
- 规范球员角色和位置信息

备份文件会保存在 `instance/` 目录下，文件名类似：

```text
baseball_players.backup_YYYYMMDD_HHMMSS.db
```

## PDF 导入

### Web 页面方式

打开：

```text
http://127.0.0.1:5000/import_pdf
```

支持：

- 预览 PDF 解析结果
- 导入单个 PDF
- 批量导入全部 PDF

### 命令行方式

预览：

```bash
python import_pdfs.py --dry-run
```

实际导入：

```bash
python import_pdfs.py
```

## 目录说明

```text
baseball-player-manager/
├── app.py
├── database.py
├── init_db.py
├── migrate_profiles_sqlite.py
├── import_pdfs.py
├── pdf_parser.py
├── cleanup_db.py
├── requirements.txt
├── README.md
├── templates/
├── static/
├── data/
└── instance/
```

### 关键文件

- `app.py`
  - Flask 主入口和主要 API
- `database.py`
  - SQLAlchemy 数据模型与兼容迁移逻辑
- `migrate_profiles_sqlite.py`
  - 旧数据库迁移脚本
- `templates/add_player.html`
  - 添加球员页面
- `templates/add_game_record.html`
  - 添加比赛记录页面
- `templates/matchup_stats.html`
  - 对局信息页面
- `static/js/script.js`
  - 球员管理前端逻辑
- `static/js/game_record.js`
  - 比赛记录前端逻辑
- `static/js/matchup_stats.js`
  - 对局统计前端逻辑

## 当前版本的几个使用说明

### 1. 添加球员

- 可以多选守备位置
- 如果勾选“是否为投手”，系统会自动补上 `投手`
- 投手仍然可以继续选择其他守位
- 主位置必须在已选位置里

### 2. 添加比赛记录

- 非投手只能录入打击记录
- 可投球球员可以录入打击记录，也可以录入投球记录
- 对手字段支持选择历史对手，也支持直接输入新对手

### 3. 对局信息统计

- 可以只按球员查询
- 可以只按对手查询
- 可以同时按球员和对手查询
- 查询结果会分成：
  - 打击记录
  - 投球记录
- 没有实际数据的空记录不会展示
- 进入筛选结果后，全队记录区域会自动隐藏，避免混淆

## 可能会用到的维护命令

重建数据库：

```bash
python init_db.py
```

迁移旧数据：

```bash
python migrate_profiles_sqlite.py
```

检查 Python 语法：

```bash
python -m py_compile app.py database.py
```

## 后续可继续优化的方向

- 把 Flask 接口进一步拆成更清晰的服务层
- 给比赛记录增加编辑功能
- 给对局信息增加日期范围筛选
- 增加用户登录和权限管理
- 增加自动备份和导入日志

## 相关文件

- `app.py`
- `database.py`
- `migrate_profiles_sqlite.py`
