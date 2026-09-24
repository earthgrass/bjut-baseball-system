# Statistics Write Path Report — Phase E0

> Phase C 重构前必须先理解当前所有"统计写入"入口。

## 入口 1：app.py:add_game_record() (line ~700)

**触发路径**：`POST /api/game_records` → `@admin_required`

**修改字段**（野手）：
- `player.doubles / .triples / .home_runs_batting / .hit_by_pitch / .stolen_bases / .caught_stealing / .sacrifice_flys / .sacrifice_hits / .total_bases / .at_bats_total / .runs_total / .hits_total / .rbi_total / .walks_total / .strikeouts_batting_total`

**修改字段**（投手）：
- `player.pitches / .strikes / .hit_by_pitch_allowed / .batters_faced / .innings_pitched_total / .hits_allowed_total / .runs_allowed_total / .earned_runs_total / .walks_allowed_total / .strikeouts_total / .home_runs_allowed_total`

**然后**：`player.update_calculated_fields()`

**commit**：`db.session.commit()` (line 789)

**风险**：30 行 inline 修改，复制粘贴容易出错；重复添加无去重。

## 入口 2：import_pdfs.py:import_game_record() (line ~100)

**触发路径**：`POST /api/pdf/import_one` 或 `POST /api/pdf/import_all` 或批量 CLI

**修改字段**：野手子集（at_bats/runs/hits/rbi/walks/strikeouts_batting_total/doubles/triples/home_runs_batting/total_bases/stolen_bases/caught_stealing/hit_by_pitch/sacrifice_flys/sacrifice_hits）

投手子集（innings_pitched/hits_allowed/runs_allowed/earned_runs/walks_allowed/strikeouts/home_runs_allowed/pitches/strikes/hit_by_pitch_allowed/batters_faced）

**去重**：按 `GameRecord.query.filter_by(player_id, game_date, opponent, is_pitching_record)` 查重，重复则跳过
**commit**：`db.session.commit()` (line 240)

**风险**：与入口 1 的字段列表**略有不同**——入口 1 还更新 `doubles/triples` 等子字段，入口 2 也更新 `doubles/triples`，但顺序与命名差异。**这是数据漂移的潜在源头**。

## 入口 3：database.py:sync_stats_from_game_records() (line ~502)

**触发路径**：`init_db()` 在每次启动时被调用（line 622）

**修改字段**：全量重算所有球员的 FielderProfile / PitcherProfile（按 GameRecord 聚合）
**commit**：`db.session.commit()` (line 610)

**用途**：修复历史漂移；但每次启动都跑，如果入口 1/2 累计有 bug，启动时会被这个全量重算掩盖。

**风险**：⚠️ **每次启动重写球员累计**。如果 GameRecord 里有重复数据（见 STEP 10 forensic），这个函数会按"重复"累加，导致 stats 系统性偏高。

## 入口 4：app.py:update_player() PUT (line ~370)

**触发路径**：`PUT /api/players/<id>` → `@admin_required`

**修改字段**：直接覆盖 `at_bats_total / hits_total / rbi_total / ...` 共 16 个打击字段 + 12 个投手字段
**commit**：`db.session.commit()` (line 442)

**风险**：⚠️ **直接覆盖**而非累加。这条路径绕过 GameRecord，与 1/2/3 的 GameRecord 聚合逻辑独立。**这是历史漂移的另一个源头**。

## 入口 5：app.py:delete_game_record() (line ~1485)

**触发路径**：`DELETE /api/matchup/game_record/<id>` → `@admin_required`

**修改字段**：反向扣减（用 `safe_subtract`，max(0, x)）
**commit**：`db.session.commit()` (line 1565)

**风险**：`safe_subtract` 掩盖真实 bug；如果之前已漂移，反向扣减可能不准。

## 入口 6：database.py:init_db() → add_sample_data() (line 622, 837)

**触发路径**：开发模式 `INIT_SAMPLE_DATA=1` 时（目前未设此 env，永远不触发）

**修改字段**：随机数填球员 profile
**commit**：`db.session.commit()` (line 866)

**风险**：当前默认 `INIT_DEFAULT_ADMIN` 才生效，`INIT_SAMPLE_DATA` 未实现，所以这个入口**当前不会被生产环境触发**。但代码还在，潜在风险。

## 入口 7：database.py:init_db() → migrate_legacy_player_stats() (line 619)

**触发路径**：每次启动

**行为**：把旧 `players` 表里的累计列迁移到 FielderProfile/PitcherProfile，**仅当 profile 为空时迁移**，然后清零旧列。
**commit**：多次 commit

**风险**：旧数据迁移完成后清零 legacy 列；新代码不再写 legacy 列，OK。

## 入口 8：app.py:create_admin.py? 不，没有这入口。create_admin.py 是 CLI 脚本

## 入口 9：cleanup_db.py（一次性 CLI）

**触发**：手动运行 `python cleanup_db.py`
**行为**：合并重复球员、重算统计

## 入口 10：sync_data.py（一次性 CLI）

**触发**：手动运行 `python sync_data.py`
**行为**：从 GameRecord 重新聚合所有球员统计（与入口 3 同义，但实现细节略不同）

---

## 调用链风险矩阵

| 风险维度 | 现状 |
|----------|------|
| 累加逻辑重复 | 4 处（入口 1/2/3/4 各自独立实现） |
| 单一真实源 | ❌ 不存在：GameRecord 写路径多，FielderProfile/PitcherProfile 是"应该一致"的缓存 |
| 启动自愈 | ✅ 入口 3 会从 GameRecord 重算，但**如果 GameRecord 本身有重复**，会重算错误 |
| 重复数据容忍 | ❌ 入口 2 去重，但入口 1（API）不去重 |
| 直接覆盖路径 | 入口 4 绕过 GameRecord |
| 删除反推准确性 | 入口 5 用 safe_subtract，假设 GameRecord 字段非空 |
| 数据漂移检测 | 无 — 没有 invariant check 工具 |

## Phase C 重构后目标（不变，仅设计）

```
GameRecord (canonical)
    │
    │  Service: GameRecordService.apply(record)
    ▼
FielderProfile / PitcherProfile (derived cache)
    │
    │  Service: StatsService.rebuild(player_id)
    │           StatsService.rebuild_all()
    ▼
all read paths always read from profiles
    │
    ▼
handles 1 write path: GameRecordService.apply
handles 1 rebuild path: StatsService.rebuild_all (called on demand)
```

**关键不变量**：
- `FielderProfile.at_bats_total = sum(GameRecord.at_bats for player)`
- 任何字段修改必须通过 `GameRecordService`，不允许 PUT 端点直接覆盖 profile 字段

**实现步骤**：
1. **暂停入口 4 的 profile 直接覆盖能力**（PUT 端点改为只允许 name/jersey/positions 修改）
2. **暂停入口 1 的 inline 累加**，改为调 `Player.apply_game_record(record)`
3. **暂停入口 5 的 safe_subtract**，改为调 `Player.reverse_game_record(record)`
4. **保留入口 3 / 10 作为 rebuild 工具**，加 `rebuild_all_stats()` 入口给运维用
5. **暂停入口 2 的重复累加**，复用 `Player.apply_game_record`
6. 加 invariant check：每次启动或 rebuild 后跑 `assert profile.at_bats_total == sum(GameRecord.at_bats for player_id)`

**禁止**：
- 在不知道 GameRecord 是否干净的情况下加 unique constraint（STEP 10 forensic 必须先做）

## 已知 Baseline Bug 候选（待 STEP 7 测试验证）

1. 入口 1（API 添加记录）无去重 — `tests/test_game_records_baseline.py::test_duplicate_records_allowed`
2. 入口 4（PUT 直接覆盖）可绕过 GameRecord 历史
3. `win / loss / save` 仅在 GameRecord 里，Player 没有累计
4. `wild_pitches` 字段在 PitcherProfile 但 GameRecord 写入路径不更新它（line 752 漏了）