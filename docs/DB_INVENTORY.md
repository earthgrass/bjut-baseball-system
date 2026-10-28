# 数据库文件全量盘点（DB Inventory）

> **只读盘点报告** — 生成日期：2026-10-28
> 所有数据库均以 `sqlite3.connect('file:<abs>?mode=ro', uri=True)` **只读模式**打开。
> 本次盘点**未执行任何** DELETE / UPDATE / ALTER / VACUUM / DROP，**未创建**任何 `-wal` / `-shm` 伴随文件。
> 盘点期间未修改或删除任何既有文件（本文档为唯一新增文件）。

---

## 0. 一句话回答

> **现有数据库在 `instance/baseball_players.db`（73,728 字节）。**
> **磁盘上一共存在 16 个 SQLite 数据库文件，但它们只有 8 份不同的内容（按 SHA256 去重）。**
> 其余 15 个全部是备份 / 取证副本 / 探针临时产物，**没有任何一个被应用运行时使用**。

---

## 1. 扫描方法与覆盖面

| 扫描手段 | 命令 / 方式 | 结果 |
|---|---|---|
| Git 索引 | `git ls-files` | 0 个数据库文件被跟踪（详见 §5） |
| Git 全历史 | `git log --all --name-status -- "instance/*.db"` | 3 个文件历史上曾被跟踪（详见 §5.3） |
| 扩展名匹配 | `find . -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db-journal" -o -name "*.db-wal" -o -name "*.db-shm" -o -name "*.sqlite-journal" -o -name "*.sqlite-wal" -o -name "*.sqlite-shm" -o -name "*.bin" \)`（排除 `.git/`） | 16 个 |
| **魔术字节嗅探（不依赖扩展名）** | 遍历全部非 `.git/` 文件，读取前 15 字节匹配 `SQLite format 3\0` | 16 个，**与扩展名扫描完全一致 → 无隐藏/无扩展名 DB 漏网** |
| WAL / SHM / journal 旁路文件 | `find . -name "*-wal" -o -name "*-shm" -o -name "*-journal"` | **0 个**（无 WAL 模式遗留，无需 checkpoint） |
| 覆盖范围 | 根目录、`instance/`、`recovery/`、`data/`、`scripts/`、`tests/`、`.claude/`、`.pytest_cache/`、`__pycache__/` | 全部已扫 |

**结论：没有遗漏。** 魔术字节扫描是权威依据 —— 它能发现任何没有 `.db`/`.sqlite` 扩展名的 SQLite 文件
（例如 `recovery/git_*_db.bin`），且结果与扩展名扫描逐一吻合。

---

## 2. 当前活跃数据库是哪个（`app.py` 解析链）

### 2.1 定义逻辑

`app.py:84-103`：

```python
# 数据库文件位置：默认 instance/baseball_players.db，可用 DATABASE_FILE 覆盖。
#   - 绝对路径 → 直接使用（测试隔离、临时库、外部挂载的持久化目录）
#   - 相对路径 → 相对于 instance/ 解析
#
# 为什么必须在 init_app 之前决定：Flask-SQLAlchemy 在 init_app() 里就 eagerly 创建
# engine，之后再改 app.config['SQLALCHEMY_DATABASE_URI'] 不会生效（官方文档明确写了
# "Changes to application config after this call will not be reflected"）。
# 早期版本的 tests/conftest.py 正是在 import 之后才覆盖 URI，导致 db.drop_all()
# 打在了真实生产库上（Phase E0.5 数据事故）。
_db_override = os.environ.get('DATABASE_FILE', '').strip()
if _db_override:
    DATABASE_FILE = (_db_override if os.path.isabs(_db_override)
                     else os.path.join(app.instance_path, _db_override))
else:
    DATABASE_FILE = os.path.join(app.instance_path, 'baseball_players.db')

_app_config = get_config()
app.config.from_object(_app_config)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_FILE}'
```

### 2.2 优先级链（从高到低）

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | **进程环境变量 `DATABASE_FILE`** | 绝对路径 → 原样使用；相对路径 → 相对 `instance/` 解析 |
| 2 | **`.env` 文件中的 `DATABASE_FILE`** | `app.py:11-15` 用 `load_dotenv(PROJECT_ROOT/.env)` 加载。**注意 `load_dotenv` 默认 `override=False`**，所以真实 shell / CI 里已存在的同名环境变量**优先于** `.env` |
| 3 | **代码默认值** | `os.path.join(app.instance_path, 'baseball_players.db')` → `instance/baseball_players.db` |
| — | `config.py` | **不参与**。`Config` / `ProductionConfig` / `TestingConfig` / `DevelopmentConfig` 都**没有** `SQLALCHEMY_DATABASE_URI` 字段；URI 由 `app.py:103` 在 `from_object()` **之后**无条件覆盖 |

`app.instance_path` = Flask 自动推导 = `<项目根>/instance`。

### 2.3 `.env` 实际把它指向了哪里

`.env`（第 10 行，已被 `.gitignore:7` 排除，未提交）：

```
# 数据库
DATABASE_FILE=baseball_players.db
```

实测（只读解析）：

```
DATABASE_FILE env = 'baseball_players.db'
isabs = False
```

→ 走**相对路径分支** → `os.path.join(app.instance_path, 'baseball_players.db')`
→ **`C:\Users\earthgrass73\Desktop\北工大棒球队管理系统\instance\baseball_players.db`**

### 2.4 结论

| 项 | 值 |
|---|---|
| **当前活跃库** | `instance/baseball_players.db` |
| **默认路径（无 env）** | `instance/baseball_players.db`（与 `.env` 解析结果**一致**，两条路径殊途同归） |
| **环境变量优先级** | 真实环境变量 > `.env` > 代码默认值 |
| **当前库指纹** | 7 张表 / players=27 / game_records=230 / users=1 / 日期区间 2023-04-01 → 2025-11-22 |
| **状态** | ✅ 与 Phase E0 取证指纹、Phase R0 恢复 winner **完全一致** —— 已从恢复库还原并投入运行（README 第 438 行确认） |
| **Docker 部署** | `docker-compose.yml` 把 `./instance:/app/instance` 挂载进容器 → 容器内外同一个库文件 |
| **测试隔离** | `tests/conftest.py:81` 在 `import app` **之前**设 `os.environ['DATABASE_FILE'] = _TMP_DB_PATH`，测试跑在临时目录的库上，**不碰 `instance/`** |

---

## 3. 三类（实为四类）文件分类

| 类别 | 含义 | 数量 | 位置 |
|---|---|---|---|
| **(a) 当前活跃库** | app 运行时真正打开的库 | **1** | `instance/baseball_players.db` |
| **(b) 事故恢复 / 取证副本** | Phase R0 冻结现场，禁止改动 | **10** | `recovery/` 整个目录 |
| **(c) 冗余旧备份** | 2026-04-05 的旧备份 + 事故空库快照 | **3** | `instance/baseball_players.backup_*.db` |
| **(d) 探针临时产物** | 调试脚本留下的库副本（非备份） | **2** | `instance/_perf.db`、`instance/_scratch_probe.db` |
| | **合计** | **16** | 合计 1,081,344 字节（1.03 MiB） |

### (b) 事故恢复目录的细分（10 个）

| 子类 | 文件 | 数量 | 来源 / 事故状态 |
|---|---|---|---|
| **事故原件**（0 表，drop_all() 后的空壳） | `recovery/baseball_players_current_DO_NOT_TOUCH.db` | 1 | 2026-09-24 22:48 事故现场冻结快照。18 页中 17 页在 freelist，只剩 `sqlite_schema` 空壳 |
| 事故原件副本 | `recovery/recovered_from_drop.db` | 1 | 上述空壳的副本，SHA 与原件**完全相同** |
| 事故原件副本 | `instance/baseball_players.backup_incident_empty.db` | 1 | 同上，第三个副本（放在 `instance/`，易被误认为备份） |
| **Git blob 提取** | `recovery/git_1281bc2_db.bin` | 1 | commit `1281bc2` "feat: 竞技风 UI 重构并准备公网部署" 的 `instance/baseball_players.db` blob |
| | `recovery/git_5f89a6d_db.bin` | 1 | commit `5f89a6d` "data: 恢复本地球员历史数据到云端" 的 blob |
| | `recovery/git_60ad337_db.bin` | 1 | commit `60ad337` "docs: 更新项目说明文档" 的 blob |
| | `recovery/git_bb429ba_db.bin` | 1 | commit `bb429ba` "feat: 完备底层 Player 类逻辑…" 的 blob —— **R0 选定的恢复源** |
| 旧备份副本 | `recovery/backup_20260405_125745.db` | 1 | `instance/` 下同名备份的副本 |
| | `recovery/backup_20260405_165141.db` | 1 | 同上 |
| **R0 恢复产物** | `recovery/recovered_pre_incident.db` | 1 | `scripts/r0_recover.py` 输出 = `git_bb429ba_db.bin` + 新建 `users` 表 + admin（`REQUIRES_PASSWORD_RESET`） |
| 测试安全快照 | `recovery/_pre_pytest_backup.db` | 1 | pytest 前对生产库的字节级快照（SHA 与当前活跃库**完全相同**） |

---

## 4. 逐文件明细

### 4.1 汇总表

| # | 路径 | 大小(字节) | 状态 | 表数 | 关键行数 | SHA256 前 16 位 |
|---|---|---|---|---|---|---|
| 1 | `instance/baseball_players.db` | 73,728 | **(a) 活库** | 7 | players=27, game_records=230, users=1, max=2025-11-22 | `7e7408f6c3e1575d` |
| 2 | `instance/_perf.db` | 73,728 | (d) 探针产物 · 与 #1 **字节相同** | 7 | 同 #1 | `7e7408f6c3e1575d` |
| 3 | `instance/_scratch_probe.db` | 73,728 | (d) 探针产物 · **已含合成测试数据** | 7 | players=27, game_records=**231**, max=**2026-03-02** | `4c3c7636a10f6e47` |
| 4 | `instance/baseball_players.backup_20260405_125745.db` | 49,152 | (c) 旧备份 | 4 | players=28, game_records=215, max=2025-11-16 | `2c99eb091e946c9e` |
| 5 | `instance/baseball_players.backup_20260405_165141.db` | 65,536 | (c) 旧备份 | 6 | players=29, game_records=215, max=2025-11-16 | `985d0af5bc70e7e3` |
| 6 | `instance/baseball_players.backup_incident_empty.db` | 73,728 | (b/c) 事故空库副本 · **0 表** | **0** | **空** | `2adb5d58731feadc` |
| 7 | `recovery/baseball_players_current_DO_NOT_TOUCH.db` | 73,728 | (b) 事故原件 · **0 表** | **0** | **空** | `2adb5d58731feadc` |
| 8 | `recovery/recovered_from_drop.db` | 73,728 | (b) 事故空库副本 · **0 表** | **0** | **空** | `2adb5d58731feadc` |
| 9 | `recovery/_pre_pytest_backup.db` | 73,728 | (b) pytest 前快照 · 与 #1 **字节相同** | 7 | 同 #1 | `7e7408f6c3e1575d` |
| 10 | `recovery/backup_20260405_125745.db` | 49,152 | (b) 旧备份副本 · 与 #4 **字节相同** | 4 | players=28, game_records=215 | `2c99eb091e946c9e` |
| 11 | `recovery/backup_20260405_165141.db` | 65,536 | (b) 旧备份副本 · 与 #5 **字节相同** | 6 | players=29, game_records=215 | `985d0af5bc70e7e3` |
| 12 | `recovery/git_1281bc2_db.bin` | 65,536 | (b) Git blob @ `1281bc2` | 6 | players=27, game_records=**231**, max=**2026-04-05** | `82c7bc5a28df6892` |
| 13 | `recovery/git_5f89a6d_db.bin` | 65,536 | (b) Git blob @ `5f89a6d` | 6 | players=27, game_records=231, max=2026-04-05 | `82c7bc5a28df6892` |
| 14 | `recovery/git_60ad337_db.bin` | 65,536 | (b) Git blob @ `60ad337` | 6 | players=27, game_records=231, max=2026-04-05 | `82c7bc5a28df6892` |
| 15 | `recovery/git_bb429ba_db.bin` | 65,536 | (b) Git blob @ `bb429ba` · **R0 恢复源** | 6 | players=27, game_records=**230**, max=**2025-11-22** | `909579420c5361ef` |
| 16 | `recovery/recovered_pre_incident.db` | 73,728 | (b) R0 恢复产物 | 7 | players=27, game_records=230, users=1, max=2025-11-22 | `03744da83ae50514` |

**总计：16 个文件，1,081,344 字节（1.03 MiB），按 SHA256 去重后仅 8 份不同内容。**

### 4.2 内容去重（8 份唯一内容）

| SHA256 | 份数 | 成员 | 语义 |
|---|---|---|---|
| `7e7408f6c3e1575d39061e7520eb12ea52a2e80a3a0f13a07047728a23912310` | 3 | #1 活库、#2 `_perf.db`、#9 `_pre_pytest_backup.db` | **当前生产状态** |
| `2adb5d58731feadcb4f092f2bb6692e29b92ac5a6f74dde95a5bc590b40e1cd6` | 3 | #6、#7、#8 | **事故空壳（0 表）** |
| `82c7bc5a28df68925f055145794629804b3810b84c6690ee4ee19ce25a7a3f27` | 3 | #12、#13、#14 | git 历史 231 条版本（2026-04-05 状态） |
| `2c99eb091e946c9ea03d1f82303630693fb238ce1f8d60bf8da14acda5c73201` | 2 | #4、#10 | 旧备份 A（4 表） |
| `985d0af5bc70e7e3a07e7412eb9bd35026ceab837b29c2f90110d7de094ee8cd` | 2 | #5、#11 | 旧备份 B（6 表） |
| `909579420c5361ef3ffbc1135eae9fde316c52f3155ffd7340a6cf11a1710283` | 1 | #15 | git blob `bb429ba`（R0 winner，230 条） |
| `03744da83ae50514687393a1fbb92bd861e30e0ae91215160fe384f52d3becfe` | 1 | #16 | R0 恢复产物（winner + users 表） |
| `4c3c7636a10f6e470569525be32d1508614eae1710f8e3c8ccbf811e51bd161c` | 1 | #3 | 探针库（含合成测试记录） |

> **净结论：真正"独立的"数据库内容只有 8 份。** 其中只有 1 份在生产运行。

### 4.3 完整 SHA256

```
instance/baseball_players.db                              7e7408f6c3e1575d39061e7520eb12ea52a2e80a3a0f13a07047728a23912310
instance/_perf.db                                         7e7408f6c3e1575d39061e7520eb12ea52a2e80a3a0f13a07047728a23912310
instance/_scratch_probe.db                                4c3c7636a10f6e470569525be32d1508614eae1710f8e3c8ccbf811e51bd161c
instance/baseball_players.backup_20260405_125745.db       2c99eb091e946c9ea03d1f82303630693fb238ce1f8d60bf8da14acda5c73201
instance/baseball_players.backup_20260405_165141.db       985d0af5bc70e7e3a07e7412eb9bd35026ceab837b29c2f90110d7de094ee8cd
instance/baseball_players.backup_incident_empty.db        2adb5d58731feadcb4f092f2bb6692e29b92ac5a6f74dde95a5bc590b40e1cd6
recovery/baseball_players_current_DO_NOT_TOUCH.db        2adb5d58731feadcb4f092f2bb6692e29b92ac5a6f74dde95a5bc590b40e1cd6
recovery/recovered_from_drop.db                           2adb5d58731feadcb4f092f2bb6692e29b92ac5a6f74dde95a5bc590b40e1cd6
recovery/_pre_pytest_backup.db                            7e7408f6c3e1575d39061e7520eb12ea52a2e80a3a0f13a07047728a23912310
recovery/backup_20260405_125745.db                       2c99eb091e946c9ea03d1f82303630693fb238ce1f8d60bf8da14acda5c73201
recovery/backup_20260405_165141.db                       985d0af5bc70e7e3a07e7412eb9bd35026ceab837b29c2f90110d7de094ee8cd
recovery/git_1281bc2_db.bin                              82c7bc5a28df68925f055145794629804b3810b84c6690ee4ee19ce25a7a3f27
recovery/git_5f89a6d_db.bin                               82c7bc5a28df68925f055145794629804b3810b84c6690ee4ee19ce25a7a3f27
recovery/git_60ad337_db.bin                               82c7bc5a28df68925f055145794629804b3810b84c6690ee4ee19ce25a7a3f27
recovery/git_bb429ba_db.bin                               909579420c5361ef3ffbc1135eae9fde316c52f3155ffd7340a6cf11a1710283
recovery/recovered_pre_incident.db                        03744da83ae50514687393a1fbb92bd861e30e0ae91215160fe384f52d3becfe
```

### 4.4 表清单 + 行数（逐文件）

所有文件共享同一套业务表结构（子集差异来自当时 schema 演进阶段）。行数由只读 `SELECT COUNT(*)` 取得。

**#1 `instance/baseball_players.db`（活库）— 7 张表**

| 表 | 行数 |
|---|---|
| players | 27 |
| positions | 9 |
| player_positions | 28 |
| game_records | **230** |
| fielder_profiles | 27 |
| pitcher_profiles | 27 |
| users | 1 |

> `game_records` 日期区间 **2023-04-01 → 2025-11-22**，与 Phase E0 取证基线完全吻合。

**#2 `instance/_perf.db`（探针产物）— 7 张表**，行数与 #1 完全相同（字节级相同文件）。

**#3 `instance/_scratch_probe.db`（探针产物）— 7 张表**

| 表 | 行数 | 备注 |
|---|---|---|
| players | 27 | |
| positions | 9 | |
| player_positions | 28 | |
| game_records | **231** | 比活库**多 1 条** |
| fielder_profiles | 27 | |
| pitcher_profiles | 27 | |
| users | 1 | admin 密码被改为进程内随机一次性密码 |

> ⚠️ **陷阱提示**：`max_date = 2026-03-02` 比活库的 2025-11-22 还"新"，但这**不是**更新的真实数据。
> `instance/_probe_stats_drift.py:16` 先 `shutil.copyfile` 复制生产库，随后第 39 行 `db.session.commit()`
> 写入了一条合成记录（`game_date='2026-03-01'`, `opponent='测试大学'`, at_bats=4 …）。
> **这是探针合成数据，切勿当作生产数据或"更新版本"误用。**

**#4 / #10 旧备份 A（4 表）** — `instance/baseball_players.backup_20260405_125745.db` ≡ `recovery/backup_20260405_125745.db`

| 表 | 行数 |
|---|---|
| players | 28 |
| positions | 9 |
| player_positions | 35 |
| game_records | 215 |

> 缺失 `fielder_profiles` / `pitcher_profiles` / `users`；日期上限 2025-11-16。

**#5 / #11 旧备份 B（6 表）** — `instance/baseball_players.backup_20260405_165141.db` ≡ `recovery/backup_20260405_165141.db`

| 表 | 行数 |
|---|---|
| players | 29 |
| positions | 9 |
| player_positions | 30 |
| game_records | 215 |
| fielder_profiles | 29 |
| pitcher_profiles | 10 |

> 缺失 `users`；日期上限 2025-11-16。

**#6 / #7 / #8 事故空壳（0 张表）** — `instance/baseball_players.backup_incident_empty.db` ≡ `recovery/baseball_players_current_DO_NOT_TOUCH.db` ≡ `recovery/recovered_from_drop.db`

```
表数量: 0
page_count = 18, freelist_count = 17
```
> **明确标注：空库（0 张表）。** 这是 2026-09-24 22:48 `db.drop_all()` 打在生产库上的事故现场快照。
> 17/18 页处于 freelist，只剩 `sqlite_schema` 表头。表名仍残留在 free pages 里（Phase R0 已手工扫描确认），
> 但**当前无法用 SQLite 正常查询**。这三个文件 SHA 完全相同，是同一份事故现场的三份拷贝。

**#9 `recovery/_pre_pytest_backup.db` — 7 张表**，行数与 #1 相同（字节级相同文件）。

**#12 / #13 / #14 Git blob 231 条版本（6 张表）**

| 表 | 行数 |
|---|---|
| players | 27 |
| positions | 9 |
| player_positions | 28 |
| game_records | **231** |
| fielder_profiles | 27 |
| pitcher_profiles | 27 |

> 三者 SHA256 **完全相同**（`82c7bc5a…`），日期上限 **2026-04-05**。缺 `users` 表。
> 已用 `git show <commit>:instance/baseball_players.db | sha256sum` 逐一复核，与文件名标注的 commit **精确对应**。

**#15 `recovery/git_bb429ba_db.bin` — 6 张表（R0 恢复源）**

| 表 | 行数 |
|---|---|
| players | 27 |
| positions | 9 |
| player_positions | 28 |
| game_records | **230** |
| fielder_profiles | 27 |
| pitcher_profiles | 27 |

> 日期区间 2023-04-01 → **2025-11-22**。Phase R0 报告 §7/§8 认定它是**唯一**精确匹配 Phase E0 取证指纹
> （27 players / 230 records / max 2025-11-22）的候选。缺 `users` 表（`users` 是后续 commit `1dbb67c` 才加的）。

**#16 `recovery/recovered_pre_incident.db` — 7 张表（R0 恢复产物）**

| 表 | 行数 |
|---|---|
| players | 27 |
| positions | 9 |
| player_positions | 28 |
| game_records | 230 |
| fielder_profiles | 27 |
| pitcher_profiles | 27 |
| users | 1 |

> `scripts/r0_recover.py` 的输出：`git_bb429ba_db.bin` + 新建 `users` 表 + admin 行
> （密码字段为占位符 `REQUIRES_PASSWORD_RESET`，需人工重设）。
> `recovery/_pre_promote_snapshot.json` 记录了 promote 前的指纹：players=27 / game_records=230 /
> max_date=2025-11-22 / fp_rows=27 / pp_rows=27 / fp_at_bats_total=351 / gr_at_bats=351（不变量成立）。

---

## 5. Git 状态与 `.gitignore` 验证

### 5.1 `git check-ignore -v` 逐个验证 —— 16/16 全部被忽略 ✅

| 文件 | 命中的 `.gitignore` 规则 |
|---|---|
| `instance/baseball_players.db` | `.gitignore:9:instance/` |
| `instance/baseball_players.backup_20260405_125745.db` | `.gitignore:9:instance/` |
| `instance/baseball_players.backup_20260405_165141.db` | `.gitignore:9:instance/` |
| `instance/baseball_players.backup_incident_empty.db` | `.gitignore:9:instance/` |
| `instance/_perf.db` | `.gitignore:9:instance/` |
| `instance/_scratch_probe.db` | `.gitignore:9:instance/` |
| `recovery/backup_20260405_125745.db` | `.gitignore:16:recovery/` |
| `recovery/backup_20260405_165141.db` | `.gitignore:16:recovery/` |
| `recovery/baseball_players_current_DO_NOT_TOUCH.db` | `.gitignore:16:recovery/` |
| `recovery/git_1281bc2_db.bin` | `.gitignore:16:recovery/` |
| `recovery/git_5f89a6d_db.bin` | `.gitignore:16:recovery/` |
| `recovery/git_60ad337_db.bin` | `.gitignore:16:recovery/` |
| `recovery/git_bb429ba_db.bin` | `.gitignore:16:recovery/` |
| `recovery/recovered_from_drop.db` | `.gitignore:16:recovery/` |
| `recovery/recovered_pre_incident.db` | `.gitignore:16:recovery/` |
| `recovery/_pre_pytest_backup.db` | `.gitignore:16:recovery/` |

`.gitignore` 相关规则原文：

```
 9:instance/       # 整个实例目录
11:*.db            # 扩展名规则
12:*.db-journal
13:*.db-wal
14:*.db-shm
16:recovery/       # 整个取证目录
```

### 5.2 `git ls-files` —— 当前无任何数据库文件被跟踪 ✅

```
$ git ls-files | grep -iE "\.db|sqlite|\.bin|recovery|instance/"
instance/matplotlib-cache/fontlist-v330.json
instance/matplotlib-cache/fontlist-v390.json
migrate_profiles_sqlite.py
```

- **16 个数据库文件 → 0 个被跟踪。** ✅
- `instance/matplotlib-cache/fontlist-v*.json` 仍在跟踪中（是 matplotlib 字体缓存，非数据库，但同属 `instance/` —— 属于历史遗留噪音，不在本次数据库盘点范围）。
- `migrate_profiles_sqlite.py` 是脚本，文件名含 `sqlite` 但不是数据库文件。

### 5.3 Git 历史：数据库**曾经**被提交过（事故史）⚠️

> **结论：历史上确实发生过数据库被提交进 git 的事故，已修复，且当前 0 个数据库被跟踪。**

| Commit | 主题 | 对 `.db` 的操作 |
|---|---|---|
| `1281bc2` | feat: 竞技风 UI 重构并准备公网部署 | **A**（新增）`baseball_players.db` + 2 个 backup |
| `81f154e` | fix: 从 Git 记录中移除数据库文件，防止泄露数据 | **D**（删除，移除跟踪） |
| `60ad337` | docs: 更新项目说明文档 | **A**（再次新增）3 个 `.db` |
| `fcdc331` | fix: 彻底从远程仓库移除数据库文件，防止干扰云端部署 | **D**（移除跟踪） |
| `5f89a6d` | data: 恢复本地球员历史数据到云端 | **A**（再次新增）`baseball_players.db` |
| `bb429ba` | feat: 完备底层 Player 类逻辑，集成 ClaudeCode+GLM5.1 提取流水线 | **A**+**M**（新增 2 个 backup + 修改主库） |
| `1ca3c0a` | **chore: stop tracking runtime artifacts** | **D**（`git rm --cached` 全部 3 个）—— **当前 HEAD 状态** |

被跟踪过的文件共 3 个：
`instance/baseball_players.db`、`instance/baseball_players.backup_20260405_125745.db`、
`instance/baseball_players.backup_20260405_165141.db`。

> ⚠️ **残留风险**：这些 blob **仍留在 git 历史对象库中**。`git log --all` 仍可检出完整数据库内容
> （本盘点的 `recovery/git_*_db.bin` 正是这样提取出来的）。若仓库曾推送到公开远端，
> 历史中的数据库内容等同泄露，需要 `git filter-repo` / BFG 清洗历史才能真正消除。

---

## 6. 风险与建议（只读盘点结论，不含任何改动）

| # | 发现 | 严重度 | 建议 |
|---|---|---|---|
| R1 | `instance/_scratch_probe.db` 含 **2026-03-01/02 合成测试记录**（对手"测试大学"），比活库 `max_date` 更"新"，极易被误当作最新生产数据 | 中 | 清理或改名加 `SYNTHETIC_` 前缀；盘点/迁移脚本应排除 `_scratch_probe.db` |
| R2 | `instance/baseball_players.backup_incident_empty.db` 是 **0 表空壳**，文件名带 `backup_` 极易被误当作可用备份 | 中 | 重命名为 `baseball_players.INCIDENT_EMPTY_DO_NOT_USE.db`，或直接删除（其内容在 `recovery/` 有两份相同副本） |
| R3 | `recovery/git_*_db.bin` **仅**靠 `.gitignore:16` 的 `recovery/` 目录规则被忽略；**没有任何扩展名规则覆盖 `.bin`** | 低 | 追加 `*.bin` 或 `git_*_db.bin` 规则，防止文件被移出 `recovery/` 后误提交 |
| R4 | `instance/_perf.db` 与 `recovery/_pre_pytest_backup.db` 与活库**字节完全相同**，属纯冗余 | 低 | 可清理；或保留 `_pre_pytest_backup.db` 作为回滚点 |
| R5 | git 历史中仍存有完整数据库 blob（含 `users` 表的密码哈希字段） | **高** | 若远端曾公开，需 `git filter-repo` 清洗历史并强制推送 / 轮换凭据 |
| R6 | 磁盘上 16 个库仅 8 份唯一内容、总量仅 1.03 MiB，但命名混乱 | 低 | 建议统一为 `instance/`（生产）+ `recovery/<类别>/`（归档）两目录结构，并加 `README` 说明各文件用途 |
| R7 | `.gitignore:9` 的 `instance/` 与已跟踪的 `instance/matplotlib-cache/*.json` 冲突（已跟踪文件不受 gitignore 约束） | 低 | `git rm --cached instance/matplotlib-cache/` 或补 `.gitignore` 规则 |

---

## 7. 复现命令

```bash
# 1) 找到所有 SQLite 文件（魔术字节法，不依赖扩展名）
find . -type f -not -path "./.git/*" -size +0 | while read f; do
  h=$(head -c 15 "$f" 2>/dev/null | od -c | head -1)
  case "$h" in *"S   Q   L   i   t   e"*) echo "SQLITE: $f";; esac
done

# 2) 逐个验证忽略状态
git check-ignore -v instance/baseball_players.db recovery/git_bb429ba_db.bin

# 3) 确认当前没有被跟踪的数据库
git ls-files | grep -iE '\.db$|\.sqlite|\.bin$'

# 4) 追溯历史中曾被跟踪的数据库
git log --all --oneline --name-status -- "instance/*.db"

# 5) 只读打开并统计
python -c "import sqlite3; c=sqlite3.connect('file:instance/baseball_players.db?mode=ro',uri=True); \
print(c.execute('select count(*) from game_records').fetchone())"
```

---

## 8. 附：只读保证

- 全部 16 个文件均通过 `sqlite3.connect('file:<abs-path>?mode=ro', uri=True)` 打开；
- 未使用任何可写模式，未执行写语句；
- 盘点前后各文件 SHA256 与 mtime 未变（未产生 `-wal` / `-shm` 伴随文件，全库无 WAL 遗留）；
- 盘点过程仅新增本文件 `docs/DB_INVENTORY.md`，**未修改或删除任何既有文件**。
