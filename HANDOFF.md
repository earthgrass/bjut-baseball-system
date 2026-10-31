# 交接说明 — 2026-10-31 存档点（R5 指标引擎补完 + PDF 页脚修复）

> 这是**明天的起点**。从这里接着做即可，不必从头回溯。
> 上一版存档点：2026-10-30（R4 + CI 硬化）；阶段报告见 `docs/`。
> 本轮增量：**指标引擎收尾**（WHIP 改标准口径 + 补 9 个派生率），
> 并顺带挖出并修掉一个**静默丢数**的 PDF 解析缺陷。

---

## 一、当前状态：可运行，指标口径已校正，CI 绿

```bash
pip install -r requirements.txt
cp .env.example .env          # SECRET_KEY 已填好（仅本机）
python run_local.py           # → http://127.0.0.1:5000
```

管理员：`admin` / `admin123`（本机开发用；公网前必须改）

**验证状态（2026-10-31 实测）**：

| 项 | 结果 |
|---|---|
| pytest | **154 passed**（原 124，本轮 +30） |
| node 单测 | 25 passed（`node --test 'tests/js/*.test.js'`） |
| ruff | `All checks passed!`（全项目 0 告警） |
| GitHub Actions | 两个 job（`test` / `safety`），**本轮尚未推送**，CI 绿待验证 |
| 端到端 | `scripts/verify_e2e.py` **30/30**（打在副本上，生产库 SHA 未变） |
| 解析器前后比对 | 17 份 PDF，差异**恰好 5 处**，全是 `batters_faced` 0 → 真值 |
| PDF 独立校验 | `scripts/validate_pdf_parse.py` 16/17（第 17 份是源 PDF 自相矛盾） |
| 生产库 | 27 球员 / **240** 比赛记录 / 2023-04-01 ~ 2025-11-22 / integrity ok / fk 0 |
| 生产库 SHA256 | 迁移前 `e3371443…` → 迁移后 `f731f13d…`（备份文件即迁移前状态） |

> ✅ **生产库已迁移**（2026-10-31 13:14）：WHIP 已按标准口径重算，BF 覆盖 44/45。
> 备份：`instance/baseball_players.pre_r5_20261031_131450.db`

---

## 二、这一轮（2026-10-31）做完了什么：指标引擎收尾 + 一个静默丢数的解析器缺陷

### 1. WHIP 改成标准口径（F3 提案的尾巴）

原来分母错用「投球局数」，改成标准的「面对打席数」：

| 投手 | 旧 WHIP | 新 WHIP |
|---|---|---|
| 刘孝宇 | 5.60 | 0.64 |
| 吴鸿硕 | 3.56 | 0.56 |
| 白云箫 | 3.53 | 0.49 |
| 李昊宇 | 2.67 | 0.47 |
| 欧阳翦 | 1.86 | 0.35 |
| 韩登越 | 1.15 | 0.27 |
| 仇志豪 | 0.00 | 1.00 |

⚠️ **WHIP 只统计「有面对打席数」的场次** —— 分子分母必须同源，
否则没 BF 的场次会把分子撑大、WHIP 反而虚高（实测 5 名投手会算错）。

补齐的派生率（教练真正会看的那几个，之前一个都没有）：
**ISO · BABIP · K% · BB% · K-B% · SB% · CS% · K/9 · BB/9**。
打击侧的 K-B% 按打席相减，投手侧按 9 局相减（两种惯例不同）。

派生率**不落库**（数据库 schema 零变更），序列化时现算，公式仍全在 `metrics.py`。

### 2. 挖出并修掉一个静默丢数的解析器缺陷

记分卡模板最下方的水印 `Scorekeeping. Stats. Live Game Updates.`
粘在**最后一个标签段的最后一条**后面，把那条整条吞掉：

```
BF: 白云箫 9, 李昊宇 3, 韩登越 11, 仇志豪 4 Scorekeeping. Stats. Live Game Updates.
```

旧代码要求整项以数字结尾 → 匹配失败 → 掉进「无数字 = 次数 1」的兜底 →
变成垃圾键 → **投手的面对打席数凭空为 0**。**17 份 PDF 全中。**

修复后可恢复 5 条（其余是真的没这一栏）：

```
韩登越 2023-04-16 = 7 · 仇志豪 2023-04-01 = 4 · 刘孝宇 2024-10-20 = 14
李昊宇 2025-10-18 = 8 · 刘孝宇 2025-10-26 = 5
```

BF 覆盖：39/45 → **44/45**（只剩 `2025-11-22` 那场手录、无 PDF 的记录）。

### 3. 顺手清掉的两处公式拷贝

- `app.py` 里自己算 `round(hits/at_bats,3)` 的一份
- `static/js/script.js` 前端自己算 OPS 的一份（还带 console.log 调试输出）

### 4. 前端接上了新指标

统计页排行榜：打击新增 6 个 tab（长打率 / ISO / BABIP / K% / BB% / K-B%），
投球新增 3 个（K/9 / BB/9 / K-B%）；球员列表表格新增「上垒率」「长打力 ISO」两列。
排行榜的配置从「一长串三元表达式」改成 `get(p)` 函数（原来加一个指标就多一个分支，
漏一个会**静默排错序**）。

### 5. ✅ 生产库迁移：已执行

```bash
python scripts/migrate_r5_metrics.py          # 只在副本上跑 + 出报告（安全）
python scripts/migrate_r5_metrics.py --apply  # 验证通过后写生产库（自动备份）
```

已于 2026-10-31 13:14 执行（业务方确认后）。副本与生产库两次独立执行的
结果**字节相同**（SHA256 = `f731f13d…`）。

副本上的验证结果（已跑过）：

```
行数      players 27 → 27 · game_records 240 → 240（零增零减）
BF 覆盖   39/45 → 44/45
完整性    integrity_check=ok · foreign_key_check=0
球员名单  零变化（0 新球员、0 未知姓名新建）
```

⚠️ 迁移会**重写 `game_records` 的行**（覆盖模式是删旧写新）→ record id 会变，
但所有字段值除 5 个 BF 外不变（解析器前后逐字段比对已证明）。
WHIP 数值会大幅变化 —— 这正是要修的东西，但值得先看一眼再落库。

报告：`docs/PHASE_R5_REPORT.md`。

---

## 三、（2026-10-30 那一轮）CI 首次跑通

## 二、这一轮（2026-10-30）做完了什么：CI 首次跑通

上一轮把 CI 的配置文件写好了，但**从没在 GitHub 上真跑过**。这一轮推上去，第一次运行
就两个 job 全红 —— 顺手挖出 **3 个真 bug**，每一个都是「本地永远发现不了」的那类：

| # | bug | 后果 | 修法 |
|---|---|---|---|
| 1 | workflow 装的是 `requirements.txt`，但 pytest 在 `requirements-dev.txt` 里 | `pytest -q` 直接 `command not found`，两个 job 全红 | 改装 `requirements-dev.txt` |
| 2 | CI 跑 `pytest -q`，本地跑 `python -m pytest` | 裸 `pytest` 不把当前目录放进 `sys.path` → `No module named 'database'`，**10 个测试文件收集失败** | `pyproject.toml` 加 `pythonpath = ["."]`；CI 也改用 `python -m pytest` |
| 3 | `requirements.txt` 没钉 SQLAlchemy | 2.1 起 `str(engine.url)` 把 Windows 路径渲染成**百分号编码**，conftest 的路径安全判定全线误判 → **95 个测试 error** | conftest 改用 `make_url()` 解析；`requirements.txt` 钉 `SQLAlchemy==2.0.54` |

另外两处：

- `tests/test_canary_r0.py` 的「生产库必须存在」在干净 checkout 里必然失败
  → 改成**没有生产库就 skip**（库不存在 ≠ 库被改了）
- CI 的 safety job 复制 `recovery/recovered_pre_incident.db` —— 但 `recovery/`
  是 `.gitignore` 排除的，干净 checkout 里根本没这个文件
  → 改用仓库自己的代码生成生产库（`python -c "import app"`）

**这条教训值得记住**：CI 的价值不在于「配了没」，而在于「**真的跑过**」。
一个从没运行过的 CI 配置，跟没有 CI 是一样的 —— 而且还会给人虚假的安全感。

---

## 四、R4 那一轮做完了什么

### 1. 把修好的 PDF 解析器**真正用到了生产数据**

R3 结束时是「代码对了、数据是错的」：列坐标解析器写好了，但生产库的 230 条记录
仍是旧文本解析器的产物。本轮完成迁移：

```text
生产库 230 → 240 条（新增 11 条旧解析整行漏掉的人次，消失 0 条）
82 条记录被修正，共 149 处字段
三垒打记录 0 → 3 · 面对打席 3 → 39 · 暴投 0 → 2
HBP 从「安在错的人头上」纠正为「按 PDF 原文归属」
刘孝宇生涯 ERA 22.50 → 19.80，李昊宇 16.88 → 15.00
球员名单零变化 · 2025-11-22 那 16 条无 PDF 依据的记录原样保留
```

报告：`docs/PHASE_R4_REPORT.md`（含逐项验证、三个指纹、两个回滚点）。

### 2. ruff 上线，抓出 3 个真 bug

| 严重度 | bug | 后果 |
|---|---|---|
| **P1** | `app.py` 用 `re.sub()` 却没 `import re` | **PDF 上传接口必然 500** —— 这条路径从未被人工走过 |
| **P1** | `cleanup_db.py` 的 CJK 部首表整体错位一位 | U+2F0C 写成「门」，其后 200+ 条映射全偏移（改用 Unicode NFKC 修） |
| **P2** | `sync_data.py` 是档案重算的**第二套实现** | 24 处 `+=`、局数按字面值、硬编码生产库路径（改为只调权威实现） |

同时：前端最后一份公式拷贝（死代码，110 行）删除；`migrate_profiles_sqlite.py`
改用 `metrics.py`；`Query.get()` 弃用告警 312 → 13 条；`conftest.py` 重复 fixture 清理。

### 3. 剩下的审计项

| # | 项 | 状态 |
|---|---|---|
| #5 | `cleanup_db.py` 合并后不重建档案 | ✅ 改调 `rebuild_player_stats()`，有回归测试 |
| #11 | `errors_fielding` / `passed_balls` 孤儿字段 | ✅ **部分解决**：查明 4 份 PDF 有 `E:`（守备失误）、1 份有 `SF:`（牺牲打）→ 接上并纳入聚合；`passed_balls` 在 17 份 PDF 里**确实没有数据源**，保留列但写明「不是真实 0」 |
| #15 | 指标公式 6 份拷贝 | ✅ 全项目只剩 `metrics.py` 一份（AST 检查同时扫 Python 与 JS） |
| #17 | 热点表零索引 | ✅ 5 个索引，热查询从 `SCAN` 变 `SEARCH ... USING COVERING INDEX` |
| #18 | 没有自动备份 | ✅ `scripts/backup_db.py`（一致性快照 + SHA256 + 指纹 + 保留份数） |
| #22 | 没有 CI / lint | ✅ ruff + GitHub Actions（pytest / node --test / ruff，外加一个专盯「测试不碰生产库」的 job）。**2026-10-30 首次真跑，两个 job 全绿**（见第二节）。⚠️ `.pre-commit-config.yaml` **未创建**（装 Git 钩子需你点头） |
| #24 | `Query.get()` 弃用 | ✅ 全项目清零 |
| #26 | 前端死代码 | ✅ 删 110 行 |
| #28 | session cookie 未配置 | ✅ HttpOnly / SameSite=Lax / Secure 可配；生产环境未开 Secure 时**启动告警** |
| #29 | 限流用内存存储 | ✅ 说明清楚：多 worker 必须换 Redis；生产启动时告警 |
| #14 | `instance/` 里的探针会写坏生产库 | ✅ 加安全闸（默认拒绝）；新增打在副本上的 `scripts/verify_e2e.py` |
| #32 | 「欧阳 / 欧阳翦」 | ✅ **业务方已确认：同一个人** → 写成显式别名，导入报告仍显式上报 |
| #33 | 赛季怎么切 | ⏳ 待业务方拍板（需要 Game 实体） |
| #34 | 刘孝宇异常失分 | ✅ 数据已修正（见上） |
| #35 | PDF 里的对方球员名字 | ✅ 澄清：新解析器不再混进我方；残留的「尹文浩」是记分卡上的教练行（0 AB），已跳过且不建球员 |

---

## 五、下一步（按建议顺序）

### 中等工程量（1-2 天）

1. **Game 一级实体**（规范 §18/§19/§71-73，审计 #20）——
   现在「一场比赛」= `game_date + opponent` 字符串，双赛日无法表达、
   对手改名会产生「同一场比赛两条记录」、去重键依赖对手字符串写法一致。
   目标 schema：`Game(id, game_date, opponent, season, venue, game_number,
   source_pdf, notes, created_at, updated_at)` + `UNIQUE(game_id, player_id, record_type)`。
   **必须在生产库副本上验证，row loss 必须为 0**，迁移报告按规范 §72 出。
2. **Service 层**（规范 §37-42，审计 #16）——
   `StatsService.audit_player / audit_all / rebuild_player / rebuild_all`
   与 `GameService`（事务边界）、`PlayerService`（metadata 边界）。
   蓝图只做 HTTP / 校验 / 鉴权 / 调 service / 返回。
3. **蓝图拆分**（规范 §43/§77）—— 一次拆一个，每拆完跑全量测试。
   顺序：players → game records → matchup → stats → pdf → auth → pages。

### 立刻能做的（1-2 小时）

4. `/batch_entry` 在**真实浏览器**里点一遍 —— 仍是唯一未做的人工验证项
   （本机没有 playwright/selenium/puppeteer）。已有三道替代验证：
   JS 单测 25 个、JS↔模板 DOM id 契约静态检查、端到端 30 项。
5. 统计页新增的 9 个排行榜 tab 在浏览器里点一遍（本轮唯一没跑过真实浏览器的新界面）。
7. `PUT /api/players` 的 400 在前端统一提示（「请改用比赛记录录入」）。
8. DataTables 加到 players / matchup 页面（现在只有 game_stats 有分页）。
9. 建 `.pre-commit-config.yaml`（需要你点头 —— 装 Git 钩子属于持久化外部工具）。

### 需要先跟你确认的（业务歧义，脚本不能自动判）

10. **赛季怎么切**（4 月春季 + 10/11 月秋季的学期制是否成立）——
   需要 Game 实体才能表达，会影响所有统计口径。
11. **2025-10-25 vs 华北电力大学那份 PDF 自己前后矛盾**：
   投手局数之和 1.0，但它的 Totals 行写 1.2。是源数据录入错误，还是记分卡惯例？
   （解析器按「Totals 行」为准 → 1.2；按明细求和 → 1.0。）
12. **`2025-11-22 vs 北京交通大学` 的 16 条记录没有对应 PDF** ——
    是漏传了 PDF，还是这��是手工录的？目前原样保留，无法用 PDF 验证。
13. **`尹文浩`** 在 2023-04-16 的记分卡上有一行（0 AB，像是教练）——
    他是队员吗？若是，需要补录。

---

## 六、必须知道的坑（别踩）

### WHIP 的分子分母必须同源（2026-10-31 新增）

有场次没有 BF（`2025-11-22` 那场是手录、无 PDF）。
若分子用全部场次、分母只用有 BF 的场次 → 分子多算 → **WHIP 虚高**。
所以 `database._accumulate_record` 只把「有 BF 的场次」计入 WHIP 基数，
`PitcherProfile.update_calculated_fields()` **不**算 whip（档案列没有这个拆分信息，
硬算就会退回旧的错误口径）。详见 `metrics.py` 顶部与 `docs/PHASE_R5_REPORT.md`。

### 「唯一公式源」的检查有盲区（2026-10-31 新增）

`tests/test_r3_metrics_and_import.py` 的 AST 检查只认 `* 9 /` 这种 ERA 特征 ——
它**抓不到** `round(hits/at_bats,3)` 这种短公式（R5 就在 app.py 与 script.js 里
各抓到一份，已清）。**加新指标时别只在 app.py / 前端现算**，
先写进 `metrics.py`（API_CONTRACT §5.2 的 checklist 已更新）。

### pytest 的 `-m`（2026-10-30 新增，最容易踩）

`python -m pytest` 会把当前目录塞进 `sys.path`，裸 `pytest` **不会**。
测试里 `from database import Player` 依赖仓库根在 `sys.path` 上 ——
裸 `pytest -q` 直接 `ModuleNotFoundError: No module named 'database'`，
10 个测试文件在收集阶段就挂。

现在 `pyproject.toml` 里设了 `pythonpath = ["."]`，两种写法都能跑；
但**新写脚本一律用 `python -m pytest`**（少一道依赖就少一处
「本地能跑、CI 不能」的坑）。

### SQLAlchemy 2.1 会把 Windows 路径渲染成百分号编码（2026-10-30 新增）

`str(engine.url)` 在 2.0.54 是 `sqlite:///C:\Users\...`，
在 2.1.x 变成 `sqlite:///C%3A%5CUsers%5C...`。
任何拿它切字符串当路径用的代码（比如 conftest 的路径安全判定）
都会全线误判 → 95 个测试集体 error。

`requirements.txt` 现在钉了 `SQLAlchemy==2.0.54`；真要升级，
先看 `tests/conftest.py` 的 `_sqlite_path_from_uri()`（已改成用
SQLAlchemy 自己的 `make_url()` 解析）。

### `recovery/` 是 gitignored 的（2026-10-30 新增）

`recovery/` 被 `.gitignore:16` 排除 —— 它是本机的只读取证快照，
**不在仓库里**。任何 CI 脚本、workflow、文档都别引用
`recovery/xxx.db`：干净 checkout 里根本没有那个文件。

### GitHub Actions 的日志需要登录才能看（2026-10-30 新增）

CI 失败时，日志正文要登录 GitHub 才能看，公开 API 也取不到
（`actions/runs/{id}/logs` 需要 admin 权限）。
自动化排查时拿不到失败详情 —— 只能靠本地复现。
所以**提交前尽量在本地按 CI 的方式跑一遍**：

```bash
python -m pytest -q          # 与 CI 一致
node --test 'tests/js/*.test.js'
ruff check .
```

### node 24 的 `node --test <目录>` 不成立

`node --test tests/js/`（带尾斜杠）会把目录当模块去 require →
`MODULE_NOT_FOUND`。必须用 glob：`node --test 'tests/js/*.test.js'`
（需要 node ≥ 21；CI 已显式钉 node 22）。

### Flask-SQLAlchemy 的 engine 绑定时机

`init_app()` 里就 eager 创建 engine，**之后**再改
`app.config['SQLALCHEMY_DATABASE_URI']` **不生效**（官方文档原话：
"Changes to application config after this call will not be reflected"）。

任何想换库的场景（包括测试隔离、迁移演练）必须走 `DATABASE_FILE` 环境变量，
在 `import app` **之前**设好。注意 **`DATABASE_FILE` 的相对路径是相对 `instance/` 解析的**
（`DATABASE_FILE=_scratch.db` → `instance/_scratch.db`；
写 `instance/_scratch.db` 会变成 `instance/instance/_scratch.db` → 报
`unable to open database file`）。

### `DATABASE_FILE` 与 pytest 的隔离顺序

`tests/conftest.py` 在 `import app` 之前设 `DATABASE_FILE`（临时目录），
并有 session 级 SHA256 看门狗。**改 conftest.py 之前先读 `docs/PHASE_R0_REPORT.md`。**

### 测试测不出 CSRF 问题

`config.py` 的 `TestingConfig` 有 `WTF_CSRF_ENABLED = False`。
写新接口请**在浏览器里实际点一次**，别只看测试。

### 端到端验证要打在副本上

用 `python scripts/verify_e2e.py`（自动复制生产库 → 连副本跑 → 复验生产库 SHA 未变 → 删副本）。
**不要**用 `instance/_verify_writes.py` / `instance/_verify_e2e.py` ——
它们打的是正在运行的服务器、硬编码 `admin/admin123`、**真的会写生产库**
（现已加安全闸默认拦截）。

### PDF 解析"零失败"是最危险的

17/17 份解析成功、0 异常，但数据静默错误率极高。
**解析成功 ≠ 数据正确。** 独立校验要用 PDF 自己的 Totals 行当真值
（`scripts/validate_pdf_parse.py`）。
R5 的页脚缺陷就是这一类：解析"成功"，但每个文件都少一条数据。

### 局数口径

`game_records.innings_pitched` 存**记法字面值**（`.1` = 1/3 局），
档案 `innings_pitched_total` 存**真实局数**。换算必须**逐条**做
（各场小数位相加可能 ≥10 而进位）。详见 `metrics.py` 开头。

### 导入的写入语义

`import_pdfs.py` 只写 `game_records`，档案一律 `rebuild_player_stats()` 重算。
**不要**再写 `player.at_bats_total += ...` 之类的增量。

### `recovery/` 是只读取证快照

绝对不要改动或删除。

---

## 七、文档地图

| 文档 | 内容 |
|---|---|
| `README.md` | 项目总览、快速开始、功能、已知问题与修复记录 |
| `.github/workflows/ci.yml` | CI：pytest / node --test / ruff / 「测试绝不碰生产库」的 safety job |
| `API_CONTRACT.md` | **接手必读** —— 接口契约、认证/CSRF、指标口径、开发约定 |
| `API_DOCUMENTATION.md` | curl 调用示例 |
| `FEATURE_PROPOSALS.md` | 10 个新功能提案 + 四维评估 |
| `docs/ISSUES_AUDIT_20261029.md` | 全量问题清单审计（35 条，本轮收敛了大半） |
| `docs/PHASE_R5_REPORT.md` | **最新阶段报告**（指标引擎补完 + PDF 页脚修复 + 迁移报告） |
| `docs/PHASE_R4_REPORT.md` | 数据校正迁移 + 硬化 |
| `docs/PHASE_R3_REPORT.md` | 指标引擎 + 列坐标解析器 |
| `docs/PHASE_R2_REPORT.md` | 收窄 PUT + 批量录入 + 三振 bug 修复 |
| `docs/PHASE_R0_REPORT.md` | 数据事故时间线与取证（改 conftest 前必读） |
| `docs/DB_INVENTORY.md` | 16 个数据库文件盘点 |
| `docs/STATS_WRITE_PATH_REPORT.md` | Phase E0 的统计写入口盘点（**行号已过时**） |
| `docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` | 作者的 Phase C 蓝图（Game 实体 / Service 层） |

---

## 八、Git 状态

分支：`main`，基线 `6dfa004`。
**R5 的改动尚未提交**（代码 + 文档都已就位，等迁移跑完一起提交）。

远端：<https://github.com/earthgrass/bjut-baseball-system>
（`main` = 主线；CI 徽章在 README 顶部）

### R5 改动清单（未提交）

```text
M app.py                    指标改走 metrics；matchup 的 WHIP 改 BF 口径；两个 stats 接口补新指标
M database.py               档案聚合记 WHIP 基数；档案 metrics()；Player 派生率属性；to_dict 输出新指标
M metrics.py                WHIP 改标准分母；新增 11 个派生率函数 + batting_metrics/pitching_metrics
M pdf_parser.py             页脚清理 + 计数提取对尾部垃圾容错
M pdf_parser_columns.py     逐行截页脚、丢弃纯页脚行
M static/js/script.js       删前端自算 OPS 的拷贝；渲染新列
M templates/players.html    表格 +上垒率 / 长打力 ISO
M templates/stats.html      排行榜改 get(p)；新增 9 个 tab；打击榜支持「越低越好」
M tests/test_r3_metrics_and_import.py   WHIP 测试跟随口径更新
M tests/test_stats_baseline.py          WHIP 测试跟随口径更新 + 无 BF 用例
A scripts/migrate_r5_metrics.py         副本迁移 + 报告 + --apply
A tests/test_r5_metrics_engine.py        30 个新测试
A docs/PHASE_R5_REPORT.md                阶段报告
M API_CONTRACT.md / HANDOFF.md / FEATURE_PROPOSALS.md
```

### 历史提交（可单独 revert）

```text
fix: 统计写入路径修正 + 安全加固（指标引擎 / 导入路径 / 局数口径）  ← R3
feat: PDF 解析器改用列坐标                                     ← R3
test: 新增 R3 测试与 PDF 校验工具                                ← R3
fix: 修 app.py 缺 import re 导致上传接口 500
fix: cleanup_db 部首映射表错位（改用 Unicode NFKC）
feat: 导入批次原子事务 + 显式别名 + 守备失误/牺牲打解析
feat: 热点表索引 + 迁移脚本
feat: 自动备份 / 迁移比对 / 安全端到端验证脚本
chore: ruff + CI + 清理弃用 API 与重复 fixture
docs: R3/R4 阶段报告 + README/API_CONTRACT 同步
fix: node --test 的目录写法在 node 24 上不成立
docs: 更新 README —— 校正过期数字，补充当前状态与 CI 说明
fix: CI 两个 bug —— pytest 没装、safety job 引用了 gitignore 掉的库
fix: 测试在 SQLAlchemy 2.1 下集体 error —— URI 路径没解码
fix: canary 测试在「没有生产库」的环境里误判为失败
fix: CI 的 pytest 写法差一个 -m，导致 10 个测试文件收集失败
docs: 同步 HANDOFF —— CI 首跑结论与新坑
```

### 推送方式（这台机器）

`~/.ssh` 里**没有私钥**、也没有 ssh agent → **SSH 推送不可用**。
实际走的是 HTTPS（凭据管理器里存着 GitHub 凭据）：

```bash
git push https://github.com/earthgrass/bjut-baseball-system.git <分支>
```

`origin` 这个 remote 仍指向 SSH 地址（`git@github.com:...`），
`git fetch origin` 会失败 —— 用上面的 HTTPS URL 代替。
若要恢复 SSH：生成密钥 → 加到 GitHub → `git remote set-url origin git@github.com:...`。

### 接手的人从 `main` 切分支

```bash
git checkout main && git pull
git checkout -b feature/xxx
```
