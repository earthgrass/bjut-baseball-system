# R6 新增功能规划 — 球员主页 / 角色权限 / 球员形象 / 对手画像 / 球员卡 / 档案生命周期 / 移动端

> **文档定位**：这是**实现说明书**，不是想法清单。照着做即可。
> **面向读者**：接手开发的学弟（以及 review 的我）。
> **基线**：commit `1a23a25`（Phase R5 完成后）· 生产库 27 球员 / 240 比赛记录 · pytest 154 passed
> **成文日期**：2026-10-31
>
> 关联文档：[`API_CONTRACT.md`](../API_CONTRACT.md)（接口契约，改接口必须同步）·
> [`HANDOFF.md`](../HANDOFF.md)（接手须知与坑）·
> [`docs/PHASE_R5_REPORT.md`](PHASE_R5_REPORT.md)（上一阶段的报告，是格式样板）·
> [`# POWER ARENA — 首席开发导师长期规范.md`](../%23%20POWER%20ARENA%20%E2%80%94%20%E9%A6%96%E5%B8%AD%E5%BC%80%E5%8F%91%E5%AF%BC%E5%B8%88%E9%95%BF%E6%9C%9F%E8%A7%84%E8%8C%83.md)（规范，下文简称「规范 §N」）

---

## 0 · 阅读指南

### 0.1 怎么用这份文档

1. **先读第 1 章**（现状）—— 里面每个数字都是实测的，不是估计。
2. **再读第 2 章**（依赖图）和**第 3 章**（公共约定）—— 这两章决定你写代码时的"通用姿势"。
3. **领一张任务卡**（第 12 章），按第 4 章起的对应章节做。
4. **卡住了就停下**（0.3 节）。

### 0.2 任务卡长什么样

第 12 章的每张任务卡包含：

```
编号 · 任务 · 前置 · 改动文件 · 验收标准 · 必须写的测试 · 预估工时
```

- **验收标准**是可勾选的客观事实（"接口返回 200 且 body 有 xxx 字段"），不是"做得好看"。
- **必须写的测试**已经指定了文件名和测试层级（规范 §47 的四层）。

### 0.3 什么时候该停下问人（不要硬猜）

以下三件事**代码判不了**，硬猜会做出一堆要返工的东西：

| # | 问题 | 阻塞 | 找谁 |
|---|---|---|---|
| B1 | 对手球员姓名的字序（`振东 姚` 是姚振东吗？） | R6-5 全部 | 教练 / 球队 |
| B2 | 学号格式、是否唯一、是否直接当登录名 | R6-1 / R6-2 | 球队管理者 |
| B3 | 赛季怎么切（4 月春 + 10/11 月秋？） | R6-4 / R6-6 | 教练 |

另外两类"停下来"的情况：

- **业务规则看不懂**（比如"双赛日算两场还是一场"）→ 问，不要按常识定
- **要改 `metrics.py` 现有公式** → 本轮范围外，单独提 PR 讨论（规范 §46）

### 0.4 本轮（本文档描述的这批）明确不做

- ❌ 不动生产库数据（R6-0 的 `flask db stamp` 是**只读标注**，不改数据）
- ❌ 不重构现有 12 个旧模板（只有 R6-7 点名的页面要迁）
- ❌ 不引入前端框架（规范 §56 禁止 React/Vue）、不引入动画库、不引入外部 AI 服务
- ❌ 不改 `metrics.py` 现有公式口径（本轮全是**新增**指标）
- ❌ 不碰公网部署相关的任何事

---

## 1 · 背景与现状（全部实测，2026-10-31）

### 1.1 数据盘点

| 项 | 值 | 备注 |
|---|---|---|
| 球员 | 27 | 全部是我方，无对手标记 |
| 比赛记录 | 240 | 打击 195 / 投球 45 |
| 比赛日 | 17 个 | 与 `data/` 下 17 份 PDF 一一对应 |
| 对手 | 13 支 | `game_records.opponent` 是**纯字符串**，无外键、无规范化表 |
| PDF 语料 | 17 份 | 2023: 4 / 2024: 7 / 2025: 6 |
| 守备位置 | 9 个 | |
| 库完整性 | `integrity_check` ok · FK 违规 0 · 档案漂移 0 | |

### 1.2 `players` 表现状 —— 只有 8 列，且有三个"半成品"字段

```
id, name, jersey_number, primary_position, is_pitcher, birth_date, join_date, contact_phone
```

| 字段 | 状态 | 问题 |
|---|---|---|
| `birth_date` | **有列、无写入路径** | 不在 `to_dict()` 里 → 接口永远不返回，界面永远不显示，没人能改 |
| `contact_phone` | **有列、无写入路径** | 同上 |
| `join_date` | 有写入、但**语义是错的** | `POST /api/players` 里自动设为当天 → 27 人全是 2025-12-05/06（建库那天），**不是真实加入日期** |

> ⚠️ 做球员主页时**不要把 `join_date` 当"加入日期"显示**。真实加入日期用新字段 `enrolled_at`（见 6.2）。

另外：旧文档说的"42 列里 36 列 legacy 孤儿列"是笔误 —— 实际是 **34 列**，且已在 2026-10-28 被物理删除。
删前逐列统计过：34 列在 27 行里**全为 0**，真身在 `fielder_profiles` / `pitcher_profiles` / `game_records`。

### 1.3 权限现状 —— 只有一个布尔，且没有第二个账号的来源

```
users 表: id, username(unique), password_hash, is_admin(default=True), created_at
```

| 事实 | 证据 |
|---|---|
| `is_admin` 是**唯一**的权限维度 | `app.py` 的 `admin_required` 只看这一个字段 |
| `admin_required` 被用了 **16 处** | 全部写操作都靠它 |
| 登录**不校验**角色 | `login_submit` 只查 username+password，成功就 `login_user` |
| **没有任何代码能创建非管理员账号** | `create_admin.py`、`init_default_admin()`、`scripts/reset_admin_password.py` 都恒 `is_admin=True` |
| 实际只有 1 个用户 | `docs/DB_INVENTORY.md` 记录 `users=1` |

> 结论：**"非管理员能登录"这条路存在，但账号没有来源**。要做角色系统，第一步就是补账号的创建与管理。

### 1.4 对手数据现状 —— 库里没有，但 PDF 里全有

这是本轮最重要的发现，直接决定 R6-5 的可行性。

| 层次 | 有没有对手球员数据 | 证据 |
|---|---|---|
| 数据库 | ❌ **无** | 7 张表里没有任何 opponent 相关表；`players` 表无对手标记 |
| 解析结果 | ❌ **无** | `pdf_parser_columns.py` 里 `ours, _theirs = sides(...)`，**`theirs` 接了不用**；表头阶段的 `right_cols` 也算了却从不使用 |
| 写库 | ❌ 无 | `import_pdfs.py` 只写 `my_team_batting` / `my_team_pitching` |
| API | ❌ 无 | `/api/matchup/*` 6 条路由全部只返回**我方** `GameRecord` 的聚合 |
| **PDF 原文** | ✅ **全有** | 实测 dump 坐标：对手栏有逐人打击（AB/R/H/RBI/BB/SO）、逐人投球（IP/H/R/ER/BB/SO/HR）、extras 标签（2B/3B/HR/TB/SB/CS/HBP/BF/P-S/W/L/WP/LOB）、**以及对手全队 Totals 行**。17/17 份全部存在 |

**实测样例**（`data/2025/北京工业大学_vs_北京科技大学_Nov_15_2025.pdf`，对手 = 北京科技大学）：

```
我方 Totals:  AB 13 · R 15 · H 7 · RBI 13 · BB 9 · SO 3
对手 Totals:  AB  8 · R  0 · H 1 · RBI  0 · BB 0 · SO 6
我方投球 Totals: IP 2.0 · H 1 · R 0 · ER 0 · BB 0 · SO 6 · HR 0
对手投球 Totals: IP 2.0 · H 7 · R 15 · ER 15 · BB 9 · SO 3 · HR 0
```

> 顺带：**比分数据（`北京工业 15 - 0 北京科技`）也在这两行 Totals 里，现在完全没解析**。
> R6-5c 的"球队战绩"要用的就是它。

**已验证**：用**现成的** `_split_by_boundary` / `_header_columns` / `_parse_player_block` 三个 helper
做只读验证，**17 份 PDF 的对手栏全部能解析出对手球员名单**（每份 9–15 名打者 + 2–8 名投手 + 双方 Totals）。
**不需要新写几何算法** —— 这是 R6-5 可行的关键依据。

### 1.5 现有页面与前端骨架

| 事实 | 详情 |
|---|---|
| 15 个模板，**只有 3 个继承 `base.html`** | `batch_entry.html` / `import_pdf.html` / `login.html`；其余 12 个是独立完整 HTML（各自复制 head + CSS + navbar） |
| `players.html` 内联 CSS 就 360 行 | 全站内联 CSS 共 2,667 行，`arena.css` 只有 357 行且只有 `base.html` 在用 |
| 导航栏有 11 份副本 | `_navbar.html` 是唯一正本（桌面端 + 移动端两处链接），旧模板各复制了一份 |
| 前端零构建 | Tailwind CDN + 原生 JS；`api.js` 是唯一 API 层，`toast.js` 是唯一提示组件 |
| 仓库里**没有任何图片文件** | png/jpg/svg 全是 0 —— 图标全是内联 SVG 复制粘贴 |

**`base.html` 的 4 个 block**（新页面一律继承它，不要再抄整段 head）：

```jinja
{% block title %}      {# 页面标题 #}
{% block extra_head %} {# 额外 <style> / <meta> #}
{% block content %}    {# 主体 #}
{% block scripts %}    {# 页面专属 <script> #}
```

### 1.6 现状里"能直接复用"的东西（做 R6 时别重写）

| 资产 | 位置 | 用途 |
|---|---|---|
| `_safe_data_path()` | `app.py` | 路径穿越防护（`realpath` + `commonpath` 严格前缀比对） |
| PDF 上传的完整校验链 | `app.py` 的上传接口 | 扩展名白名单 + **魔数校验** + 大小上限 + 重名避让，证件照上传照抄 |
| `PLAYER_METADATA_FIELDS` / `PLAYER_STATS_FIELDS` | `app.py` | PUT 的字段边界（统计字段一律 400） |
| `metrics.py` | 全项目唯一公式源 | 对手球员的指标**原样复用** |
| `rebuild_player_stats()` | `database.py` | 档案重算的唯一入口 |
| `api.js` / `toast.js` | `static/js/` | 前端 API 层 / 提示组件 |
| `arena.css` 组件类 | `static/css/arena.css` | `mecha-card` / `stat-card` / `energy-line` / `scan-line` / `badge` / `btn-primary` |
| `prefers-reduced-motion` 降级 | `arena.css` 底部 | 动画必须支持无障碍降级 |
| `scripts/validate_pdf_parse.py` 的 `our_totals()` | 该脚本 | **复制一份 `their_totals()`** 就是对手侧的金标准校验 |
| `import_pdfs.py` 的 `PLAYER_NAME_ALIASES` | 该文件 | 对手别名的同构写法 |
| `scripts/migrate_r5_metrics.py` | `scripts/` | 「副本迁移 → 报告 → `--apply`」的现成骨架，R6 各阶段的迁移照它写 |

---

## 2 · 总体架构与阶段依赖

```
                        ┌─────────────────────────────┐
                        │ R6-0 Alembic 基建（前置）    │
                        │  所有"加列"任务的地基         │
                        └──────────────┬──────────────┘
                     ┌─────────────────┼─────────────────┐
                     ▼                 ▼                 ▼
        ┌────────────────────┐ ┌──────────────┐ ┌──────────────────────┐
        │ R6-1 角色系统       │ │ R6-5b 对手落库│ │ R6-7 移动端改版       │
        │ + 用户管理         │ │ ← R6-5a 解析  │ │ （可并行，随时做）     │
        │ + 球员账号绑定     │ │   +金标准校验 │ │                      │
        └─────────┬──────────┘ └──────┬───────┘ └──────────────────────┘
                  │                   │
       ┌──────────┴────────┐   ┌──────┴──────────────┐
       ▼                   ▼   ▼                     ▼
┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐
│ R6-2 球员主页 │  │ R6-6 档案生命 │  │ R6-5c 对手画像报告       │
│ + 私有字段    │  │ 周期         │  │                        │
└──────┬───────┘  └──────────────┘  └────────────────────────┘
       ▼
┌──────────────┐
│ R6-3 球员形象 │
└──────┬───────┘
       ▼
┌──────────────┐
│ R6-4 球员卡导出│
└──────────────┘
```

**建议推进顺序**：

```
R6-0 → R6-1 → R6-2 → R6-3 → R6-4 → R6-5a → R6-5b → R6-5c → R6-6 → R6-7
```

**为什么 R6-7 放最后**：前面新写的页面如果一开始就按响应式写，能省一半返工；
但 R6-7 要动的是 12 个历史模板，越晚动越不容易和别人的改动打架。

**为什么 R6-5a 必须先于 R6-5b**：a 阶段不落库、只做"解析 + 用 PDF 自己的 Totals 校验"，
能在写任何表之前就确认解析是对的；b 阶段才建表落库。**反过来做（一上来就建表）会让错误数据进库**。

---

## 3 · 公共约定（所有阶段通用）

### 3.1 命名

| 对象 | 约定 | 例子 |
|---|---|---|
| 数据库表 | 复数 snake_case | `opponent_players` |
| 模型类 | 单数 CamelCase | `OpponentPlayer` |
| API 路径 | `/api/<资源>`，复数 | `/api/opponents/<id>/players` |
| 页面路径 | `/<资源>`，复数；详情用 `/<资源>/<id>` | `/players/7` |
| 私有字段接口 | 挂在资源下，用 `/private` 后缀 | `/api/players/7/private` |
| 前端 JS | `static/js/<页面>.js`，全小写下划线 | `static/js/player_detail.js` |
| 模板 | `templates/<页面>.html` | `templates/player_detail.html` |

### 3.2 返回结构与错误（照抄 `API_CONTRACT.md` §1）

```python
# 成功
return jsonify({'player': player.to_dict()}), 201
return jsonify(data), 200

# 失败 —— 一律这个形状，中文消息
return jsonify({'error': '球员不存在'}), 404
return jsonify({'error': '学号已被占用'}), 400
```

- 参数校验：`request.args.get('x', type=int)`，非法值给 400
- 读操作不加 CSRF；写操作前端必须走 `api.post/put/del`（自动带 CSRF）
- 写操作加权限装饰器（见 3.3）

### 3.3 权限装饰器

```python
# app.py —— 现有的 admin_required 保留不动（16 处调用零改动）
@app.route('/admin/users', methods=['GET'])
@role_required('admin')
def admin_users_page():
    ...
```

新装饰器签名：

```python
def role_required(*roles):
    """要求当前用户具备其中任一角色。未登录 → 跳登录页；角色不符 → 403 或跳登录页。"""
```

> **约定**：新写接口一律用 `role_required(...)`，不要再用 `admin_required`。
> `admin_required` 保留为 `role_required('admin')` 的别名（它已被 16 处引用，不动更安全）。

### 3.4 文件上传（证件照专用）

照抄 PDF 上传的完整校验链：

```python
# 1) 扩展名白名单
ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp'}
# 2) 大小上限（config.py 里另设一个，别改 MAX_CONTENT_LENGTH）
MAX_PHOTO_BYTES = 5 * 1024 * 1024
# 3) 魔数校验 —— 读文件头判断真实类型，防止改扩展名伪装
#    PNG: b'\x89PNG\r\n\x1a\n'  JPEG: b'\xff\xd8\xff'  WEBP: b'RIFF....WEBP'
# 4) 落盘前重命名（不要用原始文件名）
# 5) 落盘位置：data/uploads/players/<player_id>.<ext>
#    （data/uploads/ 已被 .gitignore 覆盖，规范 §51 禁止跟踪 runtime 文件）
```

> ⚠️ **路径校验必须用 `_safe_data_path()` 同款写法**（`realpath` + `commonpath`）。
> 规范 §31 明确禁止用 `path.startswith('data')` 这类判断。

### 3.5 前端页面骨架

新页面**一律继承 `base.html`**（不要再抄整段 head）：

```jinja
{% extends 'base.html' %}
{% block title %}球员档案 - POWER ARENA{% endblock %}
{% block extra_head %}<link rel="stylesheet" href="{{ url_for('static', filename='css/player_avatar.css') }}">{% endblock %}
{% block content %}
  <!-- 分区：身份卡 / 数据卡 / 记录表 / 对手维度 -->
{% endblock %}
{% block scripts %}
  <script src="{{ url_for('static', filename='js/player_detail.js') }}"></script>
{% endblock %}
```

- `base.html` 已提供：`<meta name="csrf-token">`、`api.js`、`toast.js`、`_arena_bg.html`、`_navbar.html`
- 用 Tailwind + `arena.css` 的组件类；**Bootstrap 已移除**（不要写 `alert alert-*` / `.card` / `table-success`）
- 渲染用户数据进 HTML 前**必须转义**（参考 `templates/players.html` 的 `escapeHtml()`）
- 表格/按钮在窄屏下要能用（见 R6-7 的卡片式布局规范）

### 3.6 测试要求（每个阶段都要有这四层，规范 §47）

| 层 | 放哪 | 例子 |
|---|---|---|
| Level 1 Unit | `tests/test_<功能>_baseline.py` | 纯函数：形象生成规则、特点分类阈值、姓名归一 |
| Level 2 Service | 同上 | 建号、改角色、绑定球员、落库事务 |
| Level 3 API | 同上 | 状态码、JSON 结构、权限拒绝、字段边界 |
| Level 4 Smoke | 同上 | 登录 → 进页面 → 关键 DOM id 存在 |

**页面契约测试的写法**（这是本项目事实上的前端契约，直接抄）：

```python
def test_player_detail_renders(auth_client):
    resp = auth_client.get('/players/7')
    assert resp.status_code == 200, resp.status_code
    html = resp.data.decode('utf-8')
    assert 'id="playerName"' in html
    assert 'id="playerAvatar"' in html
    assert 'id="playerStatsCard"' in html
    assert 'name="csrf-token"' in html
```

**JS 单测的写法**（`node --test` + CommonJS 导出，抄 `tests/js/batch_entry.test.js`）：

```javascript
const test = require('node:test');
const assert = require('node:assert');
const mod = require('../../static/js/player_detail.js');
test('学号在非管理员视角下不出现', () => {
    assert.strictEqual(mod.privateFieldsFor('coach'), null);
});
```

> **DOM id 交叉检查**：JS 里 `$('xxx')` 引用的每个 id 都必须存在于模板里。
> `tests/js/batch_entry.test.js` 里有一段现成的检查代码，抄过来改成你的 id 清单 ——
> 一个 id 拼错，页面会**静默**失去某个功能，没有任何报错。

### 3.7 迁移纪律（规范 §6 / §24 / §25 / §26）

任何 schema 变更：

```
1. 在生产库**副本**上跑（scripts/migrate_r5_metrics.py 是现成骨架）
2. row loss 必须为 0
3. Fresh DB（新建空库）也要能跑通
4. 出迁移报告（行数对照 + 指纹 + FK check + 业务不变量）
5. 才考虑生产库；生产库执行前自动备份
```

**测试绝对不能碰生产库** —— `tests/conftest.py` 的 fail-fast 与 SHA 看门狗已经在守这条，别绕过它。

### 3.8 可观测性（规范 §59）

以下事件要 `logging`：`login` / `failed_login` / `player_create` / `player_delete` /
`game_create` / `game_delete` / `pdf_import` / `stats_rebuild` / `migration` /
**`user_create` / `user_role_change` / `account_bind`**（R6-1 新增）

> **禁止** log：密码、secret、session cookie、CSRF token、**学号与证件照路径**（个人信息）。

---

## 4 · R6-0 · Alembic 基建（前置）

### 4.1 为什么这是第一件事

规范 §24：**「Migration 必须使用 Alembic / Flask-Migrate，新 schema 不要继续扩大手写 SQLite ALTER script」**。

现状：`app.py` 已经 `migrate = Migrate(app, db)`（Flask-Migrate 4.1.0 已在 `requirements.txt`），
但**没有 `migrations/` 目录** —— 也就是说项目历史上每一次 schema 变更
（`add_indexes.py` / `drop_legacy_columns.py`）都是手写脚本，**规范 §24 从未被真正满足过**。

R6 至少要加 8 个列、3 张表。如果继续手写 ALTER，就是把规范 §24 明令禁止的事再做 8 遍。
**所以 R6-0 必须先做，而且它本身不改变任何数据。**

### 4.2 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-0 |
| **任务** | 初始化 Alembic，产出「初始版本」（等于现有 schema），并把现有库 `stamp` 上去 |
| **前置** | 无 |
| **改动文件** | 新增 `migrations/`（alembic 生成）、`migrations/env.py`（按本项目定制）、可能 `alembic.ini` |
| **预估** | 0.5 天 |

**步骤**：

```bash
flask db init                       # 生成 migrations/ 目录
flask db migrate -m "initial schema"   # 自动生成初始版本（应与现有 schema 一致）
flask db stamp head                 # 把现有生产库标记为"已到 head"（只读标注，不改数据）
```

**关键点**：

1. **生成的初始版本必须与现有 schema 完全一致**。用 `flask db upgrade` 在**空库**上跑一遍，
   然后和 `instance/baseball_players.db` 的 `sqlite_master` 逐表比对（表名、列名、列类型、
   索引、唯一约束）。**不一致就停下来改 `env.py` 的 `include_object` 过滤**，不要手改生成的脚本。
2. **`stamp` 是只读的** —— 它只往 `alembic_version` 表写一行版本号，**不改任何业务表**。
   必须在副本上先试一遍，确认 `alembic_version` 是唯一的差异。
3. `migrations/env.py` 要做两件定制（Flask-Migrate 默认值不够用）：
   - `include_object` 过滤掉 SQLite 的内部表（`sqlite_sequence` 等）
   - `render_as_batch=True`（SQLite 不支持 `ALTER COLUMN`，Flask-Migrate 需要 batch 模式）
4. **Fresh DB 验证**（规范 §26）：`DATABASE_FILE=_fresh.db flask db upgrade` 之后，
   新库必须能被 `import app` 正常初始化（`init_db` 建表逻辑与 Alembic 并存时要注意不冲突 ——
   **建议把建表逻辑收敛到 Alembic，`init_db` 只做"补数据"不做"建表"**）。

### 4.3 验收标准

- [ ] `migrations/` 目录入库，`alembic.ini` 的 `script_location` 指向它
- [ ] `flask db upgrade` 在空库上跑通，且 schema 与现有生产库**逐列一致**
- [ ] `flask db stamp head` 在**副本**上跑通，副本与生产库的差异**只有** `alembic_version` 表
- [ ] `flask db current` 在生产库上返回 `head`
- [ ] `python -m pytest -q` 全绿（154 passed 不变）
- [ ] 生产库 SHA256 未变

### 4.4 测试要求

- Level 3：新增 `tests/test_r6_migrations.py`
  - 空库 `flask db upgrade` 后，表集合与 `database.py` 的模型一致
  - `flask db stamp` 后 `alembic_version` 有且仅有一行
  - **测试全程不得碰生产库**（用 `DATABASE_FILE` 指向临时目录，`conftest.py` 已有 fail-fast）

### 4.5 风险

| 风险 | 应对 |
|---|---|
| 自动生成的初始版本与现有 schema 有出入 | 逐列比对；不一致就在 `env.py` 里过滤，而不是手改脚本 |
| `init_db()` 与 Alembic 双重建表 | 收敛职责：Alembic 建表，`init_db` 只补数据；改完跑全量测试 |
| 学弟在生产库上直接 `flask db upgrade` | 文档强调：生产库只允许 `stamp`，`upgrade` 只在副本和空库上跑 |

---

---

## 5 · R6-1 · 角色系统与用户管理

### 5.1 目标

现在权限只有一个布尔 `is_admin`，而且**没有任何创建第二个账号的路径**（`create_admin.py`、
`init_default_admin()`、`scripts/reset_admin_password.py` 都恒 `is_admin=True`）。
本阶段要做到：

- 教练能登录、能录入/修改数据，但**不能**删数据、不能导入 PDF、不能管人
- 队员能登录，只能看**自己的**档案
- admin 全权，并能管理账号
- 账号能绑定到某个球员档案（用学号或用户名）

### 5.2 数据模型

`users` 表加三列（走 Alembic，见 R6-0）：

```python
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='player', nullable=False)   # admin / coach / player
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True, unique=True)
    is_enabled = db.Column(db.Boolean, default=True)   # 停用而不是删除
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).date())
```

> ⚠️ **不要把列名叫 `is_active`** —— `UserMixin` 已经有同名属性（Flask-Login 用它判断
> 账号是否可用），会撞车。用 `is_enabled`。

**`is_admin` 改成派生属性**（不删列语义，只换实现）：

```python
    @property
    def is_admin(self):
        return self.role == 'admin'
```

> 这样 app.py 里现有的 **16 处 `@admin_required`** 与 `_navbar.html` 的显隐逻辑
> **一行都不用改**。学弟只需把 `role` 列加上、把 `is_admin` 从列改成 property。

**迁移**（Alembic）：
1. 加 `role` / `player_id` / `is_enabled` 三列（`role` 默认 `'player'`）
2. 回填：`UPDATE users SET role = 'admin' WHERE is_admin = 1`
3. 删掉 `is_admin` 列（SQLite 走 batch 模式）
4. `is_enabled` 全部置 1

### 5.3 权限装饰器

```python
def role_required(*roles):
    """要求当前用户具备其中任一角色。

    - 未登录 → 重定向到登录页（沿用 login_manager.login_view）
    - 角色不符 → 403（API）或重定向（页面）
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


# 保留旧名，避免 16 处调用点全改（也方便回滚）
admin_required = role_required('admin')
```

**权限矩阵**（逐个接口标注在 `API_CONTRACT.md` §2 的端点表里）：

| 能力 | admin | 教练 | 队员 | 未登录 |
|---|:-:|:-:|:-:|:-:|
| 公开统计 / 排行榜 / 球员主页（公开字段） | ✓ | ✓ | ✓ | ✓ |
| 学号 / 证件照 / 备注 / 联系方式 | ✓ | ✗ | ✗ | ✗ |
| 编辑球员公开元数据（姓名/背号/位置） | ✓ | ✓ | ✗ | ✗ |
| 录入 / 修改比赛记录 | ✓ | ✓ | ✗ | ✗ |
| 删除比赛记录 / 删除球员 / PDF 导入 | ✓ | ✗ | ✗ | ✗ |
| 用户管理 / 改角色 / 绑定账号 | ✓ | ✗ | ✗ | ✗ |

**现有 16 处 `@admin_required` 的重新归类**（学弟要逐个改）：

| 路由 | 现状 | 改成 |
|---|---|---|
| `POST /api/players` | admin | `role_required('admin', 'coach')` |
| `PUT /api/players/<id>` | admin | `role_required('admin', 'coach')` |
| `DELETE /api/players/<id>` | admin | **保持 admin** |
| `POST /api/game_records` | admin | `role_required('admin', 'coach')` |
| `POST /api/game_records/batch` | admin | `role_required('admin', 'coach')` |
| `PUT /api/game_records/<id>` | admin | `role_required('admin', 'coach')` |
| `DELETE /api/matchup/game_record/<id>` | admin | **保持 admin** |
| `POST /api/pdf/upload` / `confirm_import` / `import_all` / `import_one` | admin | **保持 admin** |
| 页面：`/add_player` `/add_game_record` `/batch_entry` | admin | 录入类放宽给教练 |
| 页面：`/upload_pdf` | admin | **保持 admin** |

> ⚠️ **删除类操作一律不放宽**。误删比赛记录是不可逆的（要靠 PDF 重导才能恢复）。

### 5.4 队员账号绑定

- `users.player_id` → `players.id`，一个账号最多绑一个球员，一个球员最多一个账号
- 队员登录后访问 `/players` 时，**第一行是自己的档案**（或直接跳转到 `/players/<我的id>`）
- 未绑定的球员由 admin 在用户管理页手动绑定
- 改绑：先解除旧绑定，再绑新的（唯一约束会挡住重复绑定 → 返回 400「该球员已绑定其他账号」）

### 5.5 接口契约

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/admin/users` | admin | 用户列表（不含密码哈希） |
| POST | `/api/admin/users` | admin | 新建：`username` / `password` / `role` / `player_id`（可选） |
| PUT | `/api/admin/users/<id>` | admin | 改 `role` / `player_id` / `is_enabled` |
| POST | `/api/admin/users/<id>/reset-password` | admin | 重置密码（admin 设新密码） |
| POST | `/api/account/password` | 登录用户 | 改**自己**的密码（需提供旧密码） |

> **不提供 DELETE 用户** —— 停用（`is_enabled=False`）即可。删账号会丢审计痕迹。

### 5.6 页面

`/admin/users`（admin only），继承 `base.html`：

| DOM id | 内容 |
|---|---|
| `usersTableBody` | 用户表：用户名 / 角色 / 绑定球员 / 状态 |
| `userFormModal` | 新建 / 编辑用户表单 |
| `userRoleSelect` | 角色下拉（admin / coach / player） |
| `userPlayerSelect` | 绑定球员下拉（来自 `/api/players`） |
| `resetPasswordModal` | 重置密码 |

### 5.7 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-1 |
| **任务** | 角色字段 + 装饰器 + 用户管理页 + 16 处权限重新归类 |
| **前置** | R6-0（Alembic） |
| **改动文件** | `database.py`（User 模型）、`app.py`（装饰器 + 4 个端点 + 16 处归类）、`templates/admin_users.html`（新）、`static/js/admin_users.js`（新）、`_navbar.html`（加入口，桌面端 + 移动端两处）、`migrations/`（新版本） |
| **验收** | 教练账号能录入不能删除；队员账号只能看自己；admin 能建号改角色；`is_admin` 的 16 处旧调用点行为不变 |
| **测试** | `tests/test_r6_roles.py`：每个角色的正/负用例（Level 3）+ 页面 DOM 契约（Level 4） |
| **预估** | 2 天 |

### 5.8 风险

| 风险 | 应对 |
|---|---|
| 放宽权限后教练误删数据 | 删除类**不放宽**；`DELETE` 一律保持 admin |
| `is_admin` 从列改 property 后有代码直接写它 | 全仓库 grep `is_admin` 确认只读不写 |
| 队员越权看到别人的档案 | 绑定逻辑放在服务端过滤，前端不做鉴权 |
| 忘记改 `_navbar.html` 的移动端入口 | 两处都要改（桌面端 + 移动端） |

---

## 6 · R6-2 · 球员个人主页

### 6.1 目标

一个能讲清"这个人是谁、打得怎么样"的页面：
个人信息 + 生涯数据 + 逐场比赛 + 对手维度 + 形象 + 导出。

### 6.2 数据模型

`players` 表加 5 列：

| 字段 | 类型 | 可见性 | 说明 |
|---|---|---|---|
| `student_id` | VARCHAR(20) nullable **UNIQUE** | 仅 admin | 学号 |
| `photo_path` | VARCHAR(255) nullable | 仅 admin | 证件照相对路径（相对 `data/`） |
| `note` | TEXT nullable | admin + 教练 | 管理备注 |
| `enrolled_at` | DATE nullable | admin + 教练 | **真实**加入日期 |
| `status` | VARCHAR(20) default 'active' | 公开 | 生命周期（R6-6 用） |

> ⚠️ **不要用 `join_date` 当"加入日期"**。它在 `POST /api/players` 里被自动设为当天，
> 27 名球员全是 2025-12-05/06（建库那天），不是真实加入日。显示真实日期用 `enrolled_at`。

> ⚠️ `birth_date` / `contact_phone` 两列**早就存在**但没有写入路径、也不在 `to_dict()` 里 ——
> 本阶段顺手把它们接上（出生日期公开可见，联系方式仅 admin 可见）。

### 6.3 接口契约（分层是安全设计的核心）

| 方法 | 路径 | 权限 | 返回 |
|---|---|---|---|
| GET | `/api/players/<id>` | 公开 | 公开字段：现有 `to_dict()` + `birth_date` + `enrolled_at` + `status` + `avatar_url` |
| GET | `/api/players/<id>/private` | admin | `student_id` / `photo_url` / `note` / `contact_phone` |
| GET | `/api/players/<id>/photo` | admin | 证件照二进制（`Content-Type: image/*`，`Cache-Control: private`） |
| PUT | `/api/players/<id>/private` | admin | 改私有字段（`student_id` / `note` / `contact_phone`） |
| POST | `/api/players/<id>/photo` | admin | 上传证件照（multipart） |
| DELETE | `/api/players/<id>/photo` | admin | 删除证件照 |
| GET | `/api/players/<id>/avatar.svg` | 公开 | 球员形象（R6-3） |

> ⚠️ **证件照绝对不能放进 `static/`**。`static/` 下的一切都是公开可访问的 ——
> 放在那里等于"知道 URL 就能看"，"仅管理员可见"就是假的。
> 必须走 `GET /api/players/<id>/photo` 做权限校验后返回字节。
>
> 文件落 `data/uploads/players/<player_id>.<ext>`（`data/uploads/` 已被 `.gitignore` 覆盖，
> 规范 §51 禁止跟踪 runtime 文件）。

**上传校验**（照抄 `app.py` 现有的 PDF 上传那一套）：

```python
ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_PHOTO_BYTES = 5 * 1024 * 1024
# 魔数校验（防改扩展名伪装）：
#   PNG  b'\x89PNG\r\n\x1a\n'
#   JPEG b'\xff\xd8\xff'
#   WEBP b'RIFF' + b'WEBP'（偏移 8）
# 落盘前重命名，不要用原始文件名
```

路径校验用 `_safe_data_path()` 同款写法（`realpath` + `commonpath` 严格前缀比对），
**禁止**用 `path.startswith('data')`（规范 §31）。

### 6.4 页面

`/players/<id>`，继承 `base.html`：

| 分区 | DOM id | 内容 | 可见性 |
|---|---|---|---|
| ① 身份头 | `playerAvatar` | 形象 SVG | 公开 |
| | `playerName` / `playerJersey` / `playerPosition` / `playerStatusBadge` | 姓名 / 背号 / 位置 / 状态 | 公开 |
| ② 身份卡 | `playerPrivateCard` | 学号 / 证件照 / 联系方式 / 备注 | **仅 admin 有内容**；其他人看到 `playerPrivateMasked` 占位（"该信息仅管理员可见"） |
| ③ 数据卡 | `playerStatsCard` | 打击/投球生涯数据 + R5 的 9 个派生率 | 公开 |
| ④ 比赛记录 | `playerGameRecordsBody` | 逐场记录表 | 公开 |
| ⑤ 对手维度 | `playerVsOpponentsBody` | vs 各对手的表现 | 公开 |
| ⑥ 导出 | `exportCardBtn` | 导出球员卡 | 公开 |

④⑤ 复用现成接口：`/api/matchup/player_game_records` 与 `/api/matchup/player_vs_opponent`。
**不要**为它们新写接口。

### 6.5 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-2 |
| **任务** | 5 个新字段 + 私有接口分层 + 照片上传 + 主页页面 |
| **前置** | R6-0、R6-1（要靠角色才能实现"仅管理员可见"） |
| **改动文件** | `database.py`（Player 模型 + `to_dict()` 分层）、`app.py`（6 个端点）、`templates/player_detail.html`（新）、`static/js/player_detail.js`（新）、`templates/players.html`（每行加"档案"入口）、`_navbar.html` |
| **验收** | 未登录能看到公开字段、**看不到**学号与照片；教练能看到备注、看不到学号与照片；admin 全能看到；非 admin 直接访问照片 URL 被拒 |
| **测试** | `tests/test_r6_player_profile.py`：字段可见性矩阵（每个角色 × 每个字段）、照片上传的魔数/扩展名/大小校验、照片 URL 未授权访问被拒、页面 DOM 契约 |
| **预估** | 2–3 天 |

### 6.6 风险

| 风险 | 应对 |
|---|---|
| 照片放进了 `static/` → 权限形同虚设 | 存 `data/uploads/players/`，只经权限端点提供；测试里有一条专门断言未授权拿不到 |
| `to_dict()` 一把梭返回了学号 | **拆成两个接口**，公开接口物理上不含私有字段（不是"按角色裁剪"） |
| 学号重复 | UNIQUE 约束 + 400 提示 |
| 现有 `PUT /api/players/<id>` 的字段边界被绕过 | 私有字段**只**走 `/private` 端点，不进 `PLAYER_METADATA_FIELDS` |
| 姓名字段里的用户输入没转义 | 渲染前 `escapeHtml()` |

---

## 7 · R6-3 · 球员形象（SVG 程序化生成 + CSS 动画）

### 7.1 目标

每个球员有一张**由数据生成**的形象：同一个球员永远同一个形象，
不同位置/号码/数据的人长得不一样。零外部依赖、离线可用、可测。

> **为什么是程序化生成而不是 AI 生成或美术素材**：
> AI 生成要外部服务、离线不可用、27 个人要 27 次调用、结果不可复现；
> 美术素材要人画、学弟做不了、也放不进 git；
> 程序化生成是纯函数、确定性、可写单测 —— 且**天然契合现有"机甲 / 竞技场"主题**
> （`arena.css` 已有 `mecha-card` / `energy-line` / `scan-line` / `corner-cut`）。

### 7.2 模块

新文件 `avatar.py`（与 `metrics.py` 同级，都是"纯逻辑模块"）：

```python
def build_avatar_svg(player, size=200, seed=None):
    """生成球员形象 SVG。

    纯函数：不碰数据库、不读时间、不用全局随机数（随机由 seed 决定）。
    同一个 (player, seed) 永远得到同一张图。
    """
```

**确定性**：`seed` 默认取 `player.id`；所有"随机"选择都用
`random.Random(seed)` 的实例，**不要**用全局 `random`（全局状态会因调用顺序变化）。

### 7.3 形象规则（照这张表实现）

| 部件 | 由什么决定 | 规则 |
|---|---|---|
| 体型 | 主位置 | 投手 → 宽肩窄腰；捕手 → 壮实；内野 → 中等；外野 → 精瘦 |
| 主色 | 位置 | 沿用现有竞技场配色（`tailwind.config.js` 里的 `arena.red` / `arena.surface2` 等） |
| 帽子颜色 | 是否主力 | 主力 → 队色；替补 → 深灰 |
| 背后号码 | `jersey_number` | 居中，字号随号码位数自适应 |
| 挥棒弧线 | 打击率 | 打击率越高，弧线越长越亮 |
| 投球轨迹 | ERA | ERA 越低，轨迹越直、收束越紧 |
| 速度线 | 盗垒次数 | 数量与长度随盗垒数增加 |
| 边框装饰 | 生涯打数 | 打数越多，装饰层数越多（老将感） |

> 规则的**具体数值**学弟自己定，但必须满足：
> ① 同一个球员两次调用结果**完全一致**（有单测）
> ② 不同球员的形象**肉眼可区分**（有单测：随机取 10 个球员，两两 SVG 字符串不相同）

### 7.4 动画

CSS 写在 `static/css/player_avatar.css`（新文件，不要塞进 `arena.css` ——
`arena.css` 只放全局组件类，页面专属样式各自成文件，见 `batch_entry.html` 的约定注释）。

| 动画 | 触发 | 时长 | 说明 |
|---|---|---|---|
| 待机呼吸 | 常驻 | 3–4s 循环 | 整体轻微缩放 + 上下浮动 |
| 投球动作 | hover（投手） | 0.6s | 手臂前摆 + 轨迹线闪现 |
| 挥棒 | hover（打者） | 0.5s | 球棒扫过 + 弧线描边动画 |
| 数据高亮 | 数字变化时 | 0.3s | 发光脉冲（用 `arena.css` 的 `energy-line` 风格） |

> ⚠️ **必须支持 `prefers-reduced-motion: reduce` 降级** ——
> `arena.css` 底部已有这个模式，照抄它的写法：降级后不播放动画，只显示静态图形。

### 7.5 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-3 |
| **任务** | `avatar.py` 纯函数 + `/api/players/<id>/avatar.svg` 端点 + CSS 动画 + 主页接入 |
| **前置** | R6-2（形象要挂在主页上） |
| **改动文件** | `avatar.py`（新）、`app.py`（1 个端点）、`static/css/player_avatar.css`（新）、`templates/player_detail.html` |
| **验收** | 同一球员两次请求 SVG 字节一致；10 个球员两两不同；动画在 `prefers-reduced-motion` 下降级；SVG 不含外部引用（无外链字体/图片，保证可内联） |
| **测试** | `tests/test_r6_avatar.py`：确定性、不同性、SVG 结构合法（能被 xml 解析）、降级样式存在 |
| **预估** | 2 天 |

### 7.6 风险

| 风险 | 应对 |
|---|---|
| SVG 太大（几百 KB） | 只画必要元素；输出前做长度断言 |
| 用了全局 `random` → 同一人两次不一样 | 只用 `random.Random(seed)` 实例；单测断言确定性 |
| SVG 里引外部字体 → 内联后字体丢失 | 用 `font-family` 兜底到 `system-ui, sans-serif`，不引用 webfont |
| 动画影响低端机性能 | 只动 `transform` / `opacity`（合成层属性），不动布局属性 |

---

## 8 · R6-4 · 球员卡导出（PDF / PNG）

### 8.1 目标

球员主页和排行榜上的"导出"按钮 → 一张可分享的球员卡（PDF 或 PNG）。

### 8.2 方案（零新依赖）

| 格式 | 做法 | 依赖 |
|---|---|---|
| **PDF** | 服务端 `matplotlib` → `PdfPages`，一张卡一页 | 已有（项目已在用 matplotlib 出图） |
| **PNG** | 前端把 SVG 卡 + 数据渲染成 canvas → `toDataURL()` 下载 | 零依赖（不引 html2canvas） |
| **打印** | 前端直接 `window.print()`，配 `@media print` 样式 | 零依赖 |

> 抄 `app.py` 的 `/api/stats/visualization`（`plt.savefig` → `BytesIO` → base64）那套写法。

### 8.3 卡片内容

```
┌────────────────────────────────┐
│  [形象 SVG]   姓名 · 背号 · 位置 │
│────────────────────────────────│
│  打击：AVG / OBP / SLG / OPS    │
│  投球：ERA / WHIP / K/9         │
│  关键：HR / RBI / K / SB        │
│────────────────────────────────│
│  队伍名 · 赛季 · 生成日期        │
└────────────────────────────────┘
```

> ⚠️ **"赛季"这一行暂时写"生涯合计"** —— 赛季切分口径（B3）还没定，
> 定了之后再改这一行（不要在卡里自己按月份猜赛季）。

### 8.4 接口

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/players/<id>/card.pdf` | 公开 | 返回 PDF（`application/pdf`） |
| GET | `/api/stats/leaderboard.pdf` | 公开 | 排行榜 PDF（可选） |

> 排行榜 PDF 的"前 N 名"要写死（比如前 10），别让用户传任意 N —— 参数无界是资源耗尽入口。

### 8.5 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-4 |
| **任务** | 球员卡 PDF 端点 + 前端 PNG/打印导出 + 卡面样式 |
| **前置** | R6-3（形象） |
| **改动文件** | `app.py`（2 个端点）、`static/js/player_detail.js`、`static/css/player_card.css`（新） |
| **验收** | PDF 能打开、内容含形象与核心数据；PNG 下载文件名含球员名；`Content-Disposition` 正确 |
| **测试** | `tests/test_r6_export.py`：PDF magic bytes（`%PDF-`）、Content-Type、非法 player_id 返回 404 |
| **预估** | 1–1.5 天 |

### 8.6 风险

| 风险 | 应对 |
|---|---|
| 中文字体缺失 → PDF 里是方框 | 项目已有中文字体回退（matplotlib 部分），照抄那段配置 |
| 用户传超大 N 打爆服务器 | 前 N 写死上限 |
| 导出的数字和网页不一致 | **数据必须来自同一个 `metrics.py`** —— 不要在导出代码里另算一遍 |

---

## 9 · R6-5 · 对手球员数据链路

> **本阶段是整批里最重的一块**，分三步走，每步都能独立交付、独立验证。

### 9.1 关键前提（先读这段，能省很多困惑）

| 层次 | 有没有对手球员数据 |
|---|---|
| 数据库 | ❌ 没有 —— 7 张表里没有任何 opponent 表；`players` 表也没有对手标记 |
| 解析结果 | ❌ 没有 —— `pdf_parser_columns.py` 里 `ours, _theirs = sides(...)`，**`theirs` 接了不用**；表头阶段的 `right_cols` 也算了却从不使用 |
| 写库 | ❌ 没有 —— `import_pdfs.py` 只写 `my_team_batting` / `my_team_pitching` |
| API | ❌ 没有 —— `/api/matchup/*` 六条路由全部只返回**我方** `GameRecord` 的聚合 |
| **PDF 原文** | ✅ **全有** —— 17/17 份的对手栏都有逐人打击、逐人投球、extras 标签、**以及对手全队 Totals 行** |

实测样例（`data/2025/北京工业大学_vs_北京科技大学_Nov_15_2025.pdf`）：

```
我方 Totals:  AB 13 · R 15 · H 7 · RBI 13 · BB 9 · SO 3
对手 Totals:  AB  8 · R  0 · H 1 · RBI  0 · BB 0 · SO 6
```

> 顺带：**比分数据也在这两行里**（另一份 2026 的 PDF 印着 `中国公安大学 1 - 13 北京工业大学`），
> 现在完全没解析 —— R6-5c 的"球队战绩"要用的就是它。

**已验证**：用**现成的** `_split_by_boundary` / `_header_columns` / `_parse_player_block`
三个 helper 做只读验证，**17 份 PDF 的对手栏全部能解析出对手球员名单**
（每份 9–15 名打者 + 2–8 名投手 + 双方 Totals）。**不需要新写几何算法。**

### 9.2 a 步：解析对手栏 + 金标准校验（先不落库）

**改动点**（`pdf_parser_columns.py`）：

| 位置 | 现状 | 改成 |
|---|---|---|
| `_parse_batting_header` / `_parse_pitching_header` | 已算出 `left_cols` / `right_cols`，但只用一边 | 不变（对方侧要用） |
| 状态机 `sides(words, hdr)` | `ours, _theirs = sides(...)`，对方词被丢 | `ours, theirs = sides(...)`，**对方侧也要走一遍 section 状态** |
| 落数据 | 只解析 `side = left if ours_left else right` | 加一条并行的对方落数循环 |
| extras | 只取我方词喂 `_apply_extras` | 对方侧词也要喂一份（TB 自校验要按对方名单重算） |
| 返回结构 | 只有 `my_team_*` | 加 `their_team_batting` / `their_team_pitching` / `their_team_totals` |

**金标准校验**（`scripts/validate_pdf_parse.py`）：

把该脚本的 `our_totals()` 复制一份 `their_totals()`，
用 **PDF 自己的对手 Totals 行**校验对方解析结果（与我方校验完全同构）：

```python
def their_totals(filepath):
    """对手侧的 Totals 行 —— 解析的真值基准。

    现在的 our_totals() 用 `side = [w for w in words if (w['x0'] < boundary) == ours_left]`
    只取我方那一半；对手侧就是反过来。
    """
```

**a 步的验收标准**：
- [ ] 17 份 PDF 的对手栏都能解析出名单（人数与 PDF 里的行数一致）
- [ ] 每份 PDF 的对手打击合计（AB/H/R/BB/SO 之和）**等于** PDF 自己 Totals 行
- [ ] 每份 PDF 的对手投球局数合计 **等于** PDF 自己 Totals 行
- [ ] **一个字节都不写进数据库**

**⚠️ 三个坑（a 步最容易踩）**：

1. **对方 Totals 行可能与我方某球员的数据行同高**。
   `pdf_parser_columns.py` 的注释里明确记着这个坑（"实测会漏掉 3 人"）——
   对方侧要**重写一遍**这个判定，不能用 `startswith('Totals')`。
2. **extras 行会被误当成球员行**。
   实测 `TB:振中邢,SB:卓陈,` 会被 `_parse_player_block` 解析成"球员"——
   必须严格按 section 走，不能靠"看起来像不像名字"。
3. **对手没有"我方锚点"**。`_is_our_team()` 只认北工大关键词，
   对手侧只能靠"栏界另一侧"定位，不能靠队名关键词。

### 9.3 b 步：落库（独立表，绝不能混进 `players`）

```
opponents             (id, name UNIQUE, created_at)
opponent_players      (id, opponent_id FK → opponents, name, jersey_number,
                       primary_position, is_pitcher)     UNIQUE(opponent_id, name)
opponent_game_records (id, game_date, opponent_id FK, opponent_player_id FK,
                       is_pitching_record, <与 game_records 同名的统计字段…>)
```

> ⚠️ **对手球员绝不能进 `players` 表** —— 会污染我方 27 人档案、
> 破坏 `rebuild_player_stats` 的不变量、还会被 `rebuild_stats.py` 一起重算。

> ⚠️ **字段名必须与 `game_records` 对齐** —— 这是关键设计：
> 这样 `metrics.py` 的公式（AVG/OBP/SLG/ERA/WHIP/BABIP…）可以**原样复用**，
> 对手球员的指标算出来和我方球员**同一套口径**。
> 落库脚本照 `import_pdfs.py` 的事务/幂等/别名那套语义写。

**b 步的验收标准**：
- [ ] 新表建好，`opponent_game_records` 的字段与 `game_records` 一一对应
- [ ] 17 份 PDF 的对手数据全部落库，行数与解析结果一致
- [ ] `opponent_players` 的姓名**无重复**（同一对手内）
- [ ] `PRAGMA foreign_key_check` = 0
- [ ] **我方 `players` 表与 `game_records` 一字未改**（逐字段比对）

### 9.4 c 步：对手画像报告页面

`/opponent_report?opponent=xxx`，公开可看（数据不是秘密，教练需要它）。

| 分区 | 内容 |
|---|---|
| 球队级 | 总战绩、每场比分（比分要从 PDF 的 Totals 行解析）、场均得分 |
| 核心球员 | 按 AVG/OBP/ERA/三振/打数排序 → "谁是他们的核心" |
| 特点分类 | 见下表 |
| 我方对策 | 谁克他、谁被他克（交叉现有 `matchup` 数据） |
| 导出 | PDF（复用 R6-4 的 PDF 能力） |

**特点分类阈值**（学弟可以直接照抄实现，也可以调，但要在文档/代码注释里写清阈值）：

| 类型 | 判定（至少满足一条） |
|---|---|
| 长打型 | SLG ≥ 0.550 或 HR/20AB ≥ 0.4 |
| 短打型 | AVG ≥ 0.320 且 SLG ≤ 0.420 |
| 盗垒型 | SB/20AB ≥ 1.0 |
| 三振型 | K% ≤ 0.120 且 AB ≥ 20 |
| 控球型（投手） | BB/9 ≤ 2.5 且 K/9 ≥ 7.0 |
| 火力型（投手） | ERA ≤ 3.5 且 IP ≥ 5 |

> ⚠️ 阈值是**可调的启发式**，不是真理。UI 上要显示"依据"，让教练知道这是按什么规则分类的
> —— 不要让分类看起来像客观结论。

### 9.5 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-5a |
| **任务** | 解析对手栏 + `their_totals()` 金标准校验（**不落库**） |
| **前置** | 阻塞项 B1（对手姓名字序）**不阻塞 a 步** —— a 步只出名单与合计，不做姓名归并 |
| **改动文件** | `pdf_parser_columns.py`、`scripts/validate_pdf_parse.py` |
| **验收** | 17/17 份的对手合计与 PDF Totals 行吻合 |
| **测试** | `tests/test_r6_opponent_parse.py`：对手合计 == PDF Totals（参数化 17 份） |
| **预估** | 2–3 天 |

| 项 | 内容 |
|---|---|
| **编号** | R6-5b |
| **任务** | 三张新表 + 落库脚本 + 迁移 |
| **前置** | R6-0、R6-5a、**阻塞项 B1 已解决** |
| **改动文件** | `database.py`（3 个模型）、`import_pdfs.py`（写对方表）、`scripts/migrate_r6_opponents.py`（新）、`migrations/` |
| **验收** | 对手数据全部落库；我方数据一字未改；迁移在副本上先验（row loss = 0） |
| **测试** | `tests/test_r6_opponent_db.py`：表结构、外键、不变量（AB≥H 等） |
| **预估** | 2–3 天 |

| 项 | 内容 |
|---|---|
| **编号** | R6-5c |
| **任务** | 画像报告页 + 特点分类 + 比分解析 |
| **前置** | R6-5b |
| **改动文件** | `app.py`（端点）、`templates/opponent_report.html`（新）、`static/js/opponent_report.js`（新） |
| **验收** | 13+ 个对手各能出报告；比分与 PDF 一致；特点分类有"依据"可查 |
| **测试** | `tests/test_r6_opponent_report.py`：分类阈值单测 + 页面 DOM 契约 |
| **预估** | 2–3 天 |

### 9.6 风险

| 风险 | 应对 |
|---|---|
| **对手姓名字序反了**（B1） | 未解决前**不要落库** —— 一堆反序名字进了库，画像全是错的 |
| 对手 Totals 行与我方行同高 → 漏人 | 用 `their_totals()` 校验，漏人立刻暴露 |
| extras 行被当球员 | 严格按 section 走 + 金标准校验 |
| 对手球员跨年认不出同一人（2023 版式无背号） | 归并规则要人工确认（B1 一并问） |
| 对手数据与 2026 新赛季格式不同 | a 步的 17 份校验里加 2026 那几份 |
| 表名字段和 `game_records` 漂移 | 两边共用一份列定义（mixin 或常量），别手抄两遍 |

---

## 10 · R6-6 · 球员档案生命周期

### 10.1 目标

现在库里只有"现役"这一种状态。真实管理里需要：毕业、离队、转学、伤停。

### 10.2 数据模型

```python
# players 表
status      = Column(String(20), default='active')   # active/inactive/graduated/transferred
left_at     = Column(Date, nullable=True)             # 离开日期
left_reason = Column(String(100), nullable=True)      # 毕业/转学/伤病…

# users 表
is_enabled  = Column(Boolean, default=True)           # R6-1 已加，这里复用
```

**状态语义**：

| status | 含义 | 出现在名单页 | 出现在统计里 |
|---|---|---|---|
| `active` | 在队 | ✓ | ✓ |
| `inactive` | 在队但不参赛（伤病/休学） | ✓（可筛掉） | ✓ |
| `graduated` | 毕业离队 | 默认折叠 | ✓ **历史数据保留** |
| `transferred` | 转学/转队 | 默认折叠 | ✓ |

> ⚠️ **归档不删数据**。毕业球员的历史记录必须保留可查 ——
> 队长三年前的击球率是球队的记忆，也是"这个项目培养过谁"的证据。

### 10.3 界面与接口

| 能力 | 做法 |
|---|---|
| 名单页筛选 | `templates/players.html` 加状态下拉，默认只显示 `active` |
| 标记归档 | `PUT /api/players/<id>/lifecycle`（admin/coach）：`status` / `left_at` / `left_reason` |
| 查看归档球员 | `GET /api/players?status=graduated` |
| 停用账号 | R6-1 的 `PUT /api/admin/users/<id>`（`is_enabled`） |

### 10.4 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-6 |
| **任务** | 状态字段 + 归档接口 + 名单页筛选 |
| **前置** | R6-0、R6-1、R6-2（主页要显示状态徽章） |
| **改动文件** | `database.py`、`app.py`、`templates/players.html`、`templates/player_detail.html` |
| **验收** | 归档球员的历史数据仍可查；名单页能按状态筛；归档不删任何 `game_records` |
| **测试** | `tests/test_r6_lifecycle.py`：归档后记录数不变、筛选正确 |
| **预估** | 1 天 |

---

## 11 · R6-7 · 移动端优先改版

### 11.1 现状

- 15 个模板里**只有 3 个继承 `base.html`**（`batch_entry` / `import_pdf` / `login`），
  其余 12 个是独立完整 HTML（各自复制 head + CSS + navbar）
- `players.html` 内联 CSS 就 360 行，全站内联 CSS 共 2,667 行
- 导航栏 11 份副本
- 表格在窄屏只能横向滚动；旧模板的 navbar **没有移动端菜单**（只有 `base.html` 那一版有）

### 11.2 任务

1. **把高频页迁到 `base.html`**：`players` / `player_detail` / `stats` / `matchup_stats` /
   `game_stats` / `add_game_record`（一次迁一个，迁完跑全量测试）
2. **表格 → 卡片式响应布局**：窄屏下每行变一张卡片（用 Tailwind 的 `hidden md:table-cell` 之类）
3. **`/batch_entry` 移动端优化** —— 这是最高频场景（球场边录入）
4. **球场边录入的"大按钮"模式**：单手可点，误触保护

### 11.3 任务卡

| 项 | 内容 |
|---|---|
| **编号** | R6-7 |
| **任务** | 模板迁移 + 响应式布局 + 移动端录入优化 |
| **前置** | 建议放在最后（前面的新页面本来就用响应式写法，能省一半返工） |
| **改动文件** | `templates/*.html`、`static/css/arena.css`（补响应式工具类） |
| **验收** | 375px 宽度下：导航可展开、表格变卡片、批量录入可完成一整场 |
| **测试** | 现有的 DOM id 契约测试（迁移后 id 不能变）；JS↔模板交叉检查仍然通过 |
| **预估** | 3–5 天（分页做） |

> ⚠️ **迁模板时不要改 DOM id** —— `tests/js/` 里的 DOM id 交叉检查依赖它们。
> 只搬结构，不改契约。

---

## 12 · 任务卡汇总（可勾选清单）

| 编号 | 任务 | 前置 | 预估 | 阻塞 |
|---|---|---|---|---|
| R6-0 | Alembic 基建 | — | 0.5 天 | — |
| R6-1 | 角色系统 + 用户管理 | R6-0 | 2 天 | B2 |
| R6-2 | 球员主页 + 私有字段 + 照片 | R6-0, R6-1 | 2–3 天 | B2 |
| R6-3 | 球员形象 SVG + 动画 | R6-2 | 2 天 | — |
| R6-4 | 球员卡导出 | R6-3 | 1–1.5 天 | B3（卡片上的赛季行暂写"生涯合计"） |
| R6-5a | 解析对手栏 + 金标准校验 | — | 2–3 天 | — |
| R6-5b | 对手表 + 落库 + 迁移 | R6-0, R6-5a | 2–3 天 | **B1** |
| R6-5c | 对手画像报告 | R6-5b | 2–3 天 | — |
| R6-6 | 档案生命周期 | R6-0, R6-1, R6-2 | 1 天 | B3（毕业时间） |
| R6-7 | 移动端改版 | — | 3–5 天 | — |

**总计约 19–24 个工作日**（不含等待业务确认的时间）。

**建议顺序**：R6-0 → R6-1 → R6-2 → R6-3 → R6-4 → R6-5a → R6-5b → R6-5c → R6-6 → R6-7

---

## 13 · 测试与验收总则

### 13.1 四层测试（规范 §47）

| 层 | 放哪 | 覆盖 |
|---|---|---|
| Level 1 Unit | `tests/test_<功能>_baseline.py` | 形象生成、特点分类阈值、角色判定、文件名解析 |
| Level 2 Service | 同上 | 建号、改角色、绑定球员、归档、落库事务 |
| Level 3 API | 同上 | 状态码、JSON 结构、权限拒绝、字段边界、上传校验 |
| Level 4 Smoke | 同上 | 登录 → 进页面 → 关键 DOM id 存在 |

### 13.2 每个阶段都要跑的

```bash
python -m pytest -q          # 与 CI 一致（不要用裸 pytest）
node --test 'tests/js/*.test.js'
ruff check .
python scripts/verify_e2e.py # 端到端 30 项，生产库 SHA 不变
```

> ⚠️ 裸 `pytest` 不把当前目录塞进 `sys.path`，会 `ModuleNotFoundError: No module named 'database'`。

### 13.3 完整性检查（规范 §48）

```python
PRAGMA foreign_key_check        # 孤儿行
PRAGMA integrity_check          # 库完整性
重复业务键                       # UNIQUE 约束
负值 / NULL 异常
```

### 13.4 棒球业务不变量（规范 §49）

导入与写入后必须成立：

```
AB >= H · PA >= AB · H >= 2B + 3B + HR · IP >= 0 · ER >= 0 · SO >= 0 · BB >= 0
```

> 对手数据（`opponent_game_records`）**同样要查** —— 对手球员的记录也是记分卡解析出来的。

### 13.5 迁移纪律（规范 §6 / §24 / §25 / §26）

```
1. 生产库副本上演练
2. row loss 必须为 0
3. Fresh DB 与 Legacy DB 都要能跑通
4. 指纹 + 行数 + FK check + 业务不变量 + API smoke
5. 出迁移报告
6. 才考虑生产库；生产库执行前自动备份
```

**迁移报告模板**：抄 `scripts/migrate_r5_metrics.py` 与 `scripts/migrate_r6_2026.py`
（它们已实现"副本 → 报告 → `--apply` 自动备份"这套骨架）。

---

## 14 · 风险登记簿

| # | 风险 | 影响 | 概率 | 应对 | 责任阶段 |
|---|---|---|---|---|---|
| 1 | 对手姓名字序反了（B1） | 对手画像全是错的 | 高 | 未解决不落库 | R6-5b |
| 2 | 证件照放 `static/` | 权限形同虚设 | 中 | 只经权限端点提供 + 专项测试 | R6-2 |
| 3 | 角色放宽过头 | 教练误删数据 | 中 | 删除类不放宽 | R6-1 |
| 4 | Alembic 初始版本与现有 schema 不一致 | 迁移到一半炸 | 中 | 逐列比对 + 空库 upgrade 验证 | R6-0 |
| 5 | 新派生率与老派生率口径打架 | 网页和 CSV 不一致 | 中 | 全部来自 `metrics.py` | 全程 |
| 6 | 模板迁移改动了 DOM id | 前端功能静默失效 | 中 | 只搬结构不改 id；DOM 契约测试守着 | R6-7 |
| 7 | 12 个旧模板的重复 CSS 没清 | 改一处漏三处 | 高 | R6-7 迁一个删一个 | R6-7 |
| 8 | 赛季口径没定 | 赛季卡/生命周期口径不一致 | 高 | 暂时用"生涯合计"，别自己猜 | B3 |
| 9 | 导入 2026 后数据量变大 | 查询变慢 | 低 | 现有 5 个索引已覆盖热点表 | — |
| 10 | 有人绕过 API 直接改库 | 不变量被破坏 | 中 | 测试隔离 + 只读生产库 + canary | 全程 |

---

## 15 · 待确认问题清单（给教练 / 球队）

### 15.1 阻塞项（不解决做不下去）

**B1 · 对手球员姓名的字序**
> 实测：部分 PDF 的对手姓名是"名姓"反序 —— `振东 姚`（=姚振东？）、`甄阳刘`（=刘甄阳？）、
> `振中邢`（=邢振中？）、`梓恒陈`（=陈梓恒？）；但另一些文件是正常序（`王瑞鑫`、`蔡宇飞`）。
> - 这是记分卡的录入习惯，还是数据源本身的问题？
> - 反序的**判断依据**是什么（固定规则？还是逐个确认）？
> - 2023 版式的对手没有背号，跨年怎么认同一个人？

**B2 · 学号与账号**
> - 学号格式（几位数？带前缀吗？）
> - 全队唯一吗？
> - 登录用户名就用学号吗？还是另设？
> - 初始密码谁发？队员能自己改吗？
> - 教练有几个？谁是 admin？

**B3 · 赛季怎么切**
> - "4 月春季 + 10/11 月秋季"的学期制成立吗？
> - 2026 年的比赛在 **5–6 月**（历史是 4 月 + 10/11 月）—— 这算春季赛吗？
> - 跨年的同一届队员，数据算同一赛季吗？

### 15.2 非阻塞但最好确认

| # | 问题 | 影响 |
|---|---|---|
| 1 | 证件照从哪来（现场拍 / 学籍系统导出）？尺寸格式有要求吗？ | R6-2 上传校验规则 |
| 2 | 队服号码会重号吗？（归档队员的号码要不要保留） | R6-6 |
| 3 | 对手画像报告要不要区分"正赛"和"交流赛"？ | R6-5c |
| 4 | 球员卡导出给谁看（教练内部 / 发赞助商 / 队员发朋友圈）？要不要去掉联系方式？ | R6-4 |
| 5 | 教练要不要能看队员的联系方式？ | R6-2 权限矩阵 |

---

## 16 · 附录 · 现有可复用资产清单

> 做新功能前先看这张表 —— 很多轮子已经造好了。

### 16.1 后端

| 资产 | 位置 | 用途 |
|---|---|---|
| `metrics.py` | 全项目 | **唯一**的指标公式源（AVG/OBP/SLG/OPS/ISO/BABIP/ERA/WHIP/K%…） |
| `innings_to_true()` / `format_innings()` | `metrics.py` | 中文记法局数 ↔ 真实局数 |
| `rebuild_player_stats()` | `database.py` | 档案重算的**唯一**入口 |
| `_safe_data_path()` | `app.py` | 路径穿越防护 |
| `PLAYER_METADATA_FIELDS` / `PLAYER_STATS_FIELDS` | `app.py` | PUT 的字段边界 |
| `_normalize_player_payload()` / `_apply_player_profile()` | `app.py` | 球员元数据归一与落库 |
| `api.js` / `toast.js` | `static/js/` | 前端 API 层 / 提示组件 |
| `_build_matchup_payload()` 等 | `app.py` | 对局查询的序列化（含全部指标） |
| `import_pdfs.py` 的事务/幂等/别名 | `import_pdfs.py` | 导入语义（对手落库照抄） |
| `scripts/validate_pdf_parse.py` 的 `our_totals()` | 该脚本 | 复制一份就是对手侧金标准 |
| `scripts/migrate_r5_metrics.py` / `migrate_r6_2026.py` | `scripts/` | 「副本 → 报告 → `--apply`」的迁移骨架 |
| `scripts/rebuild_stats.py` | `scripts/` | 显式全量重建档案 |
| `scripts/backup_db.py` | `scripts/` | 一致性快照 + SHA256 + 保留份数 |
| `scripts/verify_e2e.py` | `scripts/` | 端到端 30 项（打在副本上） |

### 16.2 前端

| 资产 | 位置 | 用途 |
|---|---|---|
| `base.html` | `templates/` | 4 个 block + csrf meta + api.js + toast.js（**新页面继承它**） |
| `_navbar.html` | `templates/` | 导航正本（**桌面端 + 移动端两处都要改**） |
| `arena.css` 组件类 | `static/css/arena.css` | `mecha-card` / `stat-card` / `energy-line` / `scan-line` / `badge` / `btn-primary` / `jersey-number` |
| `prefers-reduced-motion` 降级 | `arena.css` 底部 | 动画必须支持 |
| `tailwind.config.js` | `static/js/` | `arena.*` 配色（必须在 Tailwind CDN **之前**加载） |
| `escapeHtml()` | `templates/players.html` | 渲染用户数据前必须转义 |
| `getAvgBadgeClass()` / `getOpsBadgeClass()` | `static/js/script.js` | 指标着色规则 |

### 16.3 测试写法模板

```python
# 页面契约（抄 tests/test_batch_entry_ui.py）
def test_page_renders(auth_client):
    resp = auth_client.get('/players/1')
    assert resp.status_code == 200, resp.status_code
    html = resp.data.decode('utf-8')
    assert 'id="playerName"' in html
    assert 'name="csrf-token"' in html
```

```javascript
// JS 单测（抄 tests/js/batch_entry.test.js）
const test = require('node:test');
const assert = require('node:assert');
const mod = require('../../static/js/player_detail.js');
test('非管理员拿不到私有字段', () => {
    assert.strictEqual(mod.privateFieldsFor('coach'), null);
});
```

> **DOM id 交叉检查**：JS 里 `$('xxx')` 引用的每个 id 都必须存在于模板里。
> `tests/js/batch_entry.test.js` 里有现成的检查代码，抄过来改成你的 id 清单 ——
> 一个 id 拼错，页面会**静默**失去某个功能，没有任何报错。

---

## 文档维护

- 本文档随实现进度更新：每完成一个阶段，在第 12 章的任务卡上打勾并写上实际工时
- 实现过程中的**口径变更**要回写到对应章节（例如 B3 确定了，R6-4 的"赛季"那行就要改）
- 每个阶段结束时出一份 Phase Report（规范 §64 的 16 段格式，样板见 `docs/PHASE_R5_REPORT.md`）
- 接口有变动 → 同步 `API_CONTRACT.md`（§2 端点表、§3 示例、§7 变更日志）与 `API_DOCUMENTATION.md`
