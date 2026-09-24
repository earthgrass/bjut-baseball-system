# POWER ARENA - 棒球队管理系统

一个基于 Flask 的现代化棒球队管理系统，采用竞技风 UI 设计，支持球员管理、比赛记录、统计分析、PDF 导入等功能。

## 功能特性

### 核心功能
- **球员管理**：添加、编辑、删除球员信息，支持多守备位置
- **比赛记录**：录入单场打击/投球数据，自动累计统计
- **对局查询**：按球员、对手或组合筛选历史对战数据
- **数据可视化**：打击率、防御率等统计图表
- **PDF 导入**：自动解析比赛 PDF 并导入数据
- **数据导出**：支持导出 CSV 文件

### 技术亮点
- 竞技风格 UI（深色主题 + 红色强调色）
- 响应式设计，支持移动端
- SQLite 数据库，无需额外配置
- Docker 容器化部署支持

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Flask 2.3.3 |
| ORM | Flask-SQLAlchemy 3.0.5 |
| 数据迁移 | Flask-Migrate 4.1.0 |
| 数据库 | SQLite |
| 数据分析 | pandas 2.2.3 |
| 图表 | matplotlib 3.9.2 / seaborn 0.13.2 / plotly 5.24.1 |
| PDF 解析 | pdfplumber 0.11.4 |
| 前端 | Bootstrap 5 + 原生 JavaScript + jQuery + DataTables |
| 样式 | Tailwind CSS CDN |

## 数据结构

### 核心表

| 表名 | 说明 |
|------|------|
| `players` | 球员主档案（姓名、背号、主位置、是否投手） |
| `positions` | 守备位置字典表 |
| `player_positions` | 球员-位置多对多关系 |
| `fielder_profiles` | 打击与守备汇总统计 |
| `pitcher_profiles` | 投球汇总统计 |
| `game_records` | 单场比赛原始记录 |

### 业务规则

- `is_pitcher = true` 时自动拥有「投手」位置，仍可兼守其他位置
- 每个球员都有 `fielder_profile`，投手额外拥有 `pitcher_profile`
- 比赛记录写入后自动同步更新汇总档案

## 页面入口

| 路径 | 功能 |
|------|------|
| `/` | 首页 - 数据总览与快捷入口 |
| `/players` | 球员列表 |
| `/add_player` | 添加球员 |
| `/game_stats` | 比赛数据总览 |
| `/add_game_record` | 添加比赛记录 |
| `/stats` | 综合统计与图表 |
| `/matchup_stats` | 对局信息统计 |
| `/pdf_viewer` | 历年比赛 PDF 查看 |
| `/upload_pdf` | 上传 PDF 导入比赛数据 |

## API 接口

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
GET    /api/stats/visualization        # 可视化图表
GET    /api/stats/batting_leaderboard  # 打击排行榜
GET    /api/stats/pitching_leaderboard # 投手排行榜
GET    /api/visualization/batting      # 打击可视化
GET    /api/visualization/pitching     # 投球可视化
GET    /api/export/csv                 # 导出 CSV
```

### 对局信息

```
GET    /api/matchup/opponents           # 获取所有对手列表
GET    /api/matchup/search_records      # 按条件查询比赛记录
GET    /api/matchup/all_game_records    # 获取全队所有比赛记录
DELETE /api/matchup/game_record/<id>    # 删除比赛记录
```

### PDF

```
GET  /api/pdf/files           # 获取 PDF 文件列表
GET  /api/pdf/view/<path>     # 查看 PDF 内容
GET  /api/pdf/parse/<path>    # 解析 PDF（预览）
POST /api/pdf/import_all      # 批量导入所有 PDF
POST /api/pdf/import_one      # 导入单个 PDF
POST /api/pdf/upload          # 上传并解析 PDF
POST /api/pdf/confirm_import  # 确认导入已解析的数据
```

## 环境要求

- Python 3.11 或 3.12
- pip

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/baseball-team-management.git
cd baseball-team-management
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务

```bash
python app.py
```

启动后访问：http://127.0.0.1:5000

数据库文件将自动创建在 `instance/baseball_players.db`。

### 4. 初始化示例数据（可选）

```bash
python init_db.py
```

## Docker 部署（不再主动维护，仅保留作为回退方案）

> ⚠️ **2026 年起的部署推荐直接用 Python + systemd / supervisor / Render / Fly.io 等平台。**
> 本项目的 `Dockerfile` 与 `docker-compose.yml` 仅作为历史回滚保留，未做主动测试。

如确需 Docker 部署（仅参考）：

```bash
# 必须先设置 SECRET_KEY 环境变量
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
docker-compose up -d
```

## 目录结构

```
baseball-team-management/
├── app.py                    # Flask 主入口（约 1700 行，所有路由）
├── config.py                 # 配置类（Production/Development/Testing）
├── database.py               # 数据模型 + 迁移 + 默认管理员
├── pdf_parser.py             # PDF 解析模块
├── import_pdfs.py            # PDF 批量导入脚本
├── init_db.py                # 初始化数据库（含示例数据）
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 构建文件（保留为回退方案）
├── docker-compose.yml        # Docker Compose 配置
├── .env.example              # 环境变量模板
├── scripts/                  # 一次性使用脚本（dedupe 等）
├── templates/                # HTML 模板
│   ├── base.html             # 公共布局（含 nav/arena 背景）
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
│   └── ...
├── static/                   # 静态资源
│   ├── css/
│   │   └── arena.css         # 合并的全局样式（竞技风）
│   └── js/
│       ├── tailwind.config.js  # Tailwind 共享配置
│       ├── util.js             # 通用工具（showAlert 等）
│       ├── script.js           # 球员/统计相关（旧版，新版拆分中）
│       └── ...
├── data/                     # PDF 数据文件目录
│   ├── 2023/
│   ├── 2024/
│   └── 2025/
└── instance/                 # 数据库文件目录
    └── baseball_players.db
```

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

### 对局信息统计

- 支持按球员、对手或组合筛选
- 结果分开展示打击记录和投球记录
- 空记录自动隐藏

### PDF 导入

1. 将 PDF 文件放入 `data/` 目录（按年份分子目录）
2. 访问 `/upload_pdf` 上传或选择已有 PDF
3. 预览解析结果后确认导入

PDF 文件命名格式建议：`队伍A_vs_队伍B_月_日_年.pdf`

例如：`北京工业大学_vs_北京交通大学_Nov_16_2024.pdf`

## 安全注意事项

⚠️ **部署到公网前请配置以下环境变量：**

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
# 编辑 .env，至少设置：
#   SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
#   ADMIN_PASSWORD=<首次启动创建的管理员密码>
```

关键环境变量：

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | 生产必填 | Flask session/CSRF 加密密钥；缺失时生产模式拒绝启动 |
| `FLASK_ENV` | - | `production` / `development` / `testing`（默认 production） |
| `FLASK_DEBUG` | - | `0` / `1`（默认 0，**生产必须为 0**） |
| `ADMIN_PASSWORD` | 首次部署 | 首次启动创建默认 admin 账号的密码；缺省则随机生成并打印到 stdout |
| `INIT_DEFAULT_ADMIN` | 首次部署 | `1` 才会创建默认 admin，**生产部署后必须改为 `0`** |
| `RATELIMIT_LOGIN` | - | 登录端点速率限制（默认 `5/minute`） |
| `RATELIMIT_API` | - | API 默认速率限制（默认 `60/minute`） |

**已自动启用的安全机制**：

- CSRF 保护（Flask-WTF，登录表单与所有 `/api/*` 之外的写操作）
- 登录速率限制（5 次/分钟/ IP）
- API 速率限制（60 次/分钟/ IP）
- 路径穿越防护（`_safe_data_path` 用 realpath + commonpath 严格校验）
- 错误信息脱敏（数据库错误不直接返回前端）
- 危险调试端点已删除（`/api/debug/*`、`/api/test/*`、`/debug.html`）

## 公网部署功能影响

将此项目部署到公网 GitHub 后，以下功能可能受影响：

| 功能 | 影响 | 说明 |
|------|------|------|
| 本地 PDF 文件访问 | ❌ 不可用 | `data/` 目录中的本地 PDF 文件不会提交到仓库 |
| 本地数据库 | ❌ 不会同步 | `instance/` 目录被 .gitignore 排除，数据库需重新初始化 |
| PDF 上传功能 | ✅ 可用 | 上传的文件保存到 `data/uploads/`，需要持久化存储 |
| 其他所有功能 | ✅ 完全可用 | 球员管理、比赛录入、统计图表等均正常 |

**建议**：公网部署时使用 Docker 并挂载 volume 持久化数据库：

```bash
docker run -d \
  -p 5000:5000 \
  -v ./instance:/app/instance \
  -v ./data:/app/data \
  baseball-app
```

## 后续优化方向

- [x] 用户登录与权限管理
- [ ] Flask 蓝图拆分重构
- [ ] 比赛记录编辑功能
- [ ] 对局信息日期范围筛选
- [ ] 自动备份与导入日志
- [ ] 单元测试覆盖

## 许可证

MIT License

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
6. **部署准备**：Docker 容器化、安全配置检查、文档完善

### AI 辅助开发的最佳实践

- **清晰的提示词**：准确描述需求，AI 能更高效地生成代码
- **迭代优化**：通过多轮对话逐步完善功能细节
- **代码审查**：AI 生成的代码需要人工检查安全性和正确性
- **文档同步**：让 AI 同时更新 README 和代码注释

### 致谢

感谢 Anthropic Claude 和智谱 GLM 提供的强大 AI 能力，使得本项目的快速开发成为可能。