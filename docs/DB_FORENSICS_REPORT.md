# Database Forensics Report — Phase E0

> ⚠️ Read-only analysis of `instance/baseball_players.db`. NO DELETE / UPDATE / ALTER performed.

## 1. Row counts

| Table | Rows |
|-------|------|
| players | 27 |
| positions | 9 |
| player_positions | 28 |
| game_records | **230** |
| fielder_profiles | 27 |
| pitcher_profiles | 27 |
| users | 1 |

## 2. Schema — primary keys / foreign keys / unique constraints / indexes

| Table | PK | FK | Unique Constraints | Indexes |
|-------|----|----|--------------------|---------|
| positions | id | — | name (UNIQUE) | auto on name |
| player_positions | (player_id, position_id) | players(id), positions(id) | (composite PK) | sqlite_autoindex |
| players | id | — | — | — ❌ no index on name / jersey_number |
| fielder_profiles | player_id | players(id) | — | — |
| pitcher_profiles | player_id | players(id) | — | — |
| game_records | id | players(id) | — | ❌ **NO index on (player_id, game_date)** |
| users | id | — | username (UNIQUE) | auto on username |

**注意：`players` 表还有 16 个 legacy 累计字段**（at_bats_total / hits_total / ...），
应该是历史遗留。`migrate_legacy_player_stats()` 会把它们清零，但当前数据库里仍然存在。

## 3. Game date range

- Earliest: **2023-04-01**
- Latest: **2025-11-22**
- Total 230 records across 27 players, 13 opponents.

## 4. Duplicate candidates (by `(player_id, game_date, opponent, is_pitching_record)`)

| Player ID | Date | Opponent | Pitching? | Count |
|-----------|------|----------|-----------|-------|
| 28 | 2024-11-16 | 北京交通大学 | batting | **x2** |

**1 个候选组**：球员 ID=28 在 2024-11-16 对阵 北京交通大学 有 2 条 batting 记录。

**可能原因**：
- 重复导入 PDF（baseline bug: API 不去重）
- cleanup_db.py 合并失败残留
- AMBIGUOUS — 需要人工确认（不能自动 DELETE）

## 5. AMBIGUOUS: same player + same day but DIFFERENT opponent (10 groups)

主要集中在 **2024-11-10** 这一天的 10 名球员，每人都出现在 2 个不同对手的比赛中。

**解读**：这强烈暗示 **2024-11-10 是双赛日（doubleheader）** —— 同一球队同一天打两场不同对手。这是合法的比赛场景。

**结论**：在加唯一索引时 `(player_id, game_date, opponent, is_pitching_record)` **不够**，需要更精细的设计（见 STEP 12 Game entity 设计）。

## 6. AMBIGUOUS: same player+day+opponent but DIFFERENT pitching type (39 groups)

39 组"同一球员同一天同一对手既有 batting 记录又有 pitching 记录"。

**解读**：棒球规则允许 — 投手也要打击（除非是美式 AL/DH 规则）。这 39 组都是合法的双重身份记录。

**结论**：唯一索引 **必须**包含 `is_pitching_record`，否则合法数据会被错误拒绝。

## 7. Stats consistency invariant check

```
Total inconsistencies: 0 / 27 players
```

✅ **不变量成立**：`profile.at_bats_total == SUM(GameRecord.at_bats WHERE player_id=?)`
✅ **不变量成立**：`profile.hits_total == SUM(GameRecord.hits WHERE player_id=?)`

**当前数据未漂移**。这是因为 `database.py:sync_stats_from_game_records()` 在每次启动时都会重算，掩盖了入口 1/2 的小 bug。但**入口 4（PUT 直接覆盖）不在这个不变量检查内**，因为它写 profile 而不是写 GameRecord。

## 8. 结论（喂给 STEP 12 Game schema 设计）

| 观察 | 影响 |
|------|------|
| 1 个真实重复候选 (player 28) | 加唯一索引前必须手动清理或标 AMBIGUOUS |
| 10 个双赛日记录 | `Game` 实体必须支持 game_number 字段 |
| 39 个双重身份 (batting+pitching) 记录 | 唯一约束 key 必须包含 `is_pitching_record` |
| 0 个 stats 漂移 | 当前数据健康；但入口 4 (PUT) 可能绕过历史 |
| `players` 表里 legacy 累计列还在 | `migrate_legacy_player_stats` 没清零成功，需要重跑或手动清理 |

## 9. STOP C3 / 暂停唯一索引

**禁止**直接加 `UniqueConstraint(player_id, game_date, opponent, is_pitching_record)`。

理由：
1. 双赛日会产生合法冲突
2. 现有 1 个真重复需要先标 AMBIGUOUS 或删除

正确路径：**先设计 Game 实体**（STEP 12），把 `game_number` / `season` / `venue` 等元数据纳入 Game，GameRecord 通过 `game_id` 关联。

## 10. 保留为 regression 测试

`scripts/db_forensics.py` 应当被纳入 CI（手动触发），作为 invariant check 工具：
- 每次运行都报告 stats 不变量
- 每次报告重复候选数量

任何 Phase C 后的重构不得让这些数字变差。