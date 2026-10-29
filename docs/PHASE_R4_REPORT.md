# PHASE R4 REPORT — 数据校正迁移 + 审计项收敛

> 日期：2026-10-29
> 分支：`feature/2026-10-28-runtime-restore`
> 基线：`4745021`（phase-R3：metrics.py + 列坐标解析器 + 导入路径修正）
> 规范：`# POWER ARENA — 首席开发导师长期规范.md`（§16/§22/§25/§28/§31/§61/§64）

---

## 1. Objective

把 R3 修好的 PDF 解析器**真正应用到生产数据**，并把 `docs/ISSUES_AUDIT_20261029.md`
里剩余的、**不需要业务方拍板**的条目全部收敛掉。

R3 结束时留下一个尴尬的状态：**代码是对的，数据是错的** ——
列坐标解析器写好了、16/17 份 PDF 的独立校验也过了，但生产库的 230 条记录
仍然是旧文本解析器的产物（三垒打 188/188 全丢、面对打席 93% 丢、暴投 100% 丢、
HBP 被安到**对方球员**头上）。本阶段的第一目标就是把这个落差抹平。

---

## 2. Repository state before work

```
分支：feature/2026-10-28-runtime-restore
HEAD：4745021 test: 新增 R3 测试与 PDF 校验工具
工作区：干净（只有 1 个未跟踪的规范文件）
生产库 instance/baseball_players.db
  SHA256  2f2522b7620feb58390ba645a8d7df6eeb3af3c77db4d26840079751d47e6ba7
  players 27 / game_records 230 / 日期 2023-04-01 ~ 2025-11-22
  integrity ok / fk 0 / 档案漂移 0
测试：115 passed
```

**先说一个必须交代的发现**：R3 报告与 `HANDOFF.md` 里写的生产库 SHA256
（`eb63d4a3…`）**和当时的实际值对不上** —— 本阶段开工时生产库已经是
`2f2522b7…`。取证结论：R3 期间（11:26 左右）生产库被重建过一次统计档案
（`instance/baseball_players.pre_r3_overwrite_20261029_112609.db` 与当前文件
**逐字节相同**，说明那次「重导 PDF」从未落地），随后档案按新口径（真实局数）
重建 —— 所以当前库的 ERA/WHIP 已经是修正后的值，但**逐场比赛记录仍是旧的**。

`game_records` 表与 `recovery/recovered_pre_incident.db` **逐行完全一致**，
即：生产库的比赛记录 = 事故前恢复出来的原始记录，从未被 PDF 重导污染过。

---

## 3. Files inspected

`app.py` `database.py` `import_pdfs.py` `pdf_ingest.py` `pdf_parser.py`
`pdf_parser_columns.py` `pdf_parser_columns.py` `metrics.py` `config.py`
`cleanup_db.py` `sync_data.py` `migrate_profiles_sqlite.py` `scripts/*`
`tests/*` `static/js/*` `templates/*` `docs/*` `HANDOFF.md` `README.md`
`API_CONTRACT.md` + 17 份 box score PDF（原文逐份核对）

---

## 4. Findings

### P1（本阶段处理）

| # | 问题 | 处置 |
|---|---|---|
| #1 | 生产库仍是旧解析器的数据 | 本阶段提升到生产库（§5.1） |
| #2 | 重导无法修正历史数据 | R3 已加覆盖模式；本阶段用它完成了重导 |
| #3 | 导入凭空造幽灵球员 | R3 已修；本阶段验证 0 新球员 |
| #4 | 局数单位口径 | R3 已修（逐条换算）；本阶段数据落库后 ERA/WHIP 复核一致 |
| #5 | `cleanup_db.py` 合并球员后不重建档案 | **已修**：改调 `rebuild_player_stats()` |
| #6 #7 | 路径泄漏 | R3 已修；本阶段验证解析失败不泄漏绝对路径 |
| #8 | `confirm_import` 缺路径校验 | R3 已修 |
| #9 #10 | 上传文件名/大小限制 | R3 已修 |
| #11 | `errors_fielding` / `passed_balls` 是孤儿字段 | **部分解决**：查明 4 份 PDF 有 `E:` 标签（守备失误）、1 份有 `SF:`（高飞牺牲打）→ 解析器补上，档案开始聚合；`passed_balls` 在 PDF 里**确实没有数据源**（17 份 PDF 的标签只有 AB/R/H/RBI/BB/SO/S/2B/3B/HR/TB/HBP/SB/CS/BF/WP/LOB/W/L/E/SF），保留列并写明「不是真实 0」 |
| #12 | 启动自动重算档案 | R3 已改为 audit-only；本阶段验证启动不写库 |
| #14 | `instance/` 里的探针脚本打实盘写库 | **已处理**：两个脚本加了安全闸（默认拒绝执行），并新增了**打在副本上**的 `scripts/verify_e2e.py` 取代它们 |

### 本阶段新发现（ruff / 实测）

| 级别 | 问题 | 证据 | 处置 |
|---|---|---|---|
| **P1** | `app.py` 用了 `re.sub()` 却**没 import re** | `ruff F821`；PDF 上传接口 100% 500 | 已修（补 `import re`），并补了上传接口的端到端覆盖 |
| **P1** | `cleanup_db.py` 的 CJK 部首映射表**整体错位一位** | `ruff F601` + NFKC 比对：U+2F0C 被写成「门」（部首表里没有这个字），导致其后 200+ 条映射全部偏移 | 已修：改用 Unicode NFKC 权威映射 + 4 条简体覆盖（馬→马 等） |
| **P2** | `sync_data.py` 是「档案重算」的**第二套实现**（24 处 `+=`、局数按字面值、硬编码生产库路径） | 审计 #15/#42 | 已修：改为只调用权威实现 `rebuild_player_stats()` |
| **P2** | `migrate_profiles_sqlite.py` 自己抄了一份指标公式，且抄错两处（OBP 漏 SH、ERA 用字面局数） | 审计 #15 | 已修：改用 `metrics.py` |
| **P2** | 前端 `static/js/script.js` 有一份 ERA/WHIP/OBP 拷贝，而且用的是**字面局数**（预览 8.18 / 服务器 6.75 对不上） | 审计 #15；且这三个函数**全项目无人调用** | 已删（110 行死代码），指标唯一性测试扩展到扫 JS |
| **P3** | `Query.get()` 弃用告警 312 条 | ruff/pyflakes | 已修（app.py 5 处 + tests 37 处），告警降到 13 条 |
| **P3** | `tests/conftest.py` 有两份完全重复的 fixture 定义 | ruff F811 | 已删重复块 |
| **P3** | 前端预览里的 OBP 分母漏了牺牲触击(SH) | 与 Python 侧同一个 bug | 随死代码一并删除 |

### 需业务方拍板（本阶段**未**处理，已从 AMBIGUOUS 收敛为 2 项）

| # | 问题 | 状态 |
|---|---|---|
| #32 | 2024-11-16 的「欧阳 / 欧阳翦」 | **已由业务方确认：同一个人**。已写成显式别名 `PLAYER_NAME_ALIASES`，导入报告里仍然显式上报（不静默合并） |
| #33 | 赛季怎么切（4 月春 + 10/11 月秋） | 仍无结论 —— 需要 Game 实体（Phase C） |
| #34 | 刘孝宇 2024-10-20 / 2024-11-23 的异常失分 | **本阶段数据已修正**：他 2025-10-26 的那 1 局原本被旧解析漏掉，修正后生涯 ERA 22.50 → 19.80 |
| #35 | PDF 里的孙世铎 / 子非陈 / 王佳帅 | **已澄清**：新解析器不再把对方球员混进我方列，这三个名字现在**不会**出现在我方数据里；残留的「尹文浩」经查是记分卡上的**教练行**（0 AB），已跳过且未建球员 |

---

## 5. Changes

### 5.1 数据校正迁移（生产库写入）

**副本验证 → 用户确认 → 提升**，全程可回滚。

| 阶段 | 动作 | 结果 |
|---|---|---|
| 备份 | `python scripts/backup_db.py` | `instance/backups/baseball_players.backup_20261029_155329.db`（与提升前生产库**逐条零差异**） |
| 预演 | 只读脚本对齐 PDF 解析值与库内值 | 79 条有字段变化、135 条完全相同、新增 11、**消失 0** |
| 副本迁移 | `DATABASE_FILE=_r4_migration3.db python import_pdfs.py --replace` | 224 条写入、214 条旧记录被替换、0 错误、0 新球员、1 个未知姓名跳过、1 处别名合并 |
| 比对 | `python scripts/compare_db.py 备份 新库` | 行数、逐字段差异、完整性、不变量漂移全部逐项列出 |
| 提升 | `python import_pdfs.py --replace`（生产库） | 230 → 240 条 |
| 复验 | 比对 + 全量测试 + E2E | 见 §8 |

**数据变化（生产库 230 → 240 条）**

| 指标 | 迁移前 | 迁移后 |
|---|---|---|
| 三垒打记录 | 0 | 3 |
| 面对打席（BF）记录 | 3 | 39 |
| 暴投（WP）记录 | 0 | 2 |
| 被触身球（HBP） | 30 条有值，但**安到了错的人头上** | 27 条有值，全部对得上 PDF 原文 |
| 守备失误（E） | 0（列存在但没人写） | 3 条（PDF 里有 `E:` 标签的 4 份） |
| 高飞牺牲打（SF） | 0 | 1 条 |
| 投手 ERA | 刘孝宇 22.50 / 李昊宇 16.88 | 刘孝宇 19.80 / 李昊宇 15.00 |

**没有动的**：2025-11-22 vs 北京交通大学那 16 条（**没有对应 PDF**，原样保留）；
球员名单零变化（27 人，不多不少）。

### 5.2 索引迁移（审计 #17）

`game_records` / `players` / `player_positions` 此前**一个索引都没有**，
`EXPLAIN QUERY PLAN` 全是 `SCAN`。新增 5 个索引后：

```text
迁移前: SCAN game_records / SCAN players
迁移后: SEARCH game_records USING COVERING INDEX ix_game_records_player (player_id=?)
        SEARCH game_records USING COVERING INDEX ix_game_records_game (game_date=? AND opponent=?)
        SEARCH players USING COVERING INDEX ix_players_name (name=?)
```

索引同时写进模型（`database.py` 的 `__table_args__`）——
**新建库由 `create_all()` 自动带上，老库由 `scripts/add_indexes.py` 补建**，
两边都要有，缺一不可。迁移**零数据变化**（240 条记录逐条比对无差异）。

### 5.3 代码改动清单

| 文件 | 改动 | 原因 |
|---|---|---|
| `import_pdfs.py` | 批次**原子事务**（规范 §28）；显式别名表 `PLAYER_NAME_ALIASES`；写入 `sacrifice_flys` / `errors_fielding` | 一个批次一个事务，中途失败整体回滚 |
| `database.py` | 档案聚合补 `errors_fielding`；热点表索引声明；`audit_stats_drift` 增加两个字段 | 审计 #11 / #17 |
| `pdf_parser_columns.py` | 新增 `_apply_fielding_extras`：从**投球附加行**取 `E:` / `SF:` | 守备失误印在投球区，但那是打者的数据 |
| `pdf_parser.py` | 标签正则补 `SF`；单字母标签加 `(?<![A-Za-z])` 前视 | `SF:` 之前匹配不上；`HOME:` 里的 `E:` 会被误当失误标签 |
| `cleanup_db.py` | 合并重复球员后**重建**档案；部首映射改用 NFKC | 审计 #5 + F601 错位 bug |
| `sync_data.py` | 删掉自带的第二套聚合实现，只调 `rebuild_player_stats()` | 规范 §42「统计写入口唯一」 |
| `migrate_profiles_sqlite.py` | 指标改用 `metrics.py` | 公式重复且抄错 |
| `static/js/script.js` | 删 110 行死代码（含最后一份前端公式拷贝） | 审计 #15 / #26 |
| `app.py` | 补 `import re`（F821）；`Query.get` → `db.session.get`；生产配置体检告警 | 上传接口 100% 500 的根因 |
| `config.py` | 会话 Cookie（HttpOnly / SameSite=Lax / Secure 可配）；限流存储说明 | 审计 #28 / #29 |
| `scripts/backup_db.py`（新） | 一致性快照备份 + SHA256 + 指纹 + 保留份数 | 审计 #18：项目此前**没有任何自动备份** |
| `scripts/add_indexes.py`（新） | 索引迁移 + 迁移前后执行计划对比 | 审计 #17 |
| `scripts/compare_db.py`（新） | 迁移前后逐条比对报告器 | 规范 §25「迁移报告」要可复算 |
| `scripts/verify_e2e.py`（新） | 端到端验证**打在副本上**，跑完复验生产库 SHA 未变 | 取代会写坏生产库的旧探针 |
| `pyproject.toml` / `requirements-dev.txt` / `.github/workflows/ci.yml` | ruff 配置 + CI（pytest / node --test / ruff）+ 独立的「测试不碰生产库」job | 审计 #22 |

### 5.4 新增测试（9 个）

`tests/test_r4_migration_and_hardening.py`：别名显式上报、批次原子性（失败整体回滚）、
`cleanup_db` 合并后重建档案、热点表索引、备份脚本（一致性 + 不改源库）、
`Query.get` 全项目清零。

---

## 6. Commands actually executed

```bash
# 取证
python -m pytest -q                                    # 115 passed（开工前）
python scripts/validate_pdf_parse.py                   # 16/17 份通过
python scripts/game_keys.py                            # 17 份 PDF ↔ 生产库比赛键逐一对齐
python scripts/migration_preview.py                    # 只读预演（未写任何库）

# 迁移
python scripts/backup_db.py
cp instance/baseball_players.db instance/_r4_migration3.db
DATABASE_FILE=_r4_migration3.db python import_pdfs.py --replace
python scripts/compare_db.py instance/baseball_players.db instance/_r4_migration3.db
python import_pdfs.py --replace                        # ← 生产库提升
python scripts/compare_db.py instance/backups/….db instance/baseball_players.db
python scripts/add_indexes.py                          # ← 生产库索引迁移
python scripts/verify_e2e.py                           # 30/30 通过
python -m ruff check .                                 # All checks passed!
```

---

## 7. Test result

```text
124 passed (115 原有 + 9 新增), 13 warnings
ruff check .  →  All checks passed!
node --test 'tests/js/*.test.js'  →  25 passed
scripts/validate_pdf_parse.py  →  16/17（唯一不过的那份是源 PDF 自相矛盾）
scripts/verify_e2e.py  →  30/30
```

---

## 8. Production DB safety proof

```text
提升前 SHA256   2f2522b7620feb58390ba645a8d7df6eeb3af3c77db4d26840079751d47e6ba7
提升后 SHA256   c2a1923e8a058205bc6d72a1d32a10b312420cf268291c0a74d96768c65198d4
索引迁移后      e337144317c206c78b7f68d80bad9aec190fda441d997b9f1ea3606ec79d140e
测试跑完后      e337144317c206c78b7f68d80bad9aec190fda441d997b9f1ea3606ec79d140e  ← 未变
```

回滚点（两个，都已逐条比对为内容等价）：
- `instance/backups/baseball_players.backup_20261029_155329.db` —— 提升前
- `instance/backups/baseball_players.backup_20261029_164353.db` —— 提升后、索引前

---

## 9. Database impact

| 表 | 变化 |
|---|---|
| `game_records` | 230 → 240（新增 11 条旧解析漏掉的人次；**0 条消失**；82 条被修正，共 149 处字段） |
| `fielder_profiles` | 27 行不变（内容按新数据重算，漂移 0） |
| `pitcher_profiles` | 27 行不变（内容按新数据重算，漂移 0） |
| `player_positions` | 28 → 29（仇志豪新增「投手」位置 —— 他在 2023-04-01 真有 1 局投球） |
| `players` | 27 行不变；仇志豪 `is_pitcher` 0 → 1（同上），主位置仍是二垒手 |
| 索引 | 新增 5 个 |

不变量复验（迁移后）：`integrity_check ok`、`foreign_key_check 0`、无负值、
`AB ≥ H` 0 例外、`H ≥ 2B+3B+HR` 0 例外、**档案 == SUM(game_records) 漂移 0**。

---

## 10. Security impact

- `app.py` 补 `import re` —— 上传接口从「必然 500」变成可用（**修的是可用性**，
  但也说明这条路径此前**从未被人工走过**，所以配套补了端到端覆盖）。
- 生产配置体检：session cookie 未开 Secure、限流用内存存储时**启动即告警**
  （只告警不阻断 —— 阻断会让「忘了设环境变量」直接变成「服务起不来」）。
- `instance/_verify_writes.py` / `_verify_e2e.py` 加安全闸：默认拒绝执行，
  必须显式 `ALLOW_LEGACY_PROD_WRITE=1` 才跑（旧脚本会**真的写生产库**）。
- `scripts/verify_e2e.py` 是替代品：复制生产库 → 连副本跑完整流程 → 复验生产库
  SHA256 未变 → 删副本。

---

## 11. Backward compatibility

- API 形状未变（`errors_fielding` / `sacrifice_flys` 本来就在返回里，只是值从
  恒为 0 变成真实值）。
- `PUT /api/players` 语义未变（档案字段名 → 400；记录风格字段名 → 200 +
  `ignored_fields` 点名）。
- 数据库 schema 未变（只加索引）。
- `sync_data.py` / `cleanup_db.py` / `migrate_profiles_sqlite.py` 的**命令行用法**
  未变。

---

## 12. Known issues / 未完成

| 项 | 状态 |
|---|---|
| `#33 赛季怎么切` | 待业务方拍板；需要 Game 实体（Phase C） |
| `#11 passed_balls` | 17 份 PDF 里**没有数据源**，保留列但写明「不是真实 0」 |
| `2025-10-25 vs 华北电力大学` 的 PDF **自相矛盾** | 源文件里投手局数之和 1.0，但它的 Totals 行写 1.2 —— 是源数据的问题，不是解析器的问题，已记入待确认项 |
| `2025-11-22 vs 北京交通大学` 的 16 条记录 | 没有对应 PDF，**无法用 PDF 验证**，本阶段原样保留 |
| `尹文浩` | 记分卡上的教练行（0 AB），队里没有这个人 → 跳过且不建球员。若他其实是队员，需要业务方补录 |
| `#16 Service 层` / `#20 Game 实体` / `#23 模板重复` / `#29 多机限流` | 属 Phase C 范围，本阶段未动 |
| `.pre-commit-config.yaml` | **未创建** —— 装 Git 钩子属于「持久化外部工具」，需要你单独点头 |
| `/batch_entry` 真人浏览器点击 | 仍未做（本机无浏览器自动化）；已用 JS 单测 + 端到端 30 项覆盖 |

---

## 13. Git diff summary

见 §14。

## 14. Gate

```text
tests pass                     ✓ 124 passed
test isolation proven          ✓ conftest 守卫生效（测试前后生产库 SHA 未变）
DB fingerprint verified        ✓ 三个指纹均已记录，回滚点已逐条比对
no unexplained diff            ✓ 149 处字段变化逐项对应到 PDF 原文
no unresolved P0               ✓
migration safe                 ✓ 副本先验 + 用户确认 + 原子事务 + 双回滚点
```

**GO**
