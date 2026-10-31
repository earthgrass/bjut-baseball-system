# PHASE R6-2026 REPORT — 2026 赛季数据导入 + 对手校名归一 + WHIP 回归修复

> 阶段：R6-2026（2026 赛季数据增量导入）　　日期：2026-10-31
> 基线 commit：`1a23a25`（R5 完成后）　　上一阶段：[PHASE_R5_REPORT.md](PHASE_R5_REPORT.md)

---

## 1. Objective

2026 赛季的 5 份记分卡 PDF 已放进 `data/2026/`，但还没进库。本阶段：

1. **增量导入** 2026 赛季数据（76 条记录 + 4 名新队员），**历史 240 条一字不动**
2. **对手校名归一** —— 2026 的记分卡写「中国公安大学」，历史写「中国人民公安大学」，
   不归一的话对局查询会把它列成两个对手
3. **修掉一个字符映射缺口** —— `⻋`（CJK 部件 U+2ECB）两张映射表都不认，队员名「车佳烨」被解析成「⻋佳烨」
4. **修掉一个我自己引入的 WHIP 回归**（见 §4 P1-2）

## 2. Repository state before work

```
branch: feature/2026-10-31-metrics-engine
HEAD:   1a23a25 docs: R5 阶段报告 + 契约/HANDOFF/README 同步
生产库: instance/baseball_players.db
数据:   27 球员 / 240 比赛记录（2023: 46 · 2024: 91 · 2025: 103）
基线:   pytest 154 passed · node 25 passed · ruff 全绿
新增语料: data/2026/ 5 份 PDF（13:58 放入）
```

## 3. Files inspected

```
data/2026/*.pdf              5 份 2026 记分卡
pdf_parser.py                _CHAR_MAP / _parse_opponent_from_filename
pdf_parser_columns.py        列坐标解析器（对手栏为什么被丢）
import_pdfs.py               import_all_pdfs / PLAYER_NAME_ALIASES
scripts/validate_pdf_parse.py  our_totals()（金标准校验的样板）
scripts/rebuild_stats.py     显式全量重建
database.py                  migrate_legacy_player_stats（启动时跑的 legacy 路径）
```

## 4. Findings

### P1-1 · PDF 页脚之外的第二个静默丢数：**对手校名写法不一致**

实测 2026 的记分卡印的是「中国公安大学」，而 2024 的是「中国人民公安大学」——
**同一所学校**。`game_records.opponent` 是纯字符串，不归一就是两个对手、
历史交手被拆成两段（`/api/matchup/opponents` 会同时列出两个）。

### P1-2 · **我自己引入的 WHIP 回归**（本轮最该记住的一条）

R5 我在 `database.migrate_legacy_player_stats()` 里加了一段：

```python
player.pitcher_profile.whip = whip(
    player.pitcher_profile.hits_allowed_total,   # ← 全部场次的合计
    player.pitcher_profile.walks_allowed_total,  # ← 全部场次的合计
    player.pitcher_profile.batters_faced)         # ← 只累计「有 BF 的场次」
```

**分子分母不同源** —— 这正是 R5 报告里反复强调的"限定场次"规则，我在别处遵守了，
在这里违反了。实测后果：吴鸿硕的 WHIP 被从 **0.56 改成 0.70**。

而且这段代码在 **每次应用启动时都会跑**（`init_db()` → `migrate_legacy_player_stats()`），
所以服务器一启动就把档案里正确的值覆盖掉 —— 我是在核对生产库指纹时才发现的。

> 这条同时暴露了项目的一个隐患：`migrate_legacy_player_stats()` 在启动时**有写库副作用**
> （建 profile、`update_calculated_fields()`、无条件 commit），
> 与 `init_db()` docstring 宣称的"启动只 audit 不改库"并不完全一致（规范 §16）。
> 本轮只修了我引入的那一处，**没有**动这个函数的整体行为 ——
> 那属于"启动时自动修 Stats"的规范问题，建议单独立项。

### P2-1 · `⻋` 两张映射表都不认

```
字符 '⻋' U+2ECB（车部，CJK 部件补充）
NFKC('⻋')      → '⻋'（不分解，NFKC 救不了）
pdf_parser._CHAR_MAP        → 没有
cleanup_db.CJK_RADICAL_MAP  → 没有（那个表是 NFKC 算出来的，只覆盖 2 个能分解的）
```

结果：2026 的队员「车佳烨」在 PDF 里是「⻋佳烨」→ 导入后球员名带部首字符。

### P2-2 · `import_pdfs.py` 只能全量导入

`import_all_pdfs()` 遍历 `data/` 全目录。新增赛季只想增量导入时，
用 `--replace` 会把 22 份 PDF 全部删了重写（**所有 record id 都会变**），
而用默认模式又会把 2026 的新记录当成"重复"跳过（去重键是 日期+对手+球员）。

### P3-1 · 2026 赛季在 5–6 月，与历史赛历不同

历史：4 月（春）+ 10/11 月（秋）。2026：5/16、5/24、5/30、5/31、6/6。
→ 给悬了很久的「赛季怎么切」提供了新证据（B3 阻塞项）。

### P3-2 · 比分数据就在 PDF 里，目前完全没解析

2026 的记分卡第一行印着 `中国公安大学 1 - 13 北京工业大学`。
这是 R6-5c「球队战绩 / 对手报告」要用的素材，现在没人解析。

## 5. Changes

| 文件 | 改动 | 原因 |
|---|---|---|
| `pdf_parser.py` | `_CHAR_MAP` 补 `'⻋': '车'` | P2-1 |
| `pdf_parser.py` | 新增 `OPPONENT_ALIASES` + `_normalize_opponent_name()`，在 `_parse_opponent_from_filename()` 里应用 | P1-1 |
| `import_pdfs.py` | `import_all_pdfs()` 增加 `subdir` 参数；CLI 增加 `--dir 2026` | P2-2 |
| `database.py` | `migrate_legacy_player_stats()` **删掉**我加的那段 WHIP 计算，改为注释说明"为什么不能在这里算" | P1-2 |
| `scripts/migrate_r6_2026.py` | 新增：副本迁移 + 全量重建 + 迁移报告 + `--apply` 自动备份 | 规范 §25 |
| `tests/test_r5_metrics_engine.py` | 新增 2 个回归测试（legacy 路径不得改 WHIP；WHIP 由聚合器独占） | P1-2 |

## 6. Tests added

```
test_legacy_migration_path_does_not_change_whip
    跑一遍启动时的 legacy 迁移路径，WHIP 必须纹丝不动
test_profile_whip_is_owned_by_the_aggregator
    档案 WHIP 必须能从 game_records 反推；档案总计数仍含全部场次
```

> **验证过这个测试真的能挡住 bug**：把 P1-2 的代码装回去，测试立刻变红
> （0.3 → 0.8，与吴鸿硕 0.56 → 0.70 同一类错误）；装回修复版即通过。

## 7. Commands actually executed

```bash
python -m pytest -q                                   # 156 passed（新增 2 个）
ruff check .                                          # All checks passed!
node --test 'tests/js/*.test.js'                      # 25 passed
python scripts/validate_pdf_parse.py                  # 21/22 通过（2026 的 5 份全过）
python scripts/migrate_r6_2026.py                     # 副本迁移 + 报告
```

## 8. Test result

```
pytest（Python 3.12）  PASS  156 passed（迁移前 154）
node --test             PASS  25 passed
ruff                    PASS  All checks passed!
PDF 金标准校验           PASS  21/22（22 份里唯一 FAIL 是 2025-10-25 那份源 PDF 自相矛盾，与本轮无关）
2026 的 5 份 PDF          PASS  打击合计 / 投手局数 / TB 自校验全部吻合 PDF 自己的 Totals 行
```

## 9. Production DB safety proof

```
副本迁移（未写生产库）
  迁移前 SHA256   1df344426dfea8c33448bb253f0dcfed8f6a53ef2c33ca42730045fdefeebac7
  副本后 SHA256   a76f7cc46686d690121e056bfd11a4ddc0133c134afd19ff5e40bd421ff82aec
```

- 导入与重建全程只在**副本** `instance/_r6_2026.db` 上跑
- 生产库在副本验证期间**未被改动**
- 副本验证结论：
  - 240 → 316 条记录（+76 = 63 打击 + 13 投球）
  - 27 → 31 名球员（+4）
  - **2026-01-01 之前的 240 条记录逐字段完全一致**（增量导入没碰历史）
  - `integrity_check` = ok，`foreign_key_check` = 0 条
  - BF 覆盖 44/45 → 57/58

> ✅ **生产库迁移已于 2026-10-31 14:37 执行**（业务方授权后）。
> 回滚点：`instance/baseball_players.pre_r6_20261031_143737.db`。
> 迁移后生产库 SHA `a76f7cc4…` 与副本**字节相同**；
> pytest 156 passed · ruff 全绿 · node 25 passed · verify_e2e 30/30。

## 10. Database impact（2026-10-31 14:37 已执行 --apply）

```
行数      players 27 → 31 · game_records 240 → 316
按赛季    2023: 46 → 46 · 2024: 91 → 91 · 2025: 103 → 103 · 2026: 0 → 76
历史      240 条逐字段完全一致
球员      新增 武庄 / 牛雨卿 / 王艺燃 / 车佳烨；移除 0
完整性    integrity_check ok · foreign_key_check 0
```

**导入的 5 场**：

| 日期 | 对手 | 打击 | 投球 |
|---|---|---|---|
| 2026-05-16 | 北京建筑学院（新对手） | 16 | 1 |
| 2026-05-24 | 中国人民公安大学 | 16 | 2 |
| 2026-05-30 | 中国地质大学 | 11 | 2 |
| 2026-05-31 | 北京物资学院 | 9 | 3 |
| 2026-06-06 | 北京交通大学 | 11 | 5 |

**档案 WHIP 变化**（旧 → 新）：

| 投手 | 旧 | 新 | 说明 |
|---|---|---|---|
| 吴鸿硕 | 0.70 | **0.56** | 修掉 P1-2 回归（0.70 是错值） |
| 刘孝宇 | 0.64 | 0.61 | 2026 数据并入 |
| 李昊宇 | 0.47 | 0.49 | 2026 数据并入 |
| 欧阳翦 | 0.35 | 0.36 | 2026 数据并入 |
| 杨润琦 | 0.00 | **0.57** | 2026 新数据 |
| 黄钰洲 | 0.00 | 0.00 | 只有 0.67 局，样本太小 |
| 仇志豪 / 白云箫 / 韩登越 | 1.00 / 0.49 / 0.27 | 不变 | — |

## 11. Security impact

- 新增的图片上传能力**不在本阶段**（在 R6-2 的规划里）
- 对手校名归一只影响统计口径，不涉及权限
- 新增的 `role` / `student_id` 等列**不在本阶段**（R6-1 / R6-2）
- 无认证、CSRF、上传面变化

## 12. Backward compatibility

- **API 无变化**（本轮只改解析与导入，不动端点）
- 数据库 schema **无变化**（只加数据，不加列）—— 这也是本轮能安全做增量导入的前提
- 解析器行为变化：对手名多了归一、队员名多了 `⻋→车`
- `import_pdfs.py` 新增 `--dir` 参数，**默认行为不变**（不加参数仍全量导入）
- `metrics.py` 未改

## 13. Known issues

| # | 问题 | 影响 | 处置 |
|---|---|---|---|
| 1 | 生产库迁移未执行 | 网页上看不到 2026 数据；吴鸿硕的 WHIP 仍是错值 0.70 | 跑 `python scripts/migrate_r6_2026.py --apply` |
| 2 | `2025-11-22` 那场（手录、无 PDF）吴鸿硕的记录仍没有 BF | 该场不计入 WHIP，吴鸿硕的 WHIP 覆盖 6/7 场 | 已知；口径在 API_CONTRACT 写明 |
| 3 | `migrate_legacy_player_stats()` 启动时仍有写库副作用 | 与规范 §16「禁止启动自动修 Stats」不完全一致 | 本轮只修了我引入的那处；整体行为建议单独立项 |
| 4 | 2026 的 5 场里，"中国公安大学"归一后与 2024 的合并 | 同一对手的历史交手现在是连着的（这是想要的） | 已在 API_CONTRACT 与本报告写明 |
| 5 | 比分数据仍未解析 | 球队战绩暂时做不了 | R6-5c 的任务 |

## 14. Git diff summary

```
 pdf_parser.py                 | ++++-      U+2ECB 映射 + 对手名归一
 import_pdfs.py                | ++++       --dir 支持
 database.py                   | +++-       删掉 legacy 路径里的错误 WHIP 计算
 scripts/migrate_r6_2026.py    | 新增       副本迁移 + 重建 + 报告
 tests/test_r5_metrics_engine.py | +++     2 个回归测试
 docs/PHASE_R6_2026_REPORT.md  | 新增
 docs/FEATURE_PLAN_R6.md       | 新增       新增功能规划（给学弟的实现说明书）
```

## 15. Commit hash

```
（见提交说明）
```

## 16. Gate

```
GO —— 代码与测试可以合并
GO —— 生产库迁移已执行并通过迁移后验证
```

### 结论

- **代码合并**：GO。156 passed、ruff 全绿、PDF 金标准校验 21/22（唯一 FAIL 与本轮无关）。
- **生产库迁移**：已执行（2026-10-31 14:37）。历史 240 条逐字段一致、完整性 ok、
  球员名单只增不减；迁移后 pytest 156 passed、ruff 全绿、node 25 passed、端到端 30/30。

---

## 附 · 与《新增功能规划（R6）》的关系

本阶段的三个发现直接喂给了 `docs/FEATURE_PLAN_R6.md`：

| 发现 | 落到规划里的哪一条 |
|---|---|
| 对手球员数据在 PDF 里全有（只是被丢弃） | R6-5 的可行性依据（已实测 17/17 份都能解析） |
| 对手姓名的「名姓反序」 | **阻塞项 B1**（不解决不落库） |
| 2026 赛季在 5–6 月 | 阻塞项 B3（赛季怎么切）的新证据 |
| 比分数据在 PDF 里 | R6-5c 的素材来源 |
