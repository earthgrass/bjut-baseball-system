# 交接说明 — 2026-10-29 存档点

> 这是**明天的起点**。从这里接着做即可，不必从头回溯。
> 上一版存档点：2026-10-28（phase-R1 完成时）。

---

## 一、当前状态：可运行

```bash
pip install -r requirements.txt
cp .env.example .env          # SECRET_KEY 已填好；SECRET_KEY 是本机自签名的，泄露无所谓
python run_local.py           # → http://127.0.0.1:5000
```

管理员：`admin` / `admin123`（本机开发用；公网前必须改）

**验证状态（2026-10-29 实测）**：
- **96 个 pytest 全绿**（74 原有 + 22 新增）
- **25 个 node 单测全绿**（`node --test tests/js/batch_entry.test.js`）
- 12 个页面 + 32 个 API 端点
- 端到端 53 项检查全通过（在**生产库副本**上跑，见 `docs/PHASE_R2_REPORT.md` §7）
- 不变量 `profile == SUM(game_records)` 成立（27 名球员 × 6 组字段，漂移 0）
- 生产库 SHA256 全程未变：`eb63d4a3a09c46dd4b1bfc07c6c685f2d271f10b2ed06fdac8edabab6da15d7e`

---

## 二、这一轮（phase-R2）做完了什么

### 修复：最后一个绕过 GameRecord 的统计写入口

`PUT /api/players/<id>` 以前能直接覆盖 profile 累计字段 —— `Player.at_bats_total` 等是
`database.py:_build_profile_proxy` 生成的 property proxy，`setattr` 是**真实写库**。
现已收窄为 **metadata-only**：

| 允许 | 拒绝（400） |
|---|---|
| `name` `jersey_number` `is_pitcher` `player_type` `positions` `primary_position` | 任何统计字段（打数、安打、局数、ERA、OPS……） |

- 拒绝而不是静默忽略 —— 避免「接口返回成功但数据没进去」。
- 拒绝字段集合从 proxy 清单**推导**，不手写名单 —— 以后给档案表加字段，接口自动收紧。
- 顺带删掉 `static/js/script.js` 里 530 行会发统计字段的死代码。

### 修复：三振字段重复键（真实数据丢失）

`GET /api/game_records/<id>` 的响应 dict 里 `'strikeouts'` 写了两次，
Python 后者覆盖前者 → **打击记录的三振恒返回 0**。
对局页用这个端点回填编辑表单再 PUT 回去 → **打击三振被抹成 0**，生涯三振跟着掉。
已按记录类型返回对应列，并加了一道 AST 静态检查防同类 bug 再犯。

### 新增：批量录入界面（`/batch_entry`）

粘贴 box score，一次写完整场比赛：

```
打击：姓名 AB R H RBI BB SO   [2B] [3B] [HR] [HBP] [SB] [CS] [SF] [SH]
投球：姓名 IP H R ER BB SO   [HR] [P] [ST] [BF] [WP]
```

粘贴即实时解析成两张预览表，逐行标 ✓ / 错误原因；
姓名对不上、非投手录投球、`H > AB`、`H < 2B+3B+HR` 都会标红并阻止提交
（**不静默跳过** —— 跳过等于丢数据）。确认无误后整场提交，走既有的
`POST /api/game_records/batch`（全有或全无），**后端语义没变**。

局数按 box score 上的字面数字入库（中文记法 `.1` = 1/3 局），与既有 230 条记录同口径 ——
不在 UI 层换算，避免同一列出现两套单位。

---

## 三、明天接着做（按建议顺序）

### 中等工程量（1-2 天）

1. **PDF 导入改成走 rebuild**（**最高优先级的技术债**）——
   `import_pdfs.py:157-171, 216-234` 仍用 `+=` 增量写 profile，与「档案从
   `game_records` 重算」的核心不变量直接冲突。现在被启动时的
   `sync_stats_from_game_records()` 全量重算掩盖着，但**重导 PDF 会产生漂移**。
   改法：写完 `GameRecord` 后调 `rebuild_player_stats(player.id)`，删掉全部 `+=`。
2. **PDF 解析器改用列坐标**（`FEATURE_PROPOSALS.md` F7a）——
   **性价比最高的一项**，能一次性修掉 8 个静默数据错误，
   并且**重导 17 份 PDF 就能修正全部 230 条历史数据**
   （局数少算 5.6%、三垒打全丢、HBP 幻影、投球数丢失、胜负记错）。
   建议与第 1 项一起做。
3. **指标引擎**（F3）—— 把散在 5 处的公式收成一处，顺带修 WHIP 分母、
   OBP 漏 SH。依赖第 2 项（BF 数据要靠列坐标才有）。
4. **路径泄漏修掉**（两处小改动）：
   - `pdf_parser.py:118` 把异常原文包进返回值，被**匿名可达**的
     `/api/pdf/parse/<path>` 透传 → 泄漏服务器绝对路径
   - `app.py:1903` `confirm_import` 直接回显 `str(e)` → 同上
5. **`confirm_import` 补 `_safe_data_path()` 校验**（`app.py:1911-1916`）——
   其它 PDF 路由都做了，唯独这里没做。

### 立刻能做的（1-2 小时）

6. **在浏览器里真人点一遍 `/batch_entry`** —— 本轮**唯一未验证项**。
   本机没有浏览器自动化（playwright / selenium / puppeteer 都不可用），
   已用三道替代验证覆盖（JS 解析器 25 个单测、JS↔模板 DOM id 契约静态检查、
   HTTP 层端到端 53 项），但**页面在真实浏览器里的渲染与交互没人工确认过**。
7. **`PUT /api/players` 的 400 响应在前端的提示** —— `templates/players.html`
   目前只发 metadata，碰不到 400；但如果以后有别的入口提交了统计字段，
   最好在前端统一处理这个错误（提示"请改用比赛记录录入"）。
8. **DataTables 加到 players / matchup 页面** —— 现在只有 game_stats 有分页。

### 需要先跟你确认的（业务歧义，脚本不能自动判）

9. **player 28 在 2024-11-16 对北京交通大学的 2 条重复** —— 重复导入（删一条）
   还是双赛日（归入两场 Game）？取证报告标为 AMBIGUOUS
10. **赛季怎么切** —— 4 月春季 + 10/11 月秋季的学期制是否成立？
    （`欧阳` vs `欧阳翦` 已确认：库里只有 `欧阳翦` 一个球员，不构成歧义）

---

## 四、必须知道的坑（别踩）

### Flask-SQLAlchemy 的 engine 绑定时机

`init_app()` 里就 eager 创建 engine，**之后**再改
`app.config['SQLALCHEMY_DATABASE_URI']` **不生效**（官方文档原话：
"Changes to application config after this call will not be reflected"）。

早期版本的 `tests/conftest.py` 正是在 `import app` **之后**才覆盖 URI，
导致 `db.drop_all()` 打中真实生产库 → 2026-04 数据事故。

**现在**：用 `DATABASE_FILE` 环境变量，在 `import app` **之前**指定路径。
注意 **`DATABASE_FILE` 的相对路径是相对 `instance/` 解析的**
（`DATABASE_FILE=_scratch.db` → `instance/_scratch.db`；
写 `instance/_scratch.db` 会变成 `instance/instance/_scratch.db` → 报
`unable to open database file`）。
改 `tests/conftest.py` 之前请先读 `docs/PHASE_R0_REPORT.md`。

### 测试测不出 CSRF 问题

`config.py` 的 `TestingConfig` 有 `WTF_CSRF_ENABLED = False`。
写新接口请**在浏览器里实际点一次**，别只看测试。

### 端到端验证要打在副本上

用 `cp instance/baseball_players.db instance/_scratch.db` 建副本，
`DATABASE_FILE=_scratch.db python run_local.py` 起服务，测完删掉。
**永远不要对着生产库跑写操作**（`instance/_verify_writes.py`、
`instance/_verify_e2e.py` 就是反面例子 —— 它们硬编码 `admin/admin123`
打实盘并写库，已列入 backlog）。

### PDF 解析"零失败"是最危险的

17/17 解析成功、0 异常，但数据静默错误。**解析成功 ≠ 数据正确。**

### 公式有 5 份拷贝

`database.py:334-418`（权威）· `import_pdfs.py` · `app.py` ·
`static/js/script.js`（前端预览）· `migrate_profiles_sqlite.py`。
**改一个指标要同步改 5 处**（含前端那份）。

### `recovery/` 是只读取证快照

绝对不要改动或删除。`git_bb429ba_db.bin` 是 R0 恢复源。

---

## 五、文档地图

| 文档 | 内容 |
|---|---|
| `README.md` | 项目总览、快速开始、功能、已知问题 |
| `API_CONTRACT.md` | **接手必读** —— 接口契约、认证/CSRF、已知问题、开发约定 |
| `API_DOCUMENTATION.md` | curl 调用示例 |
| `FEATURE_PROPOSALS.md` | 10 个新功能提案 + 四维评估 + PDF 根因分析 |
| `docs/PHASE_R2_REPORT.md` | **最新阶段报告**（本轮：收窄 PUT + 批量录入 + 三振 bug 修复） |
| `docs/PHASE_R0_REPORT.md` | 数据事故时间线与取证（改 conftest 前必读） |
| `docs/DB_INVENTORY.md` | 16 个数据库文件盘点 |
| `docs/STATS_WRITE_PATH_REPORT.md` | Phase E0 的统计写入口盘点（**行号已过时**，语义以 R2 报告为准） |
| `docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` | 作者的 Phase C 蓝图（Game 实体 / Service 层） |

---

## 六、Git 状态

本轮三个 commit（可单独 revert）：

```text
6554c1f fix: 收窄 PUT /api/players 为 metadata-only
07831a0 fix: 修复「三振」字段重复键导致的数据丢失
b2ccc3c feat: 新增批量录入界面 —— 粘贴 box score 一次写入整场比赛
```

分支：`feature/2026-10-28-runtime-restore`（尚未合并到 `main`）。
接手的人从 `main` 切分支：

```bash
git checkout main && git pull
git checkout -b feature/xxx
```
