# Game Domain & Service Architecture Design — Phase E0

> 只设计，不实现。Phase C 启动前必须先 review 这份设计。

## 1. Game Domain Model

### 为什么需要 Game 实体

Forensic 结果显示：
- 1 个真实重复候选（player 28, 2024-11-16 batting x2）
- 10 个双赛日记录（2024-11-10 同一球员 vs 2 个对手）
- 39 个双重身份记录（同一球员同一场比赛有 batting + pitching）

当前 GameRecord 直接存 `(player_id, game_date, opponent, is_pitching_record)`，无法表达：
- 双赛日（两场同一天同对手 vs 同一天不同对手）
- 比赛场地
- 比赛顺序（第几场）
- 来源 PDF（哪个文件导入）

### Game 实体设计

```python
class Game(db.Model):
    __tablename__ = 'games'

    id = db.Column(db.Integer, primary_key=True)
    game_date = db.Column(db.Date, nullable=False)
    opponent = db.Column(db.String(100))
    season = db.Column(db.String(20))          # e.g. "2024秋" "2025春"
    venue = db.Column(db.String(100))          # 比赛场地
    game_number = db.Column(db.Integer)        # 同日第几场（双赛日用）
    source_pdf = db.Column(db.String(255))     # 导入来源 PDF 路径
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    records = db.relationship('GameRecord', back_populates='game',
                              cascade='all, delete-orphan')

    # 当 game_number 存在时，必须同日唯一（同 game_number）
    __table_args__ = (
        UniqueConstraint('game_date', 'opponent', 'game_number',
                        name='uq_game_per_day'),
    )


class GameRecord(db.Model):
    __tablename__ = 'game_records'

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)

    is_pitching_record = db.Column(db.Boolean, default=False)

    # batting / pitching 字段（保留现有）
    at_bats = ...
    innings_pitched = ...
    win = ...
    # ...

    game = db.relationship('Game', back_populates='records')
    player = db.relationship('Player', backref=db.backref('game_records', lazy=True))

    __table_args__ = (
        # 同一 game 内，同一球员，每种类型只能 1 条
        UniqueConstraint('game_id', 'player_id', 'is_pitching_record',
                        name='uq_player_per_game'),
    )
```

### Game 实体解决的问题

| 问题 | 旧 GameRecord | 新 GameRecord + Game |
|------|---------------|----------------------|
| 双赛日 | 无法表达 | `game.game_number` 区分 |
| 同一球员同时打击 + 投球 | OK (is_pitching_record) | OK (同上) |
| 来源追溯 | ❌ 不知道哪个 PDF | `game.source_pdf` |
| 比赛场地 | ❌ | `game.venue` |
| 唯一约束 | `(player_id, game_date, opponent, is_pitching_record)` 不够细 | `(game_id, player_id, is_pitching_record)` 更准确 |

### Migration Path (Phase C2+)

```
Step 1: 新增 games 表
Step 2: 一次性脚本扫描 game_records，按 (game_date, opponent) 分组，每组创建一个 Game
  - 同一天同一对手只出现 1 个 → game_number=1
  - 同一天同一对手出现 N 次 → 创建 N 个 Game，game_number=1..N
Step 3: 给每个 game_record 填 game_id
Step 4: 加 FK 约束 NOT NULL
Step 5: 加 UNIQUE 约束 (game_id, player_id, is_pitching_record)
Step 6: 保留旧 (player_id, game_date, opponent, is_pitching_record) 索引用于回溯，但不再作唯一
```

**前置条件**：
- ✅ STEP 10 forensics 必须先识别出 1 个真重复（player 28, 2024-11-16 batting x2）并人工决定
- 如果该重复应被丢弃：在迁移脚本里 DELETE 一条
- 如果该重复是合法双赛日的另一场：保留 2 条，分别放入 2 个 Game

---

## 2. Source of Truth Architecture

```
┌─────────────────────────────────────────────────┐
│            GameRecord (canonical)               │
│  - 不变量：单一真实源                            │
│  - 所有写操作都必须经过 GameRecord               │
└─────────────────────┬───────────────────────────┘
                      │
                      │  Player.apply_game_record(rec)
                      │  Player.reverse_game_record(rec)
                      ▼
┌─────────────────────────────────────────────────┐
│   FielderProfile / PitcherProfile (cache)       │
│  - derived from sum(GameRecord.* for player)    │
│  - 可重建，可被修复                              │
│  - 读路径可走 profile                            │
└─────────────────────────────────────────────────┘
```

### 不变量（重构后必须持续成立）

```
FielderProfile.at_bats_total == SUM(GameRecord.at_bats WHERE player_id=? AND NOT is_pitching_record)
FielderProfile.hits_total == SUM(GameRecord.hits WHERE player_id=? AND NOT is_pitching_record)
... (其他字段同理)

PitcherProfile.innings_pitched_total == SUM(GameRecord.innings_pitched WHERE player_id=? AND is_pitching_record)
... (其他字段同理)
```

### 服务层调用边界

| 服务 | 职责 | 不应直接调用 |
|------|------|--------------|
| `PlayerService.create(name, jersey, ...)` | 创建球员 + 初始化 profile | GameRecord |
| `PlayerService.update(player, fields)` | 改 name/jersey/positions，不动统计 | Profile 统计字段 |
| `GameService.add_record(player, game, data)` | 创建 GameRecord + 调用 apply_game_record + commit | Player 内部字段 |
| `GameService.delete_record(record)` | 反向调用 reverse_game_record + 删除 | Player 内部字段 |
| `StatsService.rebuild_player(player_id)` | 从 GameRecord 全量重算 profile | GameRecord 写 |
| `StatsService.rebuild_all()` | 全队重建 | 同上 |
| `ImportService.import_pdf(path)` | 解析 + 创建 Game + 调 GameService.add_record | 直接写 profile |

### 禁止路径

| 操作 | 旧实现 | 新实现 |
|------|--------|--------|
| PUT /api/players/<id> 直接改 profile 字段 | ✅ 允许 | ❌ **禁止**（仅允许 name/jersey/positions） |
| 启动时自动 rebuild stats | ✅ 一直跑 | ⚠️ 可选；用 StatsService.rebuild_all() 但只在检测到漂移时跑 |
| add_game_record inline 累加 | ✅ 直接 `player.at_bats_total += ...` | ❌ 必须调 `Player.apply_game_record(rec)` |

---

## 3. Service Layer Architecture

```
app/
├── __init__.py            # create_app(), db.init_app, login_manager
├── extensions.py          # db = SQLAlchemy(), login_manager = LoginManager(), csrf, limiter
├── config.py              # ProductionConfig / DevelopmentConfig / TestingConfig
├── models/
│   ├── __init__.py
│   ├── player.py          # Player, FielderProfile, PitcherProfile
│   ├── game.py            # Game, GameRecord
│   ├── position.py        # Position
│   └── user.py            # User
├── services/
│   ├── player_service.py  # create, update, delete
│   ├── game_service.py    # add_record, delete_record
│   ├── stats_service.py   # rebuild_player, rebuild_all
│   └── pdf_import_service.py  # parse_pdf + create_game + bulk add
├── blueprints/
│   ├── players_bp.py      # /api/players/*
│   ├── game_records_bp.py # /api/game_records/*, /api/matchup/*
│   ├── stats_bp.py        # /api/stats/*, /api/visualization/*
│   ├── pdf_bp.py          # /api/pdf/*
│   ├── matchup_bp.py      # /api/matchup/*
│   ├── auth_bp.py         # /login, /logout
│   └── pages_bp.py        # /, /players, /stats, /pdf_viewer 等页面
└── errors.py              # AppError 类，统一错误返回
```

### 依赖注入方向（避免循环）

```
Blueprint → Service → Model
   ↓           ↓        ↑
  HTTP       业务     ORM 字段
  解析       逻辑
```

Service 不依赖 Blueprint；Model 不依赖 Service；Model 之间通过 FK / relationship 关联。

### 错误处理

```python
# app/errors.py
class AppError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.message = message
        if status_code:
            self.status_code = status_code
        self.payload = payload or {}

class NotFound(AppError): status_code = 404
class Conflict(AppError): status_code = 409
class ValidationError(AppError): status_code = 400
class PermissionDenied(AppError): status_code = 403

# Blueprint:
try:
    service.do_thing()
except NotFound as e:
    return _safe_error(e, 404)
except Conflict as e:
    return _safe_error(e, 409)
except AppError as e:
    return _safe_error(e, e.status_code)
```

---

## 4. 实施顺序（Phase C 重构）

1. **Phase C0**: 新增 Game model + migration 脚本（一次性数据迁移）
2. **Phase C1**: 抽 Blueprint — app.py 路由搬入 blueprints/*_bp.py
3. **Phase C2**: 抽 Service — PlayerService / GameService / StatsService
4. **Phase C3**: 抽 Model 方法 — Player.apply_game_record / reverse_game_record
5. **Phase C4**: 切所有写路径走 Service — 删 inline 累加
6. **Phase C5**: PUT /api/players/<id> 限制只改元数据，不动 profile
7. **Phase C6**: 加 invariant check (`tests/test_invariants.py`)
8. **Phase C7**: 启动时 stats drift detector — 检测到漂移才 rebuild

每阶段都要：
- 跑全量 pytest（含本次 baseline tests）
- 不变量必须 0 个 inconsistency
- 提交 git

---

## 5. 暂未决定的开放问题

- [ ] GameRecord 上的 `errors_fielding / passed_balls` 字段未使用，是删除还是保留？
- [ ] `wild_pitches` 在 GameRecord 模型但 app.py 写入路径没更新 player — 修复还是移除？
- [ ] FielderProfile / PitcherProfile 的 ON DELETE CASCADE：删球员时是级联删 profile 还是保护？
- [ ] `add_sample_data()` 的开发初始化路径是否要保留（目前默认不会触发）？
- [ ] 是否引入事件溯源 / audit log（每次 stats 修改记录谁何时为何修改）？

---

## 6. NO-GO 信号

如果出现以下任一信号，禁止进 Phase C：

| 信号 | 检测方法 |
|------|----------|
| Baseline test 失败 > 5 个 | pytest 报告 |
| Stats 不变量被破坏 | scripts/db_forensics.py 输出 inconsistencies > 0 |
| 出现真重复但无法人工确认是删还是留 | forensics STEP 4 结果是 1，但无决策 |
| CSRF 模型仍有 mutation API 豁免 | grep `@csrf.exempt` |
| Service 边界没有定义清楚 | 本文档未完成 |

当前 Phase E0 状态：CSRF 已修正；stats 不变量 0 inconsistency；1 真重复已识别待决策；Service 边界已设计；Blueprint 已设计。
**Gate 状态：CONDITIONAL GO**（待人工决策 1 个真重复后正式 GO）。