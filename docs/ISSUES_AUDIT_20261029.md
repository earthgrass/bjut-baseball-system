# 全量问题清单 — 2026-10-29 审计

> 基线：`feature/2026-10-28-runtime-restore` @ `296eb38`（phase-R2 完成后）
> 生产库：`instance/baseball_players.db`，SHA256 `eb63d4a3a09c46dd4b1bfc07c6c685f2d271f10b2ed06fdac8edabab6da15d7e`
> 方法：全部结论**逐条在当前代码或生产库上取证**，未验证的一律标注 UNVERIFIED。
> 审计期间生产库只读；所有写实验都在 `instance/` 下的副本上做，测完即删。

---

## 0. 结论摘要

| 等级 | 数量 | 性质 |
|---|---|---|
| **P0** | **0** | 无阻断级问题 |
| **P1** | **15** | 数据一致性 / 安全 —— 建议下一阶段优先处理 |
| **P2** | **9** | 架构 / 工程质量 |
| **P3** | **8** | 整洁度 / 技术债 |
| **需业务方拍板** | **4** | 脚本不能自动判定 |

**没有 P0** 是好消息：数据库结构完整、无认证绕过、无路径穿越、测试不碰生产库。

但有 **3 条 P1 会让"修 PDF 解析器"这件事白干**，必须先看：

- **#2 重导 PDF 无法修正任何历史数据**（实测 212 条跳过 / 0 条修正）——
  `HANDOFF.md` 里"重导 17 份 PDF 就能修正全部 230 条历史数据"是**错的**。
- **#3 PDF 导入会凭空造出幽灵球员**（实测造出 3 个乱码名字的球员 + 5 条记录）。
- **#4 局数单位口径不自洽** → ERA/WHIP 系统性失真，最大偏差 **44%**。

---

## 1. 生产库现状（只读审计）

```text
PRAGMA integrity_check     → ok
PRAGMA foreign_key_check   → OK
孤儿 game_records（球员不存在）→ 0
孤儿 profiles                 → 0
负值记录                      → 0
安打 > 打数的记录             → 0
profile vs SUM(game_records)  → 27 名球员全部一致，漂移 0
```

**唯一的数据歧义**：

```text
player_id 28（欧阳翦）· 2024-11-16 · 北京交通大学 · 打击记录 × 2
```

这是取证报告里标为 AMBIGUOUS 的那一条，至今没有结论。

**数据完整度（暴露 PDF 解析器的静默错误率）**：

| 字段 | 为 0 的条数 | 占比 |
|---|---|---|
| 打击 `triples`（三垒打） | 188 / 188 | **100% 全丢** |
| 打击 `sacrifice_hits` | 188 / 188 | **100% 全丢** |
| 打击 `sacrifice_flys` | 188 / 188 | **100% 全丢** |
| 打击 `hit_by_pitch` | 158 / 188 | 84% |
| 打击 `doubles` | 151 / 188 | 80% |
| 打击 `stolen_bases` | 97 / 188 | 52% |
| 打击 `at_bats` | 30 / 188 | 16% |
| 投球 `wild_pitches` | 42 / 42 | **100% 全丢** |
| 投球 `batters_faced` | 39 / 42 | 93% |
| 投球 `home_runs_allowed` | 39 / 42 | 93% |
| 投球 `pitches` | 13 / 42 | 31% |
| 投球 `strikes` | 13 / 42 | 31% |

**结论**：PDF 解析"17/17 成功、0 异常"，但数据静默错误率极高。

---

## 2. P1 — 数据一致性与安全（15 条）

### #1 PDF 导入用 `+=` 增量写档案，不走 rebuild

- **位置**：`import_pdfs.py:158-170`（13 个打击字段）、`import_pdfs.py:217-227`（11 个投手字段）
- **证据**：`player.at_bats_total += batter['at_bats']` 等 24 处
- **影响**：与本项目最核心的不变量「档案 = SUM(game_records)」**直接冲突**。
  写入路径现在有两条：比赛记录接口走 rebuild（正确），PDF 导入走增量（错）。
  目前被启动时的 `sync_stats_from_game_records()` 全量重算掩盖着，但那是**掩盖不是修复**。
- **修法**：写完 `GameRecord` 后调 `rebuild_player_stats(player.id)`，删掉全部 `+=`。

### #2 重导 PDF 无法修正任何历史数据（实测推翻既有计划的前提）

- **证据**（在生产库副本上跑 `import_all_pdfs(dry_run=False)`）：
  ```text
  导入前 game_records: 230
  导入后 game_records: 235（新增 5 条）
  imported 合计: 0   |   skipped 合计: 212
  原有 230 条里字段被改动的条数: 0
  ```
- **原因**：`import_game_record()` 的去重检查（`import_pdfs.py:128`、`:187`）
  命中已有记录就 `continue`，**新解析出的值永远写不进去**。
- **影响**：`HANDOFF.md` 第三条待办"重导 17 份 PDF 就能修正全部 230 条历史数据"
  **前提不成立**。只改解析器而不动去重逻辑，历史数据一条都修不了。
- **修法**：需要「先删后导」模式（按 game_date+opponent 删掉旧记录再重导），
  或给 `import_game_record` 加 `replace=True` 分支。

### #3 PDF 导入会凭空造出幽灵球员

- **证据**（同一实验的副本）：新导入造出 3 个球员、5 条记录：
  ```text
  id=42 姓名='齐佳王佳帅' 背号='35' 位置='捕手'   ← '齐佳' + '王佳帅' 被粘成一个名字
  id=43 姓名='孙世铎'     背号='1'  位置='投手'
  id=44 姓名='子非陈'     背号='6'  位置='投手'
  ```
  后两个名字在 27 人名单里都不存在。
- **原因**：`find_or_create_player()` 只按名字查，查不到就建新球员，
  **没有任何"这个名字像不像人名"的校验**。
- **影响**：一次误导入就污染球员表（还会连带进统计档案、排行榜、PDF 导入的增量）。
- **修法**：解析阶段对姓名做白名单/格式校验；导入阶段对未知名字走人工确认而非直接建档。

### #4 局数单位口径与 ERA/WHIP 公式不自洽 → 系统性失真

- **位置**：`database.py:406-410`（`era = ER*9/IP`、`whip = (BB+H)/IP`）
- **问题**：库里 `innings_pitched` 存的是 box score 上印的**字面值**，
  中文记法 `.1` = 1/3 局（实测存在 `0.1 / 0.2 / 1.1 / 1.2 / 2.1`）。
  但 `ER*9/IP` 要求 IP 是"真实局数"（1.1 局 ≠ 1⅓ 局）。
- **实测失真**（42 条投球记录中 10 条局数带小数）：

  | 投手 | 档案IP | 真实IP | 现 ERA | 真实 ERA | 现 WHIP | 真 WHIP |
  |---|---|---|---|---|---|---|
  | 吴鸿硕 | 3.7 | 5.333 | **17.03** | 11.81 | **5.14** | 3.56 |
  | 白云箫 | 5.2 | 5.667 | 20.77 | 19.06 | 3.85 | 3.53 |
  | 李昊宇 | 5.1 | 5.333 | 17.65 | 16.88 | 2.94 | 2.81 |
  | 欧阳翦 | 13.3 | 14.000 | 10.15 | 9.64 | 1.95 | 1.86 |

  吴鸿硕的生涯 ERA 偏高 **44%**。单场最极端的一例：
  欧阳翦 2024-11-16 vs 北京交通大学，IP=0.1、ER=4 → **现 ERA 360.00**，真实 108.00。
  这条会直接出现在投手排行榜上。
- **修法**：这需要一次**全库单位统一**（迁移，不是重算）：
  明确 IP 存"真实局数"还是"记法字面值"，然后一次性转换 42 条记录 + 统一 6 处公式。
  属于规范 §22「先保留、再转换、最后清理」里的"转换"环节。

### #5 `cleanup_db.py` 合并重复球员后不重算累计

- **位置**：`cleanup_db.py:161`（把重复球员的 game_records 改挂到保留球员）→ `:187`（只调 `update_calculated_fields()`）
- **影响**：`update_calculated_fields()` 只重算 AVG/SLG/OBP，**不动累计值**。
  合并后 `at_bats_total` 等仍是旧值，与 game_records 严重不符，且不会自愈。
- **修法**：`:187` 改调 `rebuild_player_stats(kept.id)`。

### #6 路径泄漏：PDF 解析把异常原文透传给匿名用户

- **位置**：`pdf_parser.py:118` → `result['error'] = f'读取PDF失败: {e}'`
- **链路**：`/api/pdf/parse/<path>`（**匿名可达**）→ `parse_pdf()` → 异常原文含**服务器绝对路径** → 直接回给浏览器
- **验证**：`app.py:1731` 确实做了 `_safe_data_path()`（**路径穿越本身是挡住的**），
  但错误消息里的路径不是受控内容。
- **修法**：解析失败时返回固定文案，详细异常只写服务端日志。

### #7 路径泄漏：两处直接回显 `str(e)`

- **位置**：`app.py:1291`（`读取文件失败: {str(e)}`）、`app.py:1875`（`解析PDF失败: {str(e)}`）
- **说明**：`_safe_error()` 本身是安全的（只对 `ValueError/KeyError/TypeError` 回显原文，
  其它异常统一 `logger.exception` + 500「操作失败」）。
  这两处是**绕过 `_safe_error` 直接回显**的。
  已核实其余 4 处 `str(e)`（`app.py:834/1270/1733/1771`）都是 `except ValueError` 的业务消息，安全。

### #8 `confirm_import` 缺路径校验

- **位置**：`app.py:1883-1888` —— 直接用请求体里的 `filepath`，只做 `os.path.exists` 判断
- **对比**：其它所有 PDF 路由都走了 `_safe_data_path()`
- **影响**：admin 可指向服务器任意路径让系统解析（admin 本就可信，实际危害有限，
  但破坏了"只有 data/ 下的文件能被解析"这条不变量）。

### #9 上传文件名被 `secure_filename` 抹掉中文 → 不同 PDF 互相覆盖

- **证据**（werkzeug 实测）：
  ```text
  '2024年vs清华.pdf'               → '2024vs.pdf'
  '北京工业大学_vs_北京交通大学.pdf' → 'vs_.pdf'
  '中文名.pdf'                     → 'pdf'
  ```
- **影响**：本项目的 PDF **全部是中文名**（`data/2023/北京工业大学_vs_北京交通大学_Apr_9_2023.pdf`）。
  连续上传两个不同名字的 PDF 会落到**同一个文件名**，后一个覆盖前一个 —— 静默丢文件。
- **修法**：保留中文（`secure_filename` 不适合中文场景），
  改用「UUID + 原扩展名」，或对中文名做哈希。

### #10 上传没有大小限制

- **证据**：`app.py:1796-1814` 只检查扩展名与文件名，**没有 `MAX_CONTENT_LENGTH`**，
  也没有 MIME / 文件头校验。
- **影响**：一个超大文件会直接写进 `data/uploads/`，可能撑爆磁盘。
- **修法**：`MAX_CONTENT_LENGTH` + 魔数（`%PDF-`）校验。

### #11 `errors_fielding` / `passed_balls` 是彻底的孤儿字段

- **证据**：`game_records` 有这两列、`fielder_profiles` / `pitcher_profiles` 也有，
  但 `grep errors_fielding app.py` **零命中**；库里 230 条记录这两列**全为 0**。
- **影响**：两层都没人写、没人读。R2-A 收窄 PUT 之后，连原来那条唯一的写路径也没了。
  属于"看起来能用其实永远为 0"的字段。
- **修法**：要么给 GameRecord 补写入源并纳入聚合，要么删列。

### #12 启动时自动改库（违反"审计不自动修"原则）

- **位置**：`database.py:664-668`
  ```python
  db.create_all()
  migrate_legacy_player_stats()    # 迁移 + 清零 legacy 列
  sync_stats_from_game_records()   # 全队重算档案并 commit
  init_default_admin()
  ```
- **问题**：
  - `sync_stats_from_game_records()` 每次启动**重写全队档案** ——
    规范 §16「禁止启动自动修 Stats」、§61「检测可以自动，修复必须显式」。
  - 副作用更糟：它把 #1 的 PDF 导入漂移**静默抹平** —— bug 被掩盖，不是被修。
  - 它只处理**有 game_records 的球员**，没记录的球员档案保持原样 → 口径不一致。
  - `migrate_legacy_player_stats()` 现在已是**空操作**（legacy 列在 phase-R1 已删），
    但每次启动仍跑一次 SELECT。

### #13 公网部署前的凭据风险（部署即变成 P0）

- **证据**：生产库 admin 口令 = `admin123`；`app.py` / `run.py` 绑 `0.0.0.0`
- **说明**：本机开发是刻意的弱口令（用户 2026-10-28 明确选定），**公网部署前必须改**
  （`scripts/reset_admin_password.py`）。
- **附带**：`RATELIMIT_LOGIN=5/minute` 但 `RATELIMIT_STORAGE_URI=memory://`
  → 多进程部署时每个进程各算各的，重启即清零，**多 worker 下基本等于没有限流**。

### #14 `instance/` 里的开发脚本会打实盘并写库

- **证据**：`instance/_verify_writes.py:48`、`instance/_verify_e2e.py:84` 用硬编码
  `admin/admin123` POST/PUT/DELETE `127.0.0.1:5000` 的**实盘服务器**
  （不像其它探针那样复制到 scratch 库）。
- **影响**：谁跑一次就真的写坏统计。且 `instance/_app_backup_before_writes.py`
  里还留着**废弃的 `+=` 累加与 `safe_subtract` 反向扣减** ——
  万一被误当作 app.py 恢复，会重新引入漂移。

---

## 3. P2 — 架构与工程质量（9 条）

### #15 指标公式 6 份拷贝

```text
database.py:406              （权威）
app.py:1372                 （投手排行榜）
app.py:1485                 （对局汇总）
import_pdfs.py:231
migrate_profiles_sqlite.py:164
static/js/script.js:517     （前端预览）
```
OBP 另有 2 份（`database.py:358-361`、`migrate_profiles_sqlite.py:140-144`）。
**改一个指标要同步改 6 处**（含前端那份）。

### #16 没有 Service 层，两个巨型文件

```text
app.py       1911 行
database.py   969 行
import_pdfs.py 347 行
```
Blueprint 里直接写业务与事务（违反规范 §38），模型里没有 Service 边界（§39/§40）。

### #17 热点表没有索引

```text
game_records        → 无索引
players             → 无索引
fielder_profiles    → 无索引
pitcher_profiles    → 无索引
```
`game_records` 是所有统计聚合的扫描对象。现在 230 行无痛，每赛季增长后是 scaling 风险。

### #18 没有自动备份机制

- **证据**：`scripts/` 下无备份脚本；代码里也没有定时备份逻辑。
  现存备份全是手工产物（`instance/baseball_players.backup_*.db`、`recovery/` 快照）。
- **影响**：一次误操作就可能不可逆（2026-04 那次数据事故就是前车之鉴）。

### #19 PDF 解析靠文本切分而非列坐标

- **证据**：`pdf_parser.py` 用 `line.split('\n')`、`split('AB')`、正则匹配位置切分，
  没用 pdfplumber 的 word 坐标。
- **影响**：这就是 §1 那张"静默错误率"表的根因 —— 列位置一变就串列，
  而解析过程**不报错**。**这是 #1~#5 里多个问题的共同上游。**

### #20 缺少 Game 一级实体

- **现状**：一场比赛 = `game_date + opponent` 字符串。
- **影响**：双赛日无法表达；对手改名会产生"同一场比赛两条记录"；
  去重键也依赖对手字符串的写法一致。
- **规范**：§18/§19 要求引入 `Game` 实体与 `UNIQUE(game_id, player_id, record_type)`。

### #21 `import_pdfs.py` 给野手造空的投球档案

- **位置**：`import_pdfs.py:85-100` —— 新建球员时对 **26 个字段**（含 12 个投手字段）
  逐个 `setattr(player, field, 0)`
- **机制**：property proxy 的 setter 调 `ensure_pitcher_profile()` → 自动建行
- **实测指纹**：库里 `pitcher_profiles` **27 行**，但只有 **6 名球员被标记为投手** ——
  **21 名野手有空的投球档案行**（其中 20 行全为 0，纯粹是空壳）。
- **影响**：`to_dict()` 会给野手返回 ERA 0.00 / WHIP 0.00 等字段；
  任何按 `pitcher_profiles` 统计的地方都要额外过滤。

### #22 没有 CI / lint / pre-commit

- **证据**：无 `.github/`、无 `pyproject.toml`、无 `.pre-commit-config.yaml`、无 ruff 配置。
- **影响**：本轮发现的"dict 字面量重复键"这类问题，一个 10 行的 AST 检查就能全项目拦住；
  现在只能靠人工 review。

### #23 模板层大量重复

- **证据**：14 个模板里 **12 个各自带一份 `<style>` 块和一份内联导航栏**
  （只有 `_arena_bg.html` / `_navbar.html` 是 partial）。
- **影响**：改一处样式/导航要改 12 处 —— 本轮 R2-B 加导航入口时就改了 2 处
  （`base.html` 系 + `add_game_record.html` 系的独立导航）。

---

## 4. P3 — 技术债与整洁度（8 条）

| # | 问题 | 位置 |
|---|---|---|
| #24 | `Query.get()` 已弃用（SQLAlchemy 2.x），测试输出刷 240+ 条 deprecation warning | `app.py:168` 等多处 |
| #25 | `migrate_legacy_player_stats()` / `_zero_out_legacy_columns()` 已是空操作残留 | `database.py:784+` |
| #26 | `static/js/script.js` 剩余死代码（`displayPlayers` / `addCalculationListeners` / `calculateBattingStats` / `calculatePitchingStats`） | `static/js/script.js` |
| #27 | 无 `Game` 实体导致 `game_records` / `players` 零索引（`EXPLAIN` = `SCAN`） | schema |
| #28 | Session cookie 未显式配置 `SESSION_COOKIE_SECURE` / `SAMESITE`（Flask 默认 HttpOnly=True 是好的） | `config.py` |
| #29 | 限流用内存后端，多 worker / 重启即失效（见 #13） | `config.py:22` |
| #30 | `instance/` 有 41 个开发残留文件（探针、补丁源、旧 app.py 备份、日志） | `instance/` |
| #31 | `_safe_error` 对 ValueError 返回 400、对其它异常返回 500，但调用点有 7 处自定 status，语义略乱 | `app.py:200-209` |

---

## 5. 需业务方拍板（脚本不能自动判）

| # | 问题 | 现状 |
|---|---|---|
| #32 | 欧阳翦 2024-11-16 vs 北京交通大学 的 2 条打击记录 —— 重复导入还是双赛日？ | 取证标 AMBIGUOUS，至今无结论 |
| #33 | 赛季怎么切？（4 月春季 + 10/11 月秋季的学期制是否成立） | 无任何赛季字段 |
| #34 | 刘孝宇 2024-10-20（1.0 局被 8 分、6 自责分）与 2024-11-23（1.0 局被 7 分、3 自责分）—— 真实数据还是 PDF 串列？ | 这两场直接把他生涯 ERA 拉到 22.50 |
| #35 | PDF 里的 `孙世铎`、`子非陈`、`王佳帅` 对应队里谁？（#3 的幽灵球员来源） | 27 人名单里没有前两个 |

---

## 6. 建议处理顺序

```text
第一批（数据正确性，1-2 天）
  #2 先做「先删后导」模式 + #1 改成 rebuild     ← 否则修解析器也白修
  #19 解析器改用列坐标                        ← 一次修掉 8 个静默错误
  #3  导入时对未知姓名走人工确认
  ↓
第二批（指标口径，1 天）
  #4  统一局数单位（全库转换 + 6 处公式收成一处，见 #15）
  #11 errors_fielding / passed_balls 定去留
  ↓
第三批（安全加固，半天）
  #6 #7 #8  路径泄漏与路径校验
  #9 #10    上传文件名与大小限制
  #13 #14   改口令、清 instance/ 残留
  ↓
第四批（架构，按原定 Phase C 顺序）
  #16 Service 层 → #20 Game 实体 → #17 索引 → #22 CI
  #5  cleanup_db 修 rebuild（顺手）
  #12 启动自愈改 audit-only（与 #1 一起做）
```

**注意依赖关系**：#4（局数单位）和 #19（列坐标）会同时改动 42~230 条历史记录，
必须按规范 §25「先在生产库副本上跑 + 出迁移报告」执行，不能直接打真实库。

---

## 附录：本次审计实际执行的命令

```bash
# 生产库只读指纹与完整性
python -c "import sqlite3; c=sqlite3.connect('file:instance/baseball_players.db?mode=ro', uri=True); ..."
python -c "import hashlib; print(hashlib.sha256(open('instance/baseball_players.db','rb').read()).hexdigest())"

# 端点与认证面枚举（AST）
python -c "import ast; ... 列出所有 route 及 admin_required/login_required 装饰器"

# dict 重复键 AST 扫描
python -c "import ast; ... 扫 app.py/database.py/import_pdfs.py/sync_data.py"

# PDF 重导实验（生产库副本，测完即删）
cp instance/baseball_players.db instance/_agent_scratch_reimport_20261029.db
DATABASE_FILE=... python -c "from import_pdfs import import_all_pdfs; import_all_pdfs(dry_run=False)"
# → imported 0 / skipped 212 / 新增 5 条（含 3 个幽灵球员）/ 原有 230 条改动 0

# PDF 解析器逐份跑（不写库）
python -c "from pdf_parser import parse_pdf; [parse_pdf(f) for f in glob('data/*/*.pdf')]"
# → 17/17 份解析成功，17 份都含两栖球员

# 局数单位失真量化
python -c "..."  # 逐条换算 42 条投球记录的 ERA/WHIP
```

**审计结束时生产库 SHA256 = `eb63d4a3a09c46dd4b1bfc07c6c685f2d271f10b2ed06fdac8edabab6da15d7e`，
与审计开始时一致。**
