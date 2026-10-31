# PHASE R5 REPORT — 指标引擎补完（WHIP 标准口径）+ PDF 页脚污染修复

> 阶段：R5　　日期：2026-10-31　　基线 commit：`6dfa004`
> 上一阶段：[PHASE_R4_REPORT.md](PHASE_R4_REPORT.md)

---

## 1. Objective

把 `FEATURE_PROPOSALS.md` 里的 **F3（指标引擎，唯一公式源）** 收尾：

1. **WHIP 改成标准口径** —— 分母从「投球局数」改成「面对打席数（BF）」
2. **补齐派生率** —— ISO / BABIP / K% / BB% / K-B% / SB% / CS% / K/9 / BB/9
3. 顺带修一个在查 WHIP 分母时暴露出来的**上游数据缺陷**：PDF 页脚把每个
   标签段的最后一条吞掉（17 份 PDF 全中）

不做：schema 变更、Game 实体、公网部署。

## 2. Repository state before work

```
branch: main
HEAD:   6dfa004 docs: 同步 HANDOFF —— CI 首跑结论、新坑与推送方式
生产库: instance/baseball_players.db
SHA256: e337144317c206c78b7f68d80bad9aec190fda441d997b9f1ea3606ec79d140e
数据:   27 球员 / 240 比赛记录（投球 45 / 打击 195）
基线:   pytest 124 passed · node 25 passed · ruff 全绿 · e2e 30/30
```

## 3. Files inspected

```
metrics.py                 指标引擎本体
database.py                档案模型 / 聚合 / to_dict
app.py                     API 层、matchup 序列化、CSV 导出
pdf_parser.py              文本解析层 + extras 标签段切分
pdf_parser_columns.py      列坐标解析器（生产在用）
import_pdfs.py             批量导入（档案重建入口）
templates/stats.html       统计页排行榜（tab + config）
templates/players.html     球员列表表格
static/js/script.js        球员列表渲染
tests/                     现有 14 个测试文件
instance/baseball_players.db  生产库（只读分析 + 副本迁移）
data/*/*.pdf               17 份记分卡 PDF
```

## 4. Findings

### P0 —— 无

### P1-1 · WHIP 分母用错（口径错误，数值离谱）

```
现状（修复前）：WHIP = (被安打 + 保送) / 投球局数
标准口径：      WHIP = (被安打 + 保送) / 面对打席数
```

生产库实测（旧值 → 标准口径）：

| 投手 | 旧 WHIP | 新 WHIP | 说明 |
|---|---|---|---|
| 刘孝宇 | 5.60 | 0.64 | 旧值高出近 9 倍 |
| 吴鸿硕 | 3.56 | 0.56 | |
| 白云箫 | 3.53 | 0.49 | |
| 李昊宇 | 2.67 | 0.47 | |
| 欧阳翦 | 1.86 | 0.35 | |
| 韩登越 | 1.15 | 0.27 | |
| 仇志豪 | 0.00 | 1.00 | 旧公式在他身上反而是 0（投球局数为 0） |

这不是「精度不够」，是**方向性错误**：旧公式里分母是"投了几局"，
分子是"被上了多少垒"，两个量纲不同的东西相除。

### P1-2 · WHIP 的分子分母必须同源

有几场 PDF 没给 BF（详见 P1-3）。若分子用**全部**场次、分母只用**有 BF** 的场次，
分子会多算 → WHIP 反而虚高。实测 5 名投手会算错（例：刘孝宇朴素算法 1.12 vs 限定场次 0.56）。

→ 决定：**WHIP 只统计「有面对打席数」的场次**，分子分母同源。

### P1-3 · PDF 页脚污染：每个标签段的最后一条被静默吞掉（17/17 全中）

记分卡模板最下方印着固定水印：

```
Scorekeeping.  Stats.  Live  Game  Updates.
```

它粘在**最后一个标签段的最后一条**后面：

```
BF: 白云箫 9, 李昊宇 3, 韩登越 11, 仇志豪 4 Scorekeeping. Stats. Live Game Updates.
```

而 `_extract_named_counts_from` 要求整项以数字结尾 → 这条匹配失败 →
掉进「无数字 = 次数 1」的兜底分支 → 变成垃圾键
`{'仇志豪4Scorekeeping.Stats.LiveGameUpdates.': 1}` → **投手的面对打席数凭空为 0**。

实测可恢复 5 条（其余是 PDF 里真的没这一栏）：

| 球员 | 场次 | 漏掉的 BF |
|---|---|---|
| 韩登越 | 2023-04-16 vs 华北电力大学 | 7 |
| 仇志豪 | 2023-04-01 vs 对外经济贸易大学 | 4 |
| 刘孝宇 | 2024-10-20 vs 首都经济贸易大学 | 14 |
| 李昊宇 | 2025-10-18 vs 中国地质大学 | 8 |
| 刘孝宇 | 2025-10-26 vs 首都师范大学 | 5 |

### P2-1 · OPS 二次舍入

`ops()` 收到的是**已舍入**的 OBP 与 SLG（`round(OBP,3) + round(SLG,3)`），
再舍一次入。已修：先算未舍入的 OBP/SLG，相加后只舍一次。

### P2-2 · app.py 里还藏着两份公式拷贝

- `_serialize_batting_matchup_record` 自己算 `round(hits / at_bats, 3)`
- `static/js/script.js` 前端自己算 OPS（还带 console.log 调试输出）

「唯一公式源」的 AST 检查只扫 `* 9 /` 这种 ERA 特征，漏掉了这两处。

### P2-3 · 统计页排行榜的"取哪个值"是一长串三元表达式

`cfg.key === 'x' ? p.x : cfg.key === 'y' ? ... : 0` —— 每加一个指标就多一个分支，
漏一个就**静默排错序**。已改为 `get(p)` 函数。

### P3-1 · 派生率一个都没有

F3 提案里列的 K% / BB% / K-B% / ISO / BABIP / SB% / CS% / K/9 / BB/9 全部缺失。
教练想看「这个人三振率多少」「长打力怎么样」「盗垒成功率」——全查不到。

### P3-2 · 数据自洽性检查（做迁移前的例行体检，结果为**通过**）

```
有 BF 的 44 条记录里，H+BB > BF 的：0 条        ← 没有自相矛盾
BF/IP 偏高的场次：都是 1/3 局的 reliever 登场（1 局面对 5 个打席）← 正常
```

## 5. Changes

| 文件 | 改动 | 原因 |
|---|---|---|
| `metrics.py` | `whip()` 分母改为 BF；新增 `isolated_power` / `babip` / `plate_appearances` / `strikeout_rate` / `walk_rate` / `strikeout_walk_rate` / `stolen_base_rate` / `caught_stealing_rate` / `strikeouts_per_9` / `walks_per_9` / `pitcher_strikeout_walk_rate`；新增 `batting_metrics()` / `pitching_metrics()` 两个汇总入口 | F3 收尾；提案里本来就写明了这两个函数的签名 |
| `metrics.py` | OPS 在 `batting_metrics()` 内只舍入一次 | P2-1 |
| `database.py` | `_accumulate_record` 增记 WHIP 计算基数（只记有 BF 的场次）；`_apply_agg_to_player` 写入 `pp.whip` | P1-2 |
| `database.py` | `PitcherProfile.update_calculated_fields()` 不再算 whip（改注释说明原因） | 档案列没有"哪些场次有 BF"的信息，硬算会退回旧口径 |
| `database.py` | `FielderProfile.update_calculated_fields()` 改走 `batting_metrics()` | P2-1 |
| `database.py` | 新增 `FielderProfile.metrics()` / `PitcherProfile.metrics()`；`Player` 上新增 11 个派生率属性 | P3-1 |
| `database.py` | `Player.to_dict()` 输出全部新指标 | 前端与 CSV 导出都读它 |
| `database.py` | legacy 迁移路径与 `add_sample_data()` 补算 whip | 那两条路径没有 game_records 可依据 |
| `app.py` | `_serialize_batting_matchup_record` 改用 metrics；`_serialize_pitching_matchup_record` 的 WHIP 改 BF 口径并补 K/9、BB/9 | P1-1、P2-2 |
| `app.py` | `/api/stats/batting`、`/api/stats/pitching` 补新指标字段 | P3-1 |
| `pdf_parser.py` | 新增 `_strip_page_footer_text()` / `strip_page_footer_words()` / `is_footer_only_row()`；`_split_tag_sections()` 先清页脚；`_extract_named_counts_from()` 对尾部垃圾容错 | P1-3 |
| `pdf_parser_columns.py` | 逐行截掉页脚词；整行只有页脚的行丢弃 | P1-3 |
| `templates/stats.html` | 排行榜配置改为 `get(p)`；新增打击 6 个 / 投球 3 个 tab；打击榜支持"越低越好"排序 | P2-3、P3-1 |
| `templates/players.html` | 表格新增「上垒率」「长打力 ISO」两列 | P3-1 |
| `static/js/script.js` | 删掉前端自算 OPS 的拷贝与调试日志；渲染新列 | P2-2、P3-1 |
| `scripts/migrate_r5_metrics.py` | 新增：副本迁移 + 报告 + `--apply` 正式迁移（自动备份） | 规范 §25 |
| `tests/test_r5_metrics_engine.py` | 新增 30 个测试 | 覆盖本轮全部改动 |
| `tests/test_r3_metrics_and_import.py` | `test_whip_uses_true_innings` → `test_whip_uses_batters_faced_not_innings` | 旧测试编码的是**已知错误**的口径（审计 B1），必须跟着口径改 |
| `tests/test_stats_baseline.py` | WHIP 测试改用 BF；新增"无 BF 时 WHIP 为 0" | 同上 |

**没有做 schema 变更**：新增的派生率不落库，序列化时算，公式仍全部来自 `metrics.py`。
理由：规范 §24 要求正式迁移用 Alembic/Flask-Migrate，而本项目从未初始化 Alembic
（历史上都是 `scripts/` 手写脚本）。为一个派生率引入第一套 Alembic 不划算，
而"不改 schema"这条路完全走得通 —— 详见 §12。

## 6. Tests added

`tests/test_r5_metrics_engine.py`（30 个）：

```
metrics 纯函数
  WHIP 标准公式 / 无 BF 返回 0 / 与局数无关
  ISO / BABIP / 打席数 / K% / BB% / K-B% / SB% / CS%
  K/9 / BB/9 / 投手 K-B%（按 9 局）
  OPS 只舍入一次（差 0.001 的实证用例）
  batting_metrics() 键齐全 / 全 0 不炸
  pitching_metrics() 取值 / 无 WHIP 基数时为 0

档案层
  WHIP 只统计有 BF 的场次（混合两场的场景）
  profile.whip 可从 game_records 反推（不变量）
  to_dict 暴露打击侧 / 投球侧新指标
  /api/stats/pitching 带新指标

解析器
  尾部垃圾容错 / 无数字项仍是 1 次 / 分段前清页脚
  词级截断 / 整行页脚判定
  3 份真实 PDF 回归（仇志豪 4 / 刘孝宇 14 / 李昊宇 8）
```

## 7. Commands actually executed

```bash
python -m pytest -q                      # 154 passed
node --test 'tests/js/*.test.js'         # 25 passed
ruff check .                             # All checks passed!
python scripts/verify_e2e.py             # 30/30，生产库 SHA256 未变
python scripts/migrate_r5_metrics.py     # 副本迁移 + 迁移报告（生产库未动）
# 解析器前后逐字段比对：17 份 PDF，差异恰好 5 处，全是 batters_faced 0 → 真值
```

## 8. Test result

```
pytest（Python 3.12）  PASS  154 passed（迁移前 124）
node --test             PASS  25 passed
ruff                    PASS  All checks passed!
verify_e2e.py           PASS  30/30
migrate_r5_metrics.py   PASS  副本迁移成功，行数零变化
真实 PDF 解析回归        PASS  17/17，BF 覆盖 41/41
```

## 9. Production DB safety proof

```
迁移前 SHA256   e337144317c206c78b7f68d80bad9aec190fda441d997b9f1ea3606ec79d140e
迁移后 SHA256   f731f13d12397ff9822df4185839c8eedd1de33bb8d7a1947d237409f97d1c9d
备份            instance/baseball_players.pre_r5_20261031_131450.db
                （SHA256 = e3371443…，即迁移前状态，可原样回滚）
```

- 迁移前先在**副本** `instance/_r5_migration.db` 上跑一遍并出报告（规范 §25）。
  副本迁移后的 SHA256 = `f731f13d…` —— 与随后生产库的迁移结果**字节相同**
  （两次独立执行产出同一个库，这是对流程的一次交叉验证）
- 测试库在临时目录，`conftest.py` 的 fail-fast 与 SHA 看门狗全程生效
- `scripts/verify_e2e.py` 自带「生产库未变」断言，迁移后复跑仍通过（30/30）

## 10. Database impact

**迁移已执行**（业务方确认后跑 `--apply`，2026-10-31 13:14）。

```
行数对照
  players                27 →     27
  game_records          240 →    240      ← 零增零减
  fielder_profiles       27 →     27
  pitcher_profiles       27 →     27

BF 覆盖
  迁移前 39/45 条有 BF（缺 6）
  迁移后 44/45 条有 BF（缺 1）   ← 只剩 2025-11-22 那场手录、无 PDF 的记录

完整性
  integrity_check = ok
  foreign_key_check = 0 条
  球员名单零变化（0 新球员、0 未知姓名新建）
  打击档案漂移 0 条
```

**迁移后的 WHIP（逐个从 game_records 反推验证，零偏差）**：

| 投手 | 档案 WHIP | 反推 | 有 BF 的场次 |
|---|---|---|---|
| 仇志豪 | 1.00 | (4+2)/6 | 2/2 |
| 刘孝宇 | 0.64 | (8+20)/44 | 7/7 |
| 吴鸿硕 | 0.56 | (3+12)/27 | 6/7 |
| 李昊宇 | 0.47 | (5+11)/34 | 5/5 |
| 欧阳翦 | 0.35 | (21+5)/74 | 10/10 |
| 白云箫 | 0.49 | (7+13)/41 | 3/3 |
| 韩登越 | 0.27 | (14+14)/105 | 11/11 |

⚠️ 迁移会改写 `game_records` 的行（覆盖模式是删旧写新），因此 **record id 会变**，
但**所有字段值除 5 个 BF 外不变**（解析器前后逐字段比对已证明）。
回滚点：`instance/baseball_players.pre_r5_20261031_131450.db`。


## 11. Security impact

无。本轮不涉及认证、CSRF、上传、密钥。

## 12. Backward compatibility

- **API 只增不改**：`/api/players` 与两个 stats 接口新增字段，旧字段名与含义不变
- **CSV 导出自动多几列**（`to_dict()` 带出来的），列顺序在末尾追加
- **WHIP 数值变**（这是修复，不是回归）—— 旧值 5.60 这类数字不该留着
- 数据库 schema **零变更** → 旧代码读新库不会出错，新代码读旧库也正常
  （只是 WHIP 还是旧值，直到档案重建）
- `metrics.whip()` 的**第三个参数语义变了**（IP → BF）—— 只在项目内部使用，
  已全量替换；外部调用方（本项目没有）需要同步

## 13. Known issues

| # | 问题 | 影响 | 处置 |
|---|---|---|---|
| 1 | ~~生产库尚未迁移~~ | — | ✅ 已迁移（2026-10-31），备份在 `instance/baseball_players.pre_r5_20261031_131450.db` |
| 2 | `2025-11-22` 那场（手录、无 PDF）吴鸿硕的记录没有 BF | 该场不计入 WHIP，吴鸿硕的 WHIP 覆盖 6/7 场 | 已知；UI 里 WHIP 显示为该值，口径在文档里写明 |
| 3 | 规范 §24 要求正式迁移用 Alembic，但项目从未初始化 Alembic | 后续若要加列，仍得先补 Alembic 基建 | 建议列为独立任务（见 HANDOFF 下一步） |
| 4 | 派生率不落库，每次序列化都算 | 27 名单次计算开销可忽略 | 若将来上万人需改 |
| 5 | 统计页 tab 变多（打击 17 / 投球 9） | 视觉上有点挤 | 已用 flex-wrap；可后续做「更多指标」折叠 |

## 14. Git diff summary

```
 app.py                          | +++---
 database.py                     | ++++++++---
 metrics.py                      | +++++++++++++++++++++---
 pdf_parser.py                   | +++++++-
 pdf_parser_columns.py           | +++++-
 static/js/script.js             | +++++-----
 templates/players.html          | ++
 templates/stats.html            | +++++++++++++++++++++---
 tests/test_r3_metrics_and_import.py  | ++++--
 tests/test_stats_baseline.py    | ++++++--
 scripts/migrate_r5_metrics.py   | 新增
 tests/test_r5_metrics_engine.py | 新增
 docs/PHASE_R5_REPORT.md         | 新增
```

## 15. Commit hash

```
（待提交 —— 见提交说明）
```

## 16. Gate

```
GO —— 代码与测试已合并，生产库迁移已完成
```

### 结论

- **代码合并**：GO。测试全绿（154）、ruff 全绿、端到端 30/30。
- **生产库迁移**：GO（2026-10-31 13:14 执行，已备份）。
  副本先验 → 生产库执行 → 两次结果字节相同 → 不变量逐条复验通过。

### 迁移后的复验

```
pytest                154 passed
verify_e2e.py         30/30（生产库 SHA 未变）
integrity_check       ok
foreign_key_check     0 条
WHIP 不变量           7/7 投手可从 game_records 反推，零偏差
打击档案漂移          0 条
```

