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

## Docker 部署

### 使用 Docker Compose

```bash
docker-compose up -d
```

### 手动构建

```bash
docker build -t baseball-app .
docker run -d -p 5000:5000 -v ./instance:/app/instance -v ./data:/app/data baseball-app
```

## 目录结构

```
baseball-team-management/
├── app.py                    # Flask 主入口
├── database.py               # 数据模型
├── pdf_parser.py             # PDF 解析模块
├── import_pdfs.py            # PDF 批量导入脚本
├── init_db.py                # 初始化数据库（含示例数据）
├── migrate_profiles_sqlite.py # 旧数据库迁移脚本
├── sync_data.py              # 数据同步工具
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 构建文件
├── docker-compose.yml        # Docker Compose 配置
├── templates/                # HTML 模板
│   ├── index.html            # 首页
│   ├── players.html          # 球员列表
│   ├── add_player.html       # 添加球员
│   ├── game_stats.html       # 比赛数据
│   ├── add_game_record.html  # 添加比赛记录
│   ├── stats.html            # 统计图表
│   ├── matchup_stats.html    # 对局信息
│   └── ...
├── static/                   # 静态资源
│   ├── css/
│   └── js/
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

⚠️ **部署到公网前请修改以下配置：**

1. **SECRET_KEY**：`app.py` 第 63 行的 `'your-secret-key-here'` 需要更换为随机强密钥
   ```python
   # 生成随机密钥
   import secrets
   app.config['SECRET_KEY'] = secrets.token_hex(32)
   ```

2. **关闭 Debug 模式**：生产环境设置 `debug=False`
   ```python
   app.run(debug=False, host='0.0.0.0', port=5000)
   ```

3. **数据库文件**：`instance/` 目录已加入 `.gitignore`，确保敏感数据不被提交

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

- [ ] 用户登录与权限管理
- [ ] Flask 蓝图拆分重构
- [ ] 比赛记录编辑功能
- [ ] 对局信息日期范围筛选
- [ ] 自动备份与导入日志
- [ ] 单元测试覆盖

## 许可证

MIT License