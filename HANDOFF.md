# 交接说明 — 2026-10-29 存档点（phase-R4 完成后）

> 这是**明天的起点**。从这里接着做即可，不必从头回溯。
> 上一版存档点：2026-10-29 上午（phase-R2 完成后）；R3/R4 的报告见 `docs/`。

---

## 一、当前状态：可运行，数据已校正

```bash
pip install -r requirements.txt
cp .env.example .env          # SECRET_KEY 已填好（仅本机）
python run_local.py           # → http://127.0.0.1:5000
```

管理员：`admin` / `admin123`（本机开发用；公网前必须改）

**验证状态（2026-10-29 实测）**：

| 项 | 结果 |
|---|---|
| pytest | **124 passed**（115 原有 + 9 新增） |
| node 单测 | 25 passed（`node --test tests/js/`） |
| ruff | `All checks passed!`（全项目 0 告警） |
| 端到端 | `scripts/verify_e2e.py` **30/30**（打在副本上，生产库 SHA 未变） |
| PDF 独立校验 | `scripts/validate_pdf_parse.py` 16/17（第 17 份是源 PDF 自相矛盾） |
| 生产库 | 27 球员 / **240** 比赛记录 / 2023-04-01 ~ 2025-11-22 / integrity ok / fk 0 |
| 不变量 | 档案 == SUM(game_records)，漂移 **0** |
| 生产库 SHA256 | `e337144317c206c78b7f68d80bad9aec190fda441d997b9f1ea3606ec79d140e` |

---

## 二、R4 这一轮做完了什么

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
| #22 | 没有 CI / lint | ✅ ruff + GitHub Actions（pytest / node --test / ruff，外加一个专盯「测试不碰生产库」的 job）。⚠️ `.pre-commit-config.yaml` **未创建**（装 Git 钩子需你点头） |
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

## 三、下一步（按建议顺序）

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
5. `PUT /api/players` 的 400 在前端统一提示（「请改用比赛记录录入」）。
6. DataTables 加到 players / matchup 页面（现在只有 game_stats 有分页）。
7. 建 `.pre-commit-config.yaml`（需要你点头 —— 装 Git 钩子属于持久化外部工具）。

### 需要先跟你确认的（业务歧义，脚本不能自动判）

8. **赛季怎么切**（4 月春季 + 10/11 月秋季的学期制是否成立）——
   需要 Game 实体才能表达，会影响所有统计口径。
9. **2025-10-25 vs 华北电力大学那份 PDF 自己前后矛盾**：
   投手局数之和 1.0，但它的 Totals 行写 1.2。是源数据录入错误，还是记分卡惯例？
   （解析器按「Totals 行」为准 → 1.2；按明细求和 → 1.0。）
10. **`2025-11-22 vs 北京交通大学` 的 16 条记录没有对应 PDF** ——
    是漏传了 PDF，还是这��是手工录的？目前原样保留，无法用 PDF 验证。
11. **`尹文浩`** 在 2023-04-16 的记分卡上有一行（0 AB，像是教练）——
    他是队员吗？若是，需要补录。

---

## 四、必须知道的坑（别踩）

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

## 五、文档地图

| 文档 | 内容 |
|---|---|
| `README.md` | 项目总览、快速开始、功能、已知问题与修复记录 |
| `API_CONTRACT.md` | **接手必读** —— 接口契约、认证/CSRF、指标口径、开发约定 |
| `API_DOCUMENTATION.md` | curl 调用示例 |
| `FEATURE_PROPOSALS.md` | 10 个新功能提案 + 四维评估 |
| `docs/ISSUES_AUDIT_20261029.md` | 全量问题清单审计（35 条，本轮收敛了大半） |
| `docs/PHASE_R4_REPORT.md` | **最新阶段报告**（数据校正迁移 + 硬化） |
| `docs/PHASE_R3_REPORT.md` | 指标引擎 + 列坐标解析器 |
| `docs/PHASE_R2_REPORT.md` | 收窄 PUT + 批量录入 + 三振 bug 修复 |
| `docs/PHASE_R0_REPORT.md` | 数据事故时间线与取证（改 conftest 前必读） |
| `docs/DB_INVENTORY.md` | 16 个数据库文件盘点 |
| `docs/STATS_WRITE_PATH_REPORT.md` | Phase E0 的统计写入口盘点（**行号已过时**） |
| `docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` | 作者的 Phase C 蓝图（Game 实体 / Service 层） |

---

## 六、Git 状态

分支：`feature/2026-10-28-runtime-restore`（尚未合并到 `main`）。

本轮提交（可单独 revert）：

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
```

接手的人从 `main` 切分支：

```bash
git checkout main && git pull
git checkout -b feature/xxx
```
