# PHASE R2 REPORT — 收窄球员写接口 + 新增批量录入界面

> 执行日期：2026-10-29
> 分支：`feature/2026-10-28-runtime-restore`
> 起始 commit：`0c6d116`（phase-R1）
> 结束 commit：`b2ccc3c`

---

## 1. Objective

Phase R1 把系统从"只能读不能写"修成了可写，并把写入语义统一成
**只写 `game_records`，档案一律从 `game_records` 重算**。本轮做两件事：

1. **R2-A（修复）** 堵上最后一个绕过 `GameRecord` 的统计写入口 ——
   `PUT /api/players/<id>` 仍能直接覆盖 profile 累计字段。
2. **R2-B（写入能力）** Phase R1 已有 `POST /api/game_records/batch`
   （整场一次写入，全有或全无），但**没有任何前端入口** ——
   录一场比赛得点 11 次。本轮给它一个能用的界面。

---

## 2. Repository state before work

| 项目 | 值 |
|---|---|
| 分支 | `feature/2026-10-28-runtime-restore` |
| HEAD | `0c6d116` phase-R1: runtime restore — writable system, CSRF, legacy columns, docs |
| 工作区 | 干净（`git diff` / `git diff --stat` 均无输出） |
| 生产库 | `instance/baseball_players.db`，SHA256 `eb63d4a3a09c46dd4b1bfc07c6c685f2d271f10b2ed06fdac8edabab6da15d7e` |
| 表计数 | players 27 / positions 9 / player_positions 28 / game_records 230 / fielder_profiles 27 / pitcher_profiles 27 / users 1 |
| 测试 | `pytest -q` → 74 passed（先跑 canary：3 passed） |
| SHA256 守卫 | canary 前后、全量 pytest 前后，生产库 SHA **完全一致** |
| 数据漂移 | 27 名球员 `profile` vs `SUM(game_records)` 逐项比对 → **0 漂移** |
| 姓名唯一性 | 27 个姓名互不重复（`欧阳翦` 存在，`欧阳` 不存在）→ 姓名映射无歧义 |

---

## 3. Files inspected

| 文件 | 关注点 |
|---|---|
| `app.py` | 全部写路由、`_apply_game_record_payload`、`_normalize_player_payload`、`_safe_error`、`admin_required` |
| `database.py` | `Player` / `FielderProfile` / `PitcherProfile` / `GameRecord` 模型、`_build_profile_proxy`、`rebuild_player_stats`、`_accumulate_record`、`_apply_agg_to_player` |
| `import_pdfs.py`、`sync_data.py`、`cleanup_db.py`、`migrate_profiles_sqlite.py`、`scripts/*.py` | 其它统计写入口 |
| `tests/conftest.py` | `DATABASE_FILE` 隔离点、session 级 SHA256 守卫 |
| `templates/players.html`、`templates/add_player.html`、`templates/add_game_record.html`、`templates/_navbar.html`、`templates/base.html` | 球员编辑的实际调用方、页面结构约定 |
| `static/js/script.js`、`static/js/api.js`、`static/js/toast.js`、`static/js/matchup_stats.js`、`static/js/game_record.js` | 前端写入口与 CSRF 注入 |
| `docs/STATS_WRITE_PATH_REPORT.md`、`docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` | 设计文档里"禁止路径"的原始定义 |

---

## 4. Findings

### P1 — 本轮修复

| # | 位置 | 问题 | 证据 | 影响 |
|---|---|---|---|---|
| 1 | `app.py:update_player`（原 411-463） | `PUT /api/players/<id>` 直接 `setattr` 28 个统计字段。经 `database.py:_build_profile_proxy` 的 property proxy **真实写库**到 `fielder_profiles`/`pitcher_profiles` | `Player` 映射列只有 8 个，`at_bats_total` 是运行时生成的 property → setter 直通 profile | 绕过 `GameRecord` 唯一真源；档案与原始记录对不上；违反 `DOMAIN_AND_ARCHITECTURE_DESIGN.md:150` 与规范 §41/§76 |
| 2 | `app.py:get_game_record`（原 906 & 922） | 响应 dict 里键 `'strikeouts'` **出现两次**，Python 后者覆盖前者 → 打击记录的三振恒返回投球列的 0 | AST 扫描 + 端到端实测 `GET /api/game_records/233` 返回 `strikeouts: 0`，而库里是 `1` | `matchup_stats.js` 用该端点回填编辑表单再 PUT 回去 → **打击三振被抹成 0**，生涯三振跟着掉 |

### P2 — 本轮未修（已记录进 backlog）

| # | 位置 | 问题 |
|---|---|---|
| 3 | `import_pdfs.py:157-171, 216-234` | PDF 导入走 `+=` 增量写 profile，与 `rebuild_player_stats()` 语义冲突。当前被"每次启动 `sync_stats_from_game_records()`"掩盖（现库 0 漂移），但重导 PDF 会漂移 |
| 4 | `app.py:1903` | `POST /api/pdf/confirm_import` 直接回显 `str(e)`，泄漏服务器绝对路径 |
| 5 | `pdf_parser.py:118` → `app.py:1751` | `parse_pdf` 把异常原文包进返回值，被**匿名可达**的 `/api/pdf/parse/<path>` 透传 → 路径泄漏 |
| 6 | `app.py:1911-1916` | `confirm_import` 未走 `_safe_data_path()`，接受任意绝对路径（其它 PDF 路由都做了） |
| 7 | `cleanup_db.py:157-188` | 合并重复球员时改挂 game_records，但只调 `update_calculated_fields()`，**不重算累计** → 合并后统计错误 |
| 8 | `import_pdfs.py:87-100` | 新建野手时写投手字段 → 经 proxy 凭空造出 `pitcher_profiles` 行 |
| 9 | `database.py:329-330, 469-470` | `errors_fielding` / `passed_balls` 无任何 `GameRecord` 写入源（孤儿字段），rebuild 既不清也不更新 |
| 10 | `database.py:406-409` | 局数单位口径：`.1` = 1/3 局 与 `ERA = ER*9/IP` 不自洽 |
| 11 | `instance/_verify_writes.py`、`instance/_verify_e2e.py` | 用硬编码 `admin/admin123` 打实盘 127.0.0.1:5000 并写库，不走 scratch 库 |

### P3

| # | 位置 | 问题 |
|---|---|---|
| 12 | `app.py:168` 等 | `Query.get()` 已弃用（SQLAlchemy 2.x），刷 deprecation 警告 |
| 13 | `static/js/script.js` | `displayPlayers` / `addCalculationListeners` / `calculateBattingStats` / `calculatePitchingStats` 随本轮删除的编辑弹窗一起变成死代码 |

### 需业务方拍板（本轮不涉及）

- player 28 在 2024-11-16 对北京交通大学的 2 条重复：重复导入还是双赛日？
- 赛季怎么切（4 月春季 + 10/11 月秋季的学期制是否成立）？

---

## 5. Changes

### `6554c1f` fix: 收窄 PUT /api/players 为 metadata-only

| 文件 | 改动 | 原因 |
|---|---|---|
| `app.py` | 导入 `FIELDER_PROFILE_DEFAULTS` / `PITCHER_PROFILE_DEFAULTS`，定义 `PLAYER_STATS_FIELDS`（36 个）与 `PLAYER_METADATA_FIELDS`（6 个） | 拒绝集合从 proxy 清单**推导**，不手写名单 —— 以后给档案表加字段，接口自动跟着收紧 |
| `app.py` | `update_player()` 开头拦截统计字段 → 400 + `rejected_fields` | 选"拒绝"而非"静默忽略"：静默忽略会出现"提示成功但数据没进去" |
| `app.py` | 删除 16 个打击字段 + 12 个投手字段的覆盖循环 | 堵上最后一个绕过 `GameRecord` 的统计写入口 |
| `app.py` | 删除死代码 `update_player_stats()` | 全仓库无调用点的第二份覆盖实现，是活地雷 |
| `app.py` | 响应附带 `ignored_fields` | 让客户端能自查字段名拼写（例：误传 `at_bats`） |
| `static/js/script.js` | 删除 `editPlayer()` / `savePlayerChanges()`（530 行） | 它们向该接口提交 28 个统计字段。已确认不可达：弹窗依赖已移除的 Bootstrap（`editPlayer` 自己会报警并 return），且 `add_player.html` 没有 `playersTableBody` 表格 |
| `static/js/script.js` | 删除 `displayPlayers()` 里指向 `editPlayer` 的按钮 | 避免留下悬空函数引用 |
| `tests/test_players_baseline.py` | `test_update_player_with_stats` 由"锁允许覆盖"改为"锁 400 拒绝"，docstring 记录变更历史 | 规范 §45：行为变更必须专门记录，不能顺手改 |
| `tests/test_player_metadata_boundary.py` | 新增 10 个用例 | 锁新契约 |

### `07831a0` fix: 修复「三振」字段重复键导致的数据丢失

| 文件 | 改动 | 原因 |
|---|---|---|
| `app.py` | `get_game_record()` 的 `'strikeouts'` 按 `is_pitching_record` 取 `strikeouts_pitched` 或 `strikeouts`；投球段落不再重复该键 | 与 `PUT /api/game_records/<id>` 已有契约一致 —— 两边共用同一个 JSON 键，由 `is_pitching` 决定写哪一列 |
| `tests/test_game_record_read_back.py` | 新增 5 个用例 | 锁"读回来"的契约 + 全项目重复键静态检查 |

### `b2ccc3c` feat: 新增批量录入界面

| 文件 | 改动 | 原因 |
|---|---|---|
| `app.py` | 新增路由 `batch_entry_page()`（`@admin_required`） | 页面入口 |
| `templates/batch_entry.html` | 新建，继承 `base.html` | `base.html` 已含 CSRF meta / `_navbar.html` / `api.js` / `toast.js`；表单类沿用其它页面的写法在页内定义，不动其它模板 |
| `static/js/batch_entry.js` | 新建（532 行） | 解析 / 预览 / 提交；复用 `api.js` 的 `api.post`（自动带 CSRF）与 `toast.js` 的 `toast()` |
| `templates/_navbar.html` | 管理员区加「批量录入」入口 | 桌面按钮 + 移动端菜单两处 |
| `tests/js/batch_entry.test.js` | 新增（node `--test`，25 个用例） | 规范 §47 Level 1：parser 必须有单元测试 |
| `tests/test_batch_entry_ui.py` | 新增 7 个用例 | 页面权限 / 结构 / 导航 / 批量写入后不变量 / 后端独立校验 / 触发 JS 单测 |

---

## 6. Tests added

### `tests/test_player_metadata_boundary.py`（10 个）

metadata 可改、统计字段被拒（打击 / 投手 / 派生率 / 多个同时）、
被拒后档案与 `game_records` 依然一致、认证要求、`ignored_fields` 回报、请求体非对象。

### `tests/test_game_record_read_back.py`（5 个）

打击记录 GET 回打击三振、投球记录 GET 回投球三振、
GET→PUT 往返后三振不丢（打击 + 投球各一）、
**全项目 dict 字面量无重复键**（AST 扫 `app.py`/`database.py`/`import_pdfs.py`/`sync_data.py`）。

### `tests/js/batch_entry.test.js`（25 个，node `--test`）

正常行 / 多行 / 小数局数 / 可选列；表头·注释·空行·合计行跳过；
未知姓名 / 重名 / 场员录投球；`H>AB`、`H<2B+3B+HR`、负数、非数字、列数过多过少；
错误行不阻断其它行、错误行带行号；
**JS ↔ 模板的 DOM id 契约交叉检查**（集合相等 + 无孤儿 id）。

### `tests/test_batch_entry_ui.py`（7 个）

匿名 302 / 非管理员 302 / 管理员 200 且 12 个 DOM id 与 CSRF meta 齐全 /
导航入口存在 / 批量写入后打击与投球档案都等于记录之和 /
后端独立拒绝「场员录投球」/ 有 node 时跑 JS 单测。

---

## 7. Commands actually executed

```bash
# 基线
git status --short && git branch --show-current && git log --oneline -15 && git diff --stat
python -c "import hashlib;print(hashlib.sha256(open('instance/baseball_players.db','rb').read()).hexdigest())"
python -m pytest tests/test_canary_r0.py -q          # 3 passed
python -m pytest -q                                   # 74 passed

# 漂移审计（只读，sqlite mode=ro）
# → 27 名球员，drifted: 0

# 每轮改动后
python -m pytest tests/test_player_metadata_boundary.py -q     # 10 passed
python -m pytest -q                                           # 84 / 91 / 96 passed
node --test tests/js/batch_entry.test.js                      # 25 passed

# 端到端（生产库副本）
cp instance/baseball_players.db instance/_scratch_r2.db
DATABASE_FILE=_scratch_r2.db FLASK_ENV=production PORT=5099 python run_local.py
python <e2e script>                                            # 53 项检查全通过
rm -f instance/_scratch_r2.db

# 收尾
git diff --stat && git diff && git status --short
```

---

## 8. Test result

```text
PASS
```

| 套件 | 结果 |
|---|---|
| `pytest -q`（最终） | **96 passed**（原 74 + 新增 22） |
| `node --test tests/js/batch_entry.test.js` | **25 passed** |
| 端到端（生产库副本） | **53/53 检查通过** |
| 副本库不变量复检 | 27 名球员 × 6 组字段 → **漂移 0** |

---

## 9. Production DB safety proof

| 时点 | SHA256 |
|---|---|
| 基线 | `eb63d4a3a09c46dd4b1bfc07c6c685f2d271f10b2ed06fdac8edabab6da15d7e` |
| canary 后 | 同上 |
| 全量 pytest 后（R2-A） | 同上 |
| 全量 pytest 后（R2-B） | 同上 |
| 全量 pytest 后（三振修复） | 同上 |
| 端到端验证后（副本已删） | 同上 |

**全程生产库只读。** 所有写操作都发生在 `instance/_scratch_r2.db`（生产库副本）上，
验证完即删除。`tests/conftest.py` 的 session 级 SHA256 守卫未改动。

---

## 10. Database impact

- **schema 变更：无**
- **migration：无**
- **数据迁移：无**
- **生产库写入：0 次**

新增的写路径（批量录入）只写 `game_records`，档案由既有
`rebuild_player_stats()` / `rebuild_players_stats()` 重算。

---

## 11. Security impact

| 项 | 变化 |
|---|---|
| 认证 | 无变化（`/batch_entry` 走既有 `@admin_required`；匿名 302 已验证） |
| CSRF | 无变化（`api.js` 的 `fetchJson` 自动带 `X-CSRFToken`；页面含 CSRF meta，已验证） |
| 授权 | 新增页面与既有写端点同为 admin 级 |
| 数据暴露 | 无新增公开端点；`/batch_entry` 不泄露数据 |
| 静默失败面 | **减少**：原先 PUT 静默丢弃/覆盖统计，现在 400 明确报错 |
| 路径穿越 | 本轮未触及（`confirm_import` 的路径校验问题仍在 backlog） |

---

## 12. Backward compatibility

| 变化 | 兼容性 |
|---|---|
| `PUT /api/players/<id>` 拒绝统计字段 | **破坏性**。唯一调用方 `templates/players.html` 只发 metadata → 不受影响。外部调用方会收到 400 + `rejected_fields`，可据此改用比赛记录接口 |
| `GET /api/game_records/<id>` 的 `strikeouts` | **修复**。打击记录此前恒返回 0，现在返回真实值。依赖旧（错误）行为的客户端会看到不同结果 —— 这是修正而非回归 |
| 新增 `GET /batch_entry` | 纯新增，不影响既有端点 |
| 后端批量端点语义 | **未变**。批量录入页面只是它的一个前端 |

---

## 13. Known issues

本轮**未修**（完整清单见第 4 节 P2/P3）。最需要优先处理的三条：

1. **PDF 导入仍走 `+=` 增量**（#3）—— 现在被启动时的全量重算掩盖，但重导 PDF 会产生漂移，
   且与"档案从 `game_records` 重算"的核心不变量直接冲突。建议与"PDF 解析器改用列坐标"一起做。
2. **路径泄漏**（#4、#5）—— `/api/pdf/parse/<path>` 匿名可达，异常原文里含服务器绝对路径。
   两处都是小改动。
3. **`cleanup_db.py` 合并球员后不重算累计**（#7）—— 一旦有人跑这个脚本，统计会错且不自愈。

另需业务方拍板：player 28 的 2 条重复（重复导入 vs 双赛日）、赛季怎么切。

---

## 14. Git diff summary

```text
6554c1f fix: 收窄 PUT /api/players 为 metadata-only
 app.py                                 | 141 +++------
 static/js/script.js                    | 540 +--------------------------------
 tests/test_player_metadata_boundary.py | 259 ++++++++++++++++
 tests/test_players_baseline.py         |  29 +-
 4 files changed, 336 insertions(+), 633 deletions(-)

07831a0 fix: 修复「三振」字段重复键导致的数据丢失
 app.py                              |   8 +-
 tests/test_game_record_read_back.py | 187 ++++++++++++++++++++++++++++++++++++
 2 files changed, 193 insertions(+), 2 deletions(-)

b2ccc3c feat: 新增批量录入界面 —— 粘贴 box score 一次写入整场比赛
 app.py                       |  11 +
 static/js/batch_entry.js     | 532 +++++++++++++++++++++++++++++++++++++++++++++++++++
 templates/_navbar.html       |   2 +
 templates/batch_entry.html   | 238 ++++++++++++++++++
 tests/js/batch_entry.test.js | 262 +++++++++++++++++++++
 tests/test_batch_entry_ui.py | 158 +++++++++++++
 6 files changed, 1203 insertions(+)
```

三个 commit 各自独立，可单独 `git revert`（规范 §50：一个 commit 一个目标）。

---

## 15. Commit hash

| commit | 说明 |
|---|---|
| `6554c1f` | fix: 收窄 PUT /api/players 为 metadata-only |
| `07831a0` | fix: 修复「三振」字段重复键导致的数据丢失 |
| `b2ccc3c` | feat: 新增批量录入界面 —— 粘贴 box score 一次写入整场比赛 |
| （docs） | docs: 更新 API 契约与交接说明 |

---

## 16. Gate

```text
GO
```

判定依据（规范 §63）：

- [x] canary 通过 → 全量 pytest 通过（96 passed）
- [x] 生产库 SHA256 前后一致
- [x] `profile == SUM(game_records)` 不变量复检通过（副本库漂移 0）
- [x] 端到端 53 项检查全通过（生产库副本上）
- [x] `git diff` 无意外删除 / 无生成物 / 无 secret
- [x] API_CONTRACT.md 与实现一致

**唯一未验证项**：浏览器里真人点一遍批量录入页面。
本机无浏览器自动化（playwright / selenium / puppeteer 均不可用），
所以用三道替代验证覆盖：
JS 解析器 25 个单元测试、JS ↔ 模板的 DOM id 契约静态交叉检查、
以及 HTTP 层的端到端 53 项检查（含页面 DOM id 全部存在、CSRF meta 存在、匿名 302）。
**页面在真实浏览器里的渲染与交互未经人工确认 —— 标注为 UNVERIFIED。**
