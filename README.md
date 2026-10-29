# POWER ARENA — 北工大棒球队管理系统

一个基于 Flask 的棒球队管理系统，采用竞技风（arena）深色主题 UI，支持球员管理、比赛记录录入、统计可视化、对局查询、PDF 批量导入等功能。

> 仓库地址：<https://github.com/earthgrass/bjut-baseball-system>

---

## 功能特性

### 核心功能
- **球员管理**：添加、编辑、删除球员，支持多守备位置与主位置
- **比赛记录**：录入单场打击/投球数据，自动累计到汇总档案
- **批量录入**：粘贴 box score 一次写完整场比赛，提交前逐行校验姓名与业务不变量
- **对局查询**：按球员、对手或「球员 × 对手」组合筛选历史对战数据
- **数据可视化**：打击率、防御率、排行榜等图表（服务端渲染 PNG）
- **PDF 导入**：自动解析历年比赛 PDF 并批量导入，支持预览后确认
- **数据导出**：一键导出 CSV
- **管理员登录**：所有写操作（增删改、导入、删除比赛）均需登录鉴权

### 技术亮点
- 竞技风 UI（深色主题 + 红色强调色），Tailwind CSS + 自定义 `arena.css`
- 服务端图表渲染（matplotlib + seaborn），中文字体自动回退
- SQLite 单文件数据库，零配置启动
- CSRF 防护 + 登录/API 双层速率限制 + 路径穿越防护
- **写入语义单一**：`game_records` 是唯一真实源，统计档案一律从它重算
  （恒等式 `profile == SUM(game_records)` 永远成立）
- 96 个 pytest + 25 个 node 单测，测试库与生产库物理隔离

---

## 技术栈

以下为**实际验证通过的版本**（与 `requirements.txt` 一致）：

| 层级 | 技术 |
|------|------|
| 后端 | Flask 3.1.3 |
| ORM | Flask-SQLAlchemy 3.1.1 |
| 登录 | Flask-Login 0.6.3 |
| 表单 / CSRF | Flask-WTF 1.3.0 / WTForms 3.2.2 |
| 限流 | Flask-Limiter 4.1.1 |
| 数据迁移 | Flask-Migrate 4.1.0 |
| 数据库 | SQLite（单文件 `instance/baseball_players.db`） |
| 数据分析 | pandas 3.0.5 |
| 图表 | matplotlib 3.11.1 / seaborn 0.13.2 / plotly 7.1.0 |
| PDF 解析 | pdfplumber 0.11.10 |
| 前端 | Tailwind CSS (CDN) + 原生 JavaScript + DataTables + jQuery（部分页面） |
| 运行时 | Python 3.12.10 |

---

## 快速开始

### 1. 克隆项目

```bash
git clone git@github.com:earthgrass/bjut-baseball-system.git
cd bjut-baseball-system
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

`.env` 至少需要设置 `SECRET_KEY`：

```bash
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

其余变量见 `.env.example` 与本文「安全注意事项」。

### 4. 启动服务

**本地开发（推荐，仅本机可访问）**

```bash
python run_local.py
# → http://127.0.0.1:5000
```

**服务器部署（绑定 0.0.0.0，接受外网访问）**

```bash
python app.py
# 或 PORT=8080 python app.py
```

> `run_local.py` 绑定 `127.0.0.1`，`app.py` / `run.py` 绑定 `0.0.0.0`。
> 本机试用请用前者，避免把管理后台暴露到局域网。

数据库文件会自动创建于 `instance/baseball_players.db`。

### 5. 管理员账号

首次使用需要创建管理员：

```bash
# 交互式（密码不回显，不落盘）
python scripts/reset_admin_password.py

# 或用环境变量
ADMIN_USERNAME=admin ADMIN_PASSWORD='你的密码' python scripts/reset_admin_password.py
```

也可以在首次启动时用 `INIT_DEFAULT_ADMIN=1 ADMIN_PASSWORD=...` 自动创建（见 `.env.example`）。

> ⚠️ `INIT_DEFAULT_ADMIN=1` 只在账号**不存在**时生效，不会覆盖已有账号的密码。
> 改密码请一律用 `scripts/reset_admin_password.py`。

### 6. 初始化示例数据（可选）

```bash
python init_db.py
```

---

## 数据结构

### 核心表

| 表名 | 说明 |
|------|------|
| `players` | 球员主档案（姓名、背号、主位置、是否投手） |
| `positions` | 守备位置字典表（9 个位置） |
| `player_positions` | 球员-位置多对多关系 |
| `fielder_profiles` | 打击与守备汇总统计 |
| `pitcher_profiles` | 投球汇总统计 |
| `game_records` | 单场比赛原始记录 |
| `users` | 管理员账号（密码哈希存储） |

### 业务规则

- `is_pitcher = true` 时自动拥有「投手」位置，仍可兼守其他位置
- 每个球员都有 `fielder_profile`，投手额外拥有 `pitcher_profile`
- 比赛记录写入后自动同步更新汇总档案（`sync_stats_from_game_records()`）
- 应用启动时会重算一次汇总档案，保证 profile 与 game_records 一致

### 守备位置

投手、捕手、第一垒手、第二垒手、第三垒手、游击手、左外野手、中外野手、右外野手

---

## 页面入口

| 路径 | 功能 | 鉴权 |
|------|------|------|
| `/` | 首页 — 数据总览与快捷入口 | 公开 |
| `/login` | 管理员登录 | 公开 |
| `/logout` | 退出登录（POST） | — |
| `/players` | 球员列表 | 公开 |
| `/add_player` | 添加球员 | 管理员 |
| `/game_stats` | 比赛数据总览 | 公开 |
| `/add_game_record` | 添加比赛记录 | 管理员 |
| `/batch_entry` | 批量录入整场比赛（粘贴 box score） | 管理员 |
| `/stats` | 综合统计与图表 | 公开 |
| `/matchup_stats` | 对局信息统计 | 公开 |
| `/pdf_viewer` | 历年比赛 PDF 查看 | 公开 |
| `/import_pdf` | 从 `data/` 批量导入 PDF | 管理员 |
| `/upload_pdf` | 上传单个 PDF 并导入 | 管理员 |

---

## API 接口

### 鉴权与 CSRF

- 读接口（GET）公开可访问
- 写接口（POST/PUT/DELETE）需管理员登录（session cookie），未登录返回 `302` 跳转 `/login`
- **所有写接口还需携带 CSRF token**：请求头 `X-CSRFToken`，值取自页面 `<meta name="csrf-token">`
  （前端 `static/js/api.js` 的 `fetchJson()` 会自动附加）

```bash
# 登录拿 cookie
curl -c cookies.txt http://127.0.0.1:5000/login
# 提交写请求时加上 X-CSRFToken
curl -b cookies.txt -X POST http://127.0.0.1:5000/api/game_records \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <token>" \
  -d '{...}'
```

### 球员

```
GET    /api/players              # 获取所有球员
POST   /api/players              # 添加球员
GET    /api/players/<id>         # 获取单个球员
PUT    /api/players/<id>         # 更新球员
DELETE /api/players/<id>         # 删除球员
GET    /api/players/batters      # 获取打击球员列表
GET    /api/players/pitchers     # 获取投手列表
```

### 比赛记录

```
POST   /api/game_records         # 添加比赛记录
```

### 统计

```
GET    /api/stats/batting              # 打击统计
GET    /api/stats/pitching             # 投球统计
GET    /api/stats/visualization        # 综合可视化图表
GET    /api/stats/batting_leaderboard  # 打击排行榜
GET    /api/stats/pitching_leaderboard # 投手排行榜
GET    /api/visualization/batting      # 打击可视化
GET    /api/visualization/pitching     # 投球可视化
GET    /api/export/csv                 # 导出 CSV
```

### 对局信息

```
GET    /api/matchup/opponents           # 获取所有对手列表
GET    /api/matchup/search_records      # 按 player_id / opponent 筛选比赛记录
GET    /api/matchup/player_vs_opponent  # 某球员对某对手的累计数据
GET    /api/matchup/player_game_records # 某球员的全部比赛记录
GET    /api/matchup/all_game_records    # 获取全队所有比赛记录
DELETE /api/matchup/game_record/<id>    # 删除比赛记录
```

### PDF

```
GET  /api/pdf/files           # 获取 PDF 文件列表
GET  /api/pdf/view/<path>     # 查看 PDF 内容
GET  /api/pdf/parse/<path>    # 解析 PDF（预览，不写库）
POST /api/pdf/import_all      # 批量导入所有 PDF（支持 dry_run）
POST /api/pdf/import_one      # 导入单个 PDF
POST /api/pdf/upload          # 上传并解析 PDF
POST /api/pdf/confirm_import  # 确认导入已解析的数据
```

> 更详细的调用示例见 [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)。

---

## 目录结构

```
bjut-baseball-system/
├── app.py                    # Flask 主入口（所有路由，约 1700 行）
├── run.py                    # 启动脚本，绑定 0.0.0.0（部署用）
├── run_local.py              # 启动脚本，绑定 127.0.0.1（本地开发用）
├── config.py                 # 配置类（Production / Development / Testing）
├── database.py               # 数据模型 + 迁移 + 统计同步 + 默认管理员
├── pdf_parser.py             # PDF 解析模块
├── import_pdfs.py            # PDF 批量导入脚本
├── init_db.py                # 初始化数据库（含示例数据）
├── create_admin.py           # 交互式创建管理员
├── cleanup_db.py             # 数据库清理工具
├── migrate_profiles_sqlite.py# 历史档案迁移脚本
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 构建文件（保留为回退方案）
├── docker-compose.yml        # Docker Compose 配置
├── .env.example              # 环境变量模板
├── API_DOCUMENTATION.md      # API 调用文档
├── docs/                     # 设计与事故分析文档
│   ├── DOMAIN_AND_ARCHITECTURE_DESIGN.md
│   ├── CSRF_AUDIT.md
│   ├── STATS_WRITE_PATH_REPORT.md
│   ├── DB_FORENSICS_REPORT.md
│   └── PHASE_R0_REPORT.md
├── scripts/                  # 一次性 / 运维脚本
│   ├── reset_admin_password.py  # 重设管理员密码
│   ├── r0_recover.py            # 数据库恢复工具
│   ├── db_forensics.py          # 数据库指纹取证
│   ├── dedupe_tailwind_config.py
│   └── inject_tailwind_config.py
├── tests/                    # pytest 回归测试（62 个）
│   ├── conftest.py           # 测试隔离（临时库 + 生产库 SHA256 看门狗）
│   ├── test_canary_r0.py     # 生产库未被改动的哨兵测试
│   ├── test_players_baseline.py
│   ├── test_game_records_baseline.py
│   ├── test_stats_baseline.py
│   ├── test_matchup_baseline.py
│   └── test_pdf_parser_baseline.py
├── templates/                # HTML 模板
│   ├── base.html             # 公共布局（nav / arena 背景 / csrf meta）
│   ├── _navbar.html          # 导航栏 partial
│   ├── _arena_bg.html        # 装饰背景 partial
│   ├── index.html            # 首页
│   ├── login.html            # 登录页
│   ├── players.html          # 球员列表
│   ├── add_player.html       # 添加球员
│   ├── game_stats.html       # 比赛数据
│   ├── add_game_record.html  # 添加比赛记录
│   ├── stats.html            # 统计图表
│   ├── matchup_stats.html    # 对局信息
│   ├── pdf_viewer.html       # PDF 查看
│   ├── import_pdf.html       # PDF 批量导入
│   └── upload_pdf.html       # PDF 上传
├── static/
│   ├── css/arena.css         # 竞技风全局样式
│   └── js/
│       ├── api.js            # fetchJson() 封装（自动带 CSRF header）
│       ├── script.js         # 球员页逻辑
│       ├── game_record.js    # 比赛录入逻辑
│       ├── game_stats.js     # 比赛数据页逻辑
│       ├── matchup_stats.js  # 对局统计逻辑
│       ├── pdf_viewer.js     # PDF 查看器逻辑
│       └── tailwind.config.js
├── data/                     # 历年比赛 PDF（按年份分目录）
│   ├── 2023/  (4 个 PDF)
│   ├── 2024/  (7 个 PDF)
│   └── 2025/  (6 个 PDF)
├── recovery/                 # 数据事故取证与恢复快照（本地保留，不入库）
└── instance/                 # 数据库文件目录（gitignored）
    └── baseball_players.db
```

---

## 使用说明

### 添加球员
- 可多选守备位置
- 勾选「是否为投手」自动添加投手位置
- 投手可同时选择其他守位
- 主位置必须在已选位置中

### 添加比赛记录
- 非投手只能录入打击记录
- 投手可录入打击或投球记录
- 对手支持选择历史对手或手动输入

### 批量录入整场比赛（`/batch_entry`）

把 box score 直接粘进去，一次写完整场比赛：

```
打击：姓名 AB R H RBI BB SO   [2B] [3B] [HR] [HBP] [SB] [CS] [SF] [SH]
投球：姓名 IP H R ER BB SO   [HR] [P] [ST] [BF] [WP]
```

- 粘贴后**实时解析成预览表**，逐行标 ✓ / 错误原因，确认无误再提交
- 表头行、`#` 注释行、空行、合计行自动跳过
- 姓名必须对得上队内球员；投球行必须对应投手
- 数值非法、负数、`安打 > 打数`、`安打 < 二/三/本垒打之和` → 标红并**阻止提交**
  （不静默跳过 —— 跳过等于丢数据）
- 提交走 `POST /api/game_records/batch`，**全有或全无**：任何一条不合法就整批回滚
- 局数按 box score 上的字面数字填（中文记法 `.1` = 1/3 局），与历史数据同口径

### 对局信息统计
- 支持按球员、对手或「球员 × 对手」组合筛选
- 结果分开展示打击记录和投球记录
- 空记录自动隐藏

### PDF 导入
1. 将 PDF 文件放入 `data/` 目录（按年份分子目录）
2. 访问 `/import_pdf` 选择已有 PDF 批量导入，或 `/upload_pdf` 上传新文件
3. 预览解析结果后确认导入

PDF 文件命名格式建议：`队伍A_vs_队伍B_月_日_年.pdf`

例如：`北京工业大学_vs_北京交通大学_Nov_16_2024.pdf`

---

## 测试

```bash
pip install pytest
python -m pytest tests/ -q
# 96 passed

# 前端解析器的单元测试（需要 node）
node --test tests/js/batch_entry.test.js
# 25 passed
```

> **测试绝不能碰生产库**。`tests/conftest.py` 用 `DATABASE_FILE` 环境变量
> 在 `import app` **之前**把数据库指向临时目录，并全程监视生产库的 SHA256。
> 详见 `docs/PHASE_R0_REPORT.md`（2026-04 数据事故的取证记录）。

### 测试隔离机制（重要）

测试**绝不会**触碰生产库 `instance/baseball_players.db`。三道防线：

1. **物理隔离**：`tests/conftest.py` 在 `import app` **之前**通过 `DATABASE_FILE` 环境变量
   把数据库指向 `tempfile.mkdtemp()` 下的临时文件。
   Flask-SQLAlchemy 在 `init_app()` 里就 eager 创建 engine，之后再改
   `app.config['SQLALCHEMY_DATABASE_URI']` **不会生效**——早期版本的 conftest 正是
   在 import 之后才覆盖 URI，导致 `db.drop_all()` 打在了生产库上（见下方事故记录）。
2. **路径校验**：`_is_test_safe_path()` 拒绝任何路径组件含 `instance` 的 URI，
   只接受 `:memory:`、OS 临时目录或 `tests/.tmp/` 内的路径。
3. **SHA256 看门狗**：session 级 fixture 比对生产库运行前后的 SHA256，
   不一致立即 `RuntimeError` fail-fast；`tests/test_canary_r0.py` 另有独立哨兵测试。

> ⚠️ 修改 `tests/conftest.py` 前请先读 [`docs/PHASE_R0_REPORT.md`](docs/PHASE_R0_REPORT.md)。

---

## 安全注意事项

⚠️ **部署到公网前请配置以下环境变量：**

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
# 至少设置：
#   SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
#   ADMIN_PASSWORD=<首次启动创建的管理员密码>
```

关键环境变量：

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | 生产必填 | Flask session/CSRF 加密密钥；缺失时生产模式拒绝启动 |
| `FLASK_ENV` | - | `production` / `development` / `testing`（默认 production） |
| `FLASK_DEBUG` | - | `0` / `1`（默认 0，**生产必须为 0**） |
| `DATABASE_FILE` | - | 数据库文件路径。绝对路径直接使用，相对路径相对 `instance/`。**测试用它做隔离** |
| `ADMIN_PASSWORD` | 首次部署 | 首次启动创建默认 admin 账号的密码；缺省则随机生成并打印到 stdout |
| `INIT_DEFAULT_ADMIN` | 首次部署 | `1` 才会创建默认 admin，**生产部署后必须改为 `0`** |
| `RATELIMIT_LOGIN` | - | 登录端点速率限制（默认 `5/minute`） |
| `RATELIMIT_API` | - | API 默认速率限制（默认 `60/minute`） |

**已自动启用的安全机制**：

- CSRF 保护（Flask-WTF，登录表单 + 所有写接口；写接口走 `X-CSRFToken` header）
- 登录速率限制（5 次/分钟/IP）、API 速率限制（60 次/分钟/IP）
- 路径穿越防护（`_safe_data_path` 用 realpath + commonpath 严格校验）
- 错误信息脱敏（数据库错误不直接返回前端，统一记日志）
- 密码哈希存储（`werkzeug.security`），明文不落盘
- 危险调试端点已删除（`/api/debug/*`、`/api/test/*`、`/debug.html`）

---

## 数据事故与恢复（2026-04）

### 发生了什么

Phase E0/E0.5 期间，`tests/conftest.py` 用 `sqlite:///:memory:` 覆盖数据库 URI，
但该配置在 `import app` **之后**才生效——而 Flask-SQLAlchemy 早已在 `init_app()`
时把 engine 绑到了真实的 `instance/baseball_players.db`。于是 `db.drop_all()`
在生产库上执行，真实数据库被清空（27 名球员 / 230 条比赛记录 / 1 个管理员账号）。

### 怎么恢复的

1. 冻结现场：从 git 历史提取 4 个 DB blob，逐一比对指纹
   （表数 / 球员数 / 记录数 / 最大日期）
2. 选定 `git_bb429ba` 的 blob —— 唯一精确匹配事故前指纹（27 / 230 / max 2025-11-22）
3. 重建 `users` 表并重设管理员密码
4. 净数据损失：**0**

完整时间线、指纹矩阵与取证过程见 [`docs/PHASE_R0_REPORT.md`](docs/PHASE_R0_REPORT.md)
与 [`docs/DB_FORENSICS_REPORT.md`](docs/DB_FORENSICS_REPORT.md)。

### 当前状态

- `instance/baseball_players.db` —— 已从恢复库还原并投入运行
- `recovery/` —— 事故现场快照与恢复副本，**只读**，本地保留
- 测试隔离已按根因重写（见「测试」一节），事故不会重演

---

## 已知问题与修复记录

| 问题 | 现象 | 处理 |
|------|------|------|
| matplotlib 在 Windows 上选中 TkAgg | 访问 `/api/visualization/pitching` 时整个进程 `Tcl_AsyncDelete` 崩溃 | `app.py` 在 import pyplot 前强制 `matplotlib.use('Agg')`（服务端只输出 PNG，不需要 GUI） |
| `DATABASE_FILE` 环境变量未实现 | `.env.example` 声明了但 `app.py` 从不读取，测试无法真正隔离 | `app.py` 实现该变量；`conftest.py` 改用它做物理隔离 |
| `_is_test_safe_path` 大小写敏感 | Windows 临时目录 `...\AppData\Local\Temp\` 被误判为不安全，49 个测试全部 error | 改为按路径组件 + `commonpath` 校验 |
| 测试会清空生产库 | 见「数据事故与恢复」 | 根因修复 + SHA256 看门狗 + 路径校验，三重防线 |
| `.gitignore` 是 UTF-16 编码 | Git 解析失败，**所有忽略规则全部失效**：`.env`（含 SECRET_KEY）、真实数据库、`__pycache__/` 均可被误提交 | 转存为 UTF-8，并补 `recovery/`、`*.db-wal` 等规则 |
| `PUT /api/players/<id>` 能直接覆盖累计统计 | `Player.at_bats_total` 等是 property proxy，`setattr` **真实写库**，绕过 `game_records` 唯一真源 | 收窄为 **metadata-only**：统计字段一律 400 拒绝（不静默忽略），并删除前端的同款死代码 |
| `GET /api/game_records/<id>` 的 `'strikeouts'` 重复键 | Python dict 后者覆盖前者 → 打击记录的三振恒返回 0；对局页编辑保存时把打击三振**抹成 0** | 按 `is_pitching` 返回对应列；另加 AST 静态检查防同类 bug 再犯 |

---

## 公网部署功能影响

将项目部署到公网 GitHub 后，以下功能可能受影响：

| 功能 | 影响 | 说明 |
|------|------|------|
| 历年比赛 PDF | ✅ 可用 | `data/` 下的 17 个 PDF 已随仓库提交，克隆后开箱即用 |
| 本地数据库 | ❌ 不会同步 | `instance/` 被 .gitignore 排除，数据库需重新初始化（或挂载持久化卷） |
| PDF 上传功能 | ✅ 可用 | 上传的文件保存到 `data/uploads/`（已 gitignore），需要持久化存储 |
| 管理员账号 | ❌ 不会同步 | `users` 表在数据库里，需用 `scripts/reset_admin_password.py` 重建 |
| 其他所有功能 | ✅ 完全可用 | 球员管理、比赛录入、统计图表等均正常 |

**建议**：公网部署时挂载 volume 持久化数据库与 PDF：

```bash
docker run -d \
  -p 5000:5000 \
  -v ./instance:/app/instance \
  -v ./data:/app/data \
  baseball-app
```

### Docker 部署（不再主动维护，仅保留作为回退方案）

> ⚠️ **2026 年起的部署推荐直接用 Python + systemd / supervisor / Render / Fly.io 等平台。**
> 本项目的 `Dockerfile` 与 `docker-compose.yml` 仅作为历史回滚保留，未做主动测试。

```bash
# 必须先设置 SECRET_KEY 环境变量
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
docker-compose up -d
```

---

## 后续优化方向

- [x] 用户登录与权限管理
- [x] 单元测试覆盖（74 个回归测试）
- [x] CSRF 防护 + 速率限制 + 路径穿越防护
- [x] 测试与生产库物理隔离
- [x] 比赛记录编辑功能（`PUT /api/game_records/<id>` + 对局页编辑弹窗）
- [x] 整场比赛批量写入（`POST /api/game_records/batch`）
- [x] 投手战绩聚合（胜/负/救/胜率）
- [ ] Flask 蓝图拆分重构（`app.py` 约 1900 行，路由密度偏高）
- [ ] 对局信息日期范围筛选
- [ ] 自动备份与导入日志
- [ ] PDF 导入的字段映射可视化编辑（解析器改用列坐标，见 `FEATURE_PROPOSALS.md` F7a）
- [ ] 批量录入的前端界面（后端接口已就绪，见 `API_CONTRACT.md` §3.2）

---

## 许可证

MIT License

> 仓库暂未包含 `LICENSE` 文件，正式分发或对外协作前请补充。

---

## 项目构建过程

本项目采用 **AI 辅助开发** 模式，结合多种 AI 工具完成设计与开发。

### 开发工具

| 工具 | 用途 |
|------|------|
| **UI-UX-Promax** | UI/UX 竞技风格设计，深色主题 + 红色强调色的视觉系统 |
| **ClaudeCode + GLM5.1** | 全栈开发、代码生成、调试优化、文档编写 |

### 开发流程

1. **需求分析**：通过对话明确棒球队管理系统的核心功能需求
2. **UI 设计**：使用 UI-UX-Promax 设计竞技风格的界面原型
3. **后端开发**：
   - 使用 Flask 搭建 RESTful API
   - SQLAlchemy ORM 设计数据模型
   - 实现 PDF 解析与数据导入功能
4. **前端开发**：
   - Tailwind CSS 实现响应式竞技风 UI
   - 原生 JavaScript + jQuery 处理交互逻辑
   - DataTables 实现数据表格展示
5. **功能迭代**：持续优化用户体验，添加数据可视化、对局统计等功能
6. **加固与运维**：CSRF / 限流 / 路径校验、回归测试、数据事故取证与恢复

### AI 辅助开发的最佳实践

- **清晰的提示词**：准确描述需求，AI 能更高效地生成代码
- **迭代优化**：通过多轮对话逐步完善功能细节
- **代码审查**：AI 生成的代码需要人工检查安全性和正确性
- **文档同步**：让 AI 同时更新 README 和代码注释
- **回归测试兜底**：重构前先锁定行为（baseline tests），AI 改动才能安全验证

### 致谢

感谢 Anthropic Claude 和智谱 GLM 提供的强大 AI 能力，使得本项目的快速开发成为可能。
