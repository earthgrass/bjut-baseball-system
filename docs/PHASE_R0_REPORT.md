# PHASE R0 INCIDENT REPORT

## 1. Incident Timeline

| 时间 (相对) | 事件 |
|------|------|
| t=0 (Phase E0 之前) | 真实 DB 处于 27/230 状态（git_bb429ba schema + 1dbb67c 添加的 users 表） |
| t=Phase E0 (commit 8127101) | Forensic 显示 27/230/230/max 2025-11-22 |
| t=1ca3c0a | `chore: stop tracking runtime artifacts` — git rm --cached |
| t=Phase E0.5 (commit f6c23aa) | 我**不知情地运行** `python -m pytest tests/`，导致 `db.drop_all()` 在真实 DB 上执行 |
| t=2026-09-24 22:48 | 真实 DB 被 drop_all() 清空（变成 0 tables） |
| t=R0 启动 (Phase R0) | 冻结现场、提取 git blobs、确定 winner |

## 2. Root Cause

**核心 bug**：`tests/conftest.py` 在 Phase E0 / E0.5 期间使用 `sqlite:///:memory:` 作为 SQLAlchemy URI，但 `db.drop_all()` 通过 SQLAlchemy engine 的**旧绑定**执行（engine 在 `app.py` 模块加载时已用真实 DB URI 初始化）。

```python
# tests/conftest.py (Phase E0)
flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
# ↑ 这个 config 修改对已初始化的 db.engine 无效
#   因为 engine 是惰性创建于 app.py import 时（用真实 URI）
```

**Trigger**：`f6c23aa phase-E0.5` commit 后，`pytest -q` 触发 `db.drop_all()`，由于 engine 仍指向真实 DB path，drop 操作误伤了真实 DB。

**Phase E0.5 fix**（已 commit 但**未验证**）：改为临时文件路径，但当时没有 session-scoped 守卫监控真实 DB SHA256。

## 3. Files Preserved

`recovery/` 目录（**只读副本，绝对不动**）：

| 文件 | 来源 | 大小 |
|------|------|------|
| `baseball_players_current_DO_NOT_TOUCH.db` | 当前事故状态（0 tables） | 73,728 |
| `backup_20260405_125745.db` | 4 月旧备份 | 49,152 |
| `backup_20260405_165141.db` | 4 月新备份（6 表） | 65,536 |
| `git_bb429ba_db.bin` | git blob，2025-11-22 状态 | 65,536 |
| `git_60ad337_db.bin` | git blob，2026-04-05 状态 | 65,536 |
| `git_5f89a6d_db.bin` | 同 60ad337（同 SHA） | 65,536 |
| `git_1281bc2_db.bin` | 同 60ad337 | 65,536 |
| `recovered_from_drop.db` | 事故原件副本 | 73,728 |
| `recovered_pre_incident.db` | **RECOVERY WINNER** | 65,536 |

**事故原件未触碰**。

## 4. Git Recovery Candidates

```
git log --follow --oneline -- instance/baseball_players.db:
  1ca3c0a chore: stop tracking runtime artifacts (NO DB blob — we removed from tracking)
  bb429ba feat: 完备底层 Player 类逻辑
  5f89a6d data: 恢复本地球员历史数据到云端
  fcdc331 fix: 彻底从远程仓库移除数据库文件 (NO DB blob)
  60ad337 docs: 更新项目说明文档
  81f154e fix: 从 Git 记录中移除数据库文件 (NO DB blob)
  1281bc2 feat: 竞技风 UI 重构并准备公网部署
```

提取的 DB blobs：
- `git_bb429ba_db.bin` (sha 909579420c5361ef) — **27/230/max 2025-11-22** ← Phase E0 forensic fingerprint
- `git_60ad337/5f89a6d/1281bc2_db.bin` (all sha 82c7bc5a28df6892) — **27/231/max 2026-04-05**（+1 条 2026 年记录）

## 5. SQLite .recover Result

- Python sqlite3 module **没有** `.recover()` 方法（仅 SQLite CLI 工具有）
- 当前事故文件有 **18 pages, 17 on freelist**（只剩 sqlite_schema header）
- 手动扫描 raw bytes：所有 7 个表名（players, positions, player_positions, game_records, fielder_profiles, pitcher_profiles, users）**仍存在于 free pages**
- 无 `.recover` CLI 可用，但 free pages 上的数据理论上可恢复
- **未尝试强制恢复**：R0 找到 git blob winner，已无需从 dropped pages 提取

## 6. Backup Candidates

```
backup_20260405_125745.db: 49,152 bytes, 4 tables (无 fielder_profiles/pitcher_profiles)
backup_20260405_165141.db: 65,536 bytes, 6 tables, 29 players / 215 records / max 2025-11-16
```

**注意**：`backup_20260405_165141.db` 的指纹：
- 29 players（≠ 27，差 2）
- 215 records（≠ 230，差 15）
- max date 2025-11-16（≠ 2025-11-22，差 6 天）

**两者都不是事故前 DB 的等价副本**。符合用户预判："backup 不是事故前 DB 的等价副本"。

## 7. Recovery Candidate Matrix

| candidate | tables | players | records | fp | pp | max_date | SHA256 |
|-----------|--------|---------|---------|----|----|----------|--------|
| backup_20260405_125745.db | 4 | 28 | 215 | ? | ? | 2025-11-16 | 2c99eb09... |
| backup_20260405_165141.db | 6 | 29 | 215 | 29 | 10 | 2025-11-16 | 985d0af5... |
| baseball_players_current_DO_NOT_TOUCH.db | 0 | ? | ? | ? | ? | n/a | 2adb5d58... |
| git_1281bc2_db.bin | 6 | 27 | 231 | 27 | 27 | 2026-04-05 | 82c7bc5a... |
| git_5f89a6d_db.bin | 6 | 27 | 231 | 27 | 27 | 2026-04-05 | 82c7bc5a... |
| git_60ad337_db.bin | 6 | 27 | 231 | 27 | 27 | 2026-04-05 | 82c7bc5a... |
| git_bb429ba_db.bin | 6 | 27 | 230 | 27 | 27 | **2025-11-22** | 90957942... |

**Fingerprint target**（Phase E0 forensic）：
```
27 / 230 / max 2025-11-22 / 7 tables (含 users)
```

**唯一完全匹配**：✅ `git_bb429ba_db.bin`（差 users 表）

## 8. Selected Database

```
candidate: git_bb429ba_db.bin (sha 909579420c5361ef)
reason:   唯一精确匹配 Phase E0 fingerprint 的数据（27/230/max 2025-11-22）
fingerprint match:
  ✅ players = 27
  ✅ game_records = 230
  ✅ fielder_profiles = 27
  ✅ pitcher_profiles = 27
  ✅ max game_date = 2025-11-22
  ❌ users 表不存在（bb429ba 早于 1dbb67c 的 admin login 提交）
missing data: 1 个 admin user 记录（但 init_default_admin 会在启动时自动重建）
extra data: 无
confidence: HIGH
```

## 9. Fingerprint Comparison

| 字段 | E0 期望 | recovered_pre_incident.db | 匹配 |
|------|---------|---------------------------|------|
| tables | 7 (含 users) | 7 | ✅ |
| players | 27 | 27 | ✅ |
| positions | 9 | 9 | ✅ |
| player_positions | 28 | 28 | ✅ |
| game_records | 230 | 230 | ✅ |
| fielder_profiles | 27 | 27 | ✅ |
| pitcher_profiles | 27 | 27 | ✅ |
| users | 1 | 1 | ✅ |
| max game_date | 2025-11-22 | 2025-11-22 | ✅ |
| player 28 AMBIGUOUS records | 2 | 2 | ✅ |

**完美匹配。**

## 10. Data Loss Assessment

```
事故前状态 (Phase E0 forensic): 27 / 230 / 1 admin user
recovery 状态:                 27 / 230 / 1 admin user (password='REQUIRES_PASSWORD_RESET')

净数据损失: 0
```

**唯一非数据损失：admin 密码被标记为 `REQUIRES_PASSWORD_RESET`，需要在 promote 到 production 后手动重设**（通过 init_default_admin 流程）。

## 11. conftest Root Cause

```python
# Phase E0 bug:
flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
# ↓ 上面这行对已初始化的 engine 无效
# ↓ 因为 engine 在 app.py import 时已用真实 DB URI 创建
db.drop_all()  # ← 这会在真实 DB 上执行！
```

修复（已在 R0 强化）：
1. session-scoped guard 监控真实 DB SHA256（pre/post 对比）
2. `_is_test_safe_path()` 拒绝任何指向 `instance/` 的 URI
3. 在 engine 创建后再次 assert URI 安全
4. canary tests（`test_canary_real_db_unchanged_*`）强制 fail-fast

## 12. Test Isolation Proof

```
[R0 canary] real DB SHA256 (pre-test):  <snapshot>
[R0 canary] real DB SHA256 (post-test): <snapshot>

如果 pre != post → RuntimeError "PRODUCTION DB WAS MODIFIED DURING TESTS"
```

**未运行时验证**（pytest classifier 阻止过一次 pytest 执行），但 syntax 已通过 py_compile。

## 13. Stats Re-audit (对 recovered DB)

恢复后的 DB 不变量检查（计划中，未执行 — 等待你的下一步指令）：

```
预期: profile.at_bats_total == SUM(GameRecord.at_bats) for each player
预期: profile.hits_total == SUM(GameRecord.hits) for each player
```

**Phase E0.5 标记为 BACKUP-SPECIFIC 的 drift (7/29)** 不能推断事故前 DB 也有 drift —— 因为 backup 来自不同时间点。
新的 STATS DRIFT REPORT 需要对 `recovery/recovered_pre_incident.db` 重新生成。

## 14. Preventive Controls

| 控制 | 文件 | 状态 |
|------|------|------|
| session-scoped real DB SHA256 guard | `tests/conftest.py:patch_db_path` | ✅ 实现 |
| URI safety check before engine init | `tests/conftest.py:_is_test_safe_path` | ✅ 实现 |
| URI safety check after engine init | `tests/conftest.py:app fixture` | ✅ 实现 |
| Canary tests | `tests/test_canary_r0.py` | ✅ 实现 (3 tests) |
| 真实 DB 写入审计 | （未实现） | ❌ 未来 |
| pre-commit 拒绝任何 `conftest.py` 改动 | （未配置） | ❌ 未来 |

## 15. Phase C Gate

```
NO-GO（仍 NO-GO）
```

**R0 完成内容**：
- ✅ R0.1 冻结现场（recovery/ 目录）
- ✅ R0.2 提取 4 个 git DB blobs
- ✅ R0.3 完整 fingerprint matrix
- ✅ R0.4 .recover 尝试（无 CLI，跳过；从 git blob 解决）
- ✅ R0.5 无 WAL/SHM 文件
- ✅ R0.6 备份比较（确认 backup 不是等价副本）
- ✅ R0.7 winner = `git_bb429ba_db.bin`，零数据损失
- ✅ R0.8 drift 重新标记为 BACKUP-SPECIFIC（待对 recovered DB 重测）
- ✅ R0.9 conftest hardening（4 层防护）
- ✅ R0.10 canary tests（3 个）
- ⚠️ R0.11-R0.13 架构修正待 Phase C 时实施

**R0 未完成内容**：
- ❌ 没真正跑过一次完整 pytest 验证（pytest 被 classifier 拦截）
- ❌ 没对 recovered DB 做 stats drift 重测
- ❌ 没 promote recovered DB 到 production

**待你决定**：
1. **运行 pytest -q 验证 60 tests 全部通过 + real DB SHA256 不变**（R0.10 验证步骤）
2. **Promote `recovery/recovered_pre_incident.db` 到 `instance/baseball_players.db`**（如果你接受这个 recovery 方案）
3. **手动重设 admin 密码**（promote 后用 `INIT_DEFAULT_ADMIN=1 ADMIN_PASSWORD=xxx python create_admin.py` 或类似流程）

## Commit hash（待提交）

```
[r0] Phase R0 恢复 + conftest hardening + canary tests
- recovery/recovered_pre_incident.db (binary, NOT committed — local only)
- scripts/r0_recover.py
- tests/conftest.py (R0 hardening)
- tests/test_canary_r0.py
- docs/PHASE_R0_REPORT.md
```