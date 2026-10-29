# API 契约 — POWER ARENA 棒球队管理系统

> 版本：**v1.1**
> 基线代码：2026-10-29（`app.py` 全部 32 个 API 路由 + 14 个页面路由）
> 面向对象：**接手继续开发的学弟**
> 配套文档：[`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)（curl 调用示例）、[`FEATURE_PROPOSALS.md`](FEATURE_PROPOSALS.md)（功能提案）

---

## 0. 三分钟上手

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # 填进 .env 的 SECRET_KEY

# 3. 本地启动（只绑定 127.0.0.1，局域网不可达）
python run_local.py
# → http://127.0.0.1:5000

# 4. 管理员账号
python scripts/reset_admin_password.py
```

**部署启动**用 `python app.py`（绑定 `0.0.0.0`）。**不要**用 `run_local.py` 上公网。

---

## 1. 基础约定

| 项 | 约定 |
|---|---|
| 基址 | `http://127.0.0.1:5000`（本地） |
| 数据格式 | 请求与响应均为 `application/json`（`/api/export/csv` 除外） |
| 字符编码 | UTF-8。响应里的中文**不转义**（`config.py` 的 `JSON_AS_ASCII = False`） |
| 认证 | Session Cookie。`POST /login` 成功后浏览器自动携带 |
| 跨域 | 不支持（纯同源部署） |

### 1.1 认证流程

```
POST /login  (表单，字段 username / password / csrf_token)
    → 302 重定向到 /
    → 响应 Set-Cookie: session=...

后续所有请求带 Cookie 即可。
```

未登录访问写接口 → `302` 重定向到 `/login`。

### 1.2 CSRF（**最重要的一条**）

后端全局启用了 `CSRFProtect`（`app.py:126`），且 **Phase E0 已刻意移除 `/api/*` 的豁免**。

| 请求类型 | 是否需要 CSRF | 怎么带 |
|---|---|---|
| `GET` / `HEAD` / `OPTIONS` | 否 | — |
| `POST` / `PUT` / `DELETE` | **是** | 请求头 `X-CSRFToken: <token>` |
| 表单 POST（如 `/login`、`/logout`） | **是** | 隐藏域 `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` |

**Token 来源**：页面 `<meta name="csrf-token" content="...">`。所有页面都已包含。

**前端已封装**（`static/js/api.js`），新代码直接用：

```js
const players = await api.get('/api/players');
const created = await api.post('/api/players', { name: '张三', ... });
```

`api.js` 会自动：
- 给 `fetch` / `$.ajax` 加上 `X-CSRFToken`
- 把 `body` 为普通对象时自动 JSON 化
- 把非 2xx 响应转成 `ApiError { message, status, code, data }`

> ⚠️ **`config.py` 的 `TestingConfig` 关闭了 CSRF**（`WTF_CSRF_ENABLED = False`），
> 所以**测试里测不出 CSRF 缺失**。生产配置下缺 token 一律 400。
> 写新接口时，请在浏览器里实际点一次，别只看测试。

### 1.3 响应格式

**成功**：直接返回数据本体。

```jsonc
// 列表型
[{ "id": 7, "name": "韩登越", ... }]

// 对象型
{ "message": "球员添加成功", "player": { ... } }
```

**失败**：统一 `{"error": "<中文可读消息>"}` + HTTP 状态码。

```jsonc
{ "error": "姓名和背号为必填项" }
```

> 约定：**新增接口一律沿用 `{"error": "..."}`**。如果需要区分错误类型，
> 可以额外加一个 `"code"` 字段（**不要**改成嵌套对象，会破坏前端解析）。

### 1.4 状态码使用约定

| 码 | 什么时候用 | 例子 |
|---|---|---|
| 200 | 查询成功、修改成功 | |
| 201 | 创建成功（新增球员、导入比赛记录） | `POST /api/players` |
| 302 | 未登录访问受保护资源 → 重定向 `/login` | |
| 400 | 参数不合法、业务规则不满足 | 缺 CSRF、字段为空、不能删最后一名球员 |
| 403 | 已登录但无权限（预留，当前只有单一 admin 角色） | |
| 404 | 资源不存在 / 数据不足 | `GET /api/players/999` |
| 405 | 方法不允许 | |
| 429 | 触发速率限制 | 登录 5 次/分钟、API 60 次/分钟 |
| 500 | 未捕获异常（消息已脱敏，日志里有完整堆栈） | |

---

## 2. 端点清单

### 2.1 球员

| 方法 | 路径 | 认证 | 返回 | 说明 |
|---|---|---|---|---|
| GET | `/api/players` | 公开 | `Player[]` | 全部球员。**每项含 50 个键**：扁平统计字段 + `fielder_profile` + `pitcher_profile` 两个嵌套对象 |
| POST | `/api/players` | admin | `{message, player}` | 新增。body 见 §3.1 |
| GET | `/api/players/<id>` | 公开 | `Player` | 单个球员 |
| PUT | `/api/players/<id>` | admin | `{message, player, ignored_fields}` | 更新**资料**。**只接受 metadata**；提交统计字段 → 400（见 §3.1b） |
| DELETE | `/api/players/<id>` | admin | `{message, remaining_players}` | 删除。不能删最后一名球员（400） |
| GET | `/api/players/batters` | 公开 | `对象[]` | 键为中文（打数/安打/…）。**注意：返回全部 27 人，不过滤投手**（见 §4.2） |
| GET | `/api/players/pitchers` | 公开 | `对象[]` | 键为中文（局数/被安打/…）。**只返回投手**（6 人） |

`Player` 对象结构（`database.py:Player.to_dict`）：

```jsonc
{
  "id": 7,
  "name": "韩登越",
  "jersey_number": "30",
  "primary_position": "投手",
  "positions": ["投手"],
  "positions_string": "投手",
  "is_pitcher": true,
  "player_type": "pitcher",          // "pitcher" | "fielder"
  "has_fielder_profile": true,
  "has_pitcher_profile": true,

  // 打击统计（扁平，与 fielder_profile 内同名字段值一致）
  "at_bats_total": 31, "runs_total": 18, "hits_total": 19, "rbi_total": 22,
  "walks_total": 8, "strikeouts_batting_total": 4,
  "doubles": 4, "triples": 0, "home_runs_batting": 3, "total_bases": 31,
  "hit_by_pitch": 1, "stolen_bases": 8, "caught_stealing": 1,
  "sacrifice_flys": 0, "sacrifice_hits": 0,
  "errors_fielding": 0, "passed_balls": 0,
  "batting_average": 0.613, "on_base_percentage": 0.707,
  "slugging_percentage": 1.0, "ops": 2.32,
  "position": "投手", "home_runs": 3,

  // 投球统计（仅 is_pitcher=true 时才有这些键）
  "innings_pitched_total": 24.1, "hits_allowed_total": 9,
  "runs_allowed_total": 2, "earned_runs_total": 2,
  "walks_allowed_total": 5, "strikeouts_total": 41,
  "home_runs_allowed_total": 1, "pitches": 0, "strikes": 0,
  "hit_by_pitch_allowed": 0, "batters_faced": 0, "wild_pitches": 0,
  "era": 0.75, "whip": 1.16, "strike_percentage": 0.0,

  // 嵌套档案（数据真身）
  "fielder_profile": { "player_id": 7, "at_bats_total": 31, ... },
  "pitcher_profile": { "player_id": 7, "innings_pitched_total": 24.1, ... }
}
```

### 2.2 比赛记录

| 方法 | 路径 | 认证 | 返回 | 说明 |
|---|---|---|---|---|
| POST | `/api/game_records` | admin | `{message, record_id, updated_stats}` | 新增一条记录。**一次一名球员一条记录** |
| POST | `/api/game_records/batch` | admin | `{message, created, record_ids, game_date, opponent}` | **整场比赛一次写入**（打击+投球混合）。全有或全无 |
| GET | `/api/game_records/<id>` | 公开 | 原始记录全字段 | 编辑用。取回该条记录的完整原始字段 |
| PUT | `/api/game_records/<id>` | admin | `{message, record_id, updated_stats}` | **编辑**已有记录 |
| DELETE | `/api/matchup/game_record/<id>` | admin | `{message, player_name, opponent, game_date}` | 删除一条记录 |

`updated_stats` 返回写入后该球员的累计统计快照。

> **写入语义（重要）**：写操作**只写 `game_records`**，统计档案一律用
> `rebuild_player_stats()` 从 `game_records` 重算，**不做增量 +/-**。
> 这样恒等式 `profile.at_bats_total == SUM(GameRecord.at_bats WHERE player_id=?)`
> 永远成立，也顺带修复历史漂移。
> 旧实现（PUT 直接覆盖 profile、DELETE 用 `max(0,x)` 扣减）已移除。

### 2.3 统计

| 方法 | 路径 | 认证 | 返回 | 说明 |
|---|---|---|---|---|
| GET | `/api/stats/batting` | 公开 | `对象[]` | 打击统计。键：`name, position, batting_average, home_runs, rbi, stolen_bases` |
| GET | `/api/stats/pitching` | 公开 | `对象[]` | 投球统计。键：`name, position, era, whip, strikeouts, innings` |
| GET | `/api/stats/visualization` | 公开 | `{image, total_players, batters, pitchers}` | `image` 是 `data:image/png;base64,...` |
| GET | `/api/stats/batting_leaderboard` | 公开 | `对象[]` | 前 10 名。键：`name, jersey_number, position, avg, obp, hits, hr, rbi` |
| GET | `/api/stats/pitching_leaderboard` | 公开 | `对象[]` | 键：`name, jersey_number, position, era, whip, strikeouts, wins, losses, saves, win_pct, innings` |
| GET | `/api/visualization/batting` | 公开 | `{image, ...}` | 打击可视化图（base64 PNG） |
| GET | `/api/visualization/pitching` | 公开 | `{image, ...}` | 投球可视化图 |
| GET | `/api/export/csv` | 公开 | CSV 文件流 | 导出全部球员 |

> **图表接口慢**：服务端用 matplotlib 现画 PNG，`/api/visualization/*` 约 1–3 秒。
> 前端务必给 loading 态，别让用户以为卡死。

### 2.4 对局信息

| 方法 | 路径 | 认证 | 参数 | 返回 |
|---|---|---|---|---|
| GET | `/api/matchup/opponents` | 公开 | — | `string[]`，13 个对手名 |
| GET | `/api/matchup/search_records` | 公开 | `player_id` / `opponent`（可组合） | `{batting_records, pitching_records, batting_summary, pitching_summary, title, filters}` |
| GET | `/api/matchup/player_vs_opponent` | 公开 | `player_id` + `opponent`（**都必填**） | 单球员对单对手的汇总 |
| GET | `/api/matchup/player_game_records` | 公开 | `player_id` | 该球员全部比赛记录 |
| GET | `/api/matchup/all_game_records` | 公开 | — | 全队所有记录（同 search_records 的结构） |
| DELETE | `/api/matchup/game_record/<id>` | admin | — | 删除一条比赛记录，**会同步扣减累计统计** |

### 2.5 PDF

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| GET | `/api/pdf/files` | 公开 | 列出 `data/` 下所有 PDF：`{display_name, filename, full_path, path, size, year}` |
| GET | `/api/pdf/view/<path>` | 公开 | 返回 PDF 的 base64 JSON（不是原始 PDF 流） |
| GET | `/api/pdf/parse/<path>` | 公开 | **只解析不写库**，返回完整解析结果，用于预览 |
| POST | `/api/pdf/import_all` | admin | body `{dry_run: bool}`，批量导入 |
| POST | `/api/pdf/import_one` | admin | body `{filepath: "2025/xxx.pdf"}` |
| POST | `/api/pdf/upload` | admin | multipart，字段名 `file`。**只解析并返回预览，不写库** |
| POST | `/api/pdf/confirm_import` | admin | body `{filepath}`，**重新解析后写库** |

> ⚠️ `confirm_import` **不做 `_safe_data_path` 校验**（其他 3 个端点都做了）。
> 这是已知的待修项（§4.3）。

---

## 3. 请求示例

### 3.1 新增球员

```bash
curl -X POST http://127.0.0.1:5000/api/players \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" \
  -b cookies.txt \
  -d '{
    "name": "张三",
    "jersey_number": "18",
    "player_type": "fielder",
    "positions": ["游击手", "二垒手"],
    "primary_position": "游击手"
  }'
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 姓名 |
| `jersey_number` | ✅ | 背号（字符串，允许 `'00'`） |
| `player_type` | — | `"pitcher"` / `"fielder"`，也可写 `"投手"` |
| `is_pitcher` | — | 布尔，与 `player_type` 二选一，优先级更高 |
| `positions` | ✅ | 守备位置中文名数组，如 `["投手","外野手"]` |
| `primary_position` | ✅ | 必须在 `positions` 里 |

业务规则：
- `player_type=pitcher` → 自动把「投手」插到 `positions` 首位
- `player_type=fielder` → 自动移除「投手」位置
- `positions` 为空 → 400
- `primary_position` 不在 `positions` 内 → 400

### 3.1b 更新球员资料（只改 metadata）

```bash
curl -X PUT http://127.0.0.1:5000/api/players/7 \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{"name": "张三", "jersey_number": "18",
       "is_pitcher": false,
       "positions": ["游击手", "二垒手"],
       "primary_position": "游击手"}'
```

**允许的字段**（其余一律视为资料字段之外的键，会被忽略并在 `ignored_fields` 里回报）：

| 字段 | 说明 |
|---|---|
| `name` | 姓名 |
| `jersey_number` | 背号 |
| `is_pitcher` | 布尔 |
| `player_type` | `"pitcher"` / `"fielder"`（与 `is_pitcher` 二选一） |
| `positions` | 守备位置中文名数组 |
| `primary_position` | 必须在 `positions` 里 |

**统计字段一律拒绝**（400）：

累计数据（打数、安打、局数、ERA、OPS……）是 `game_records` 的派生值，
**只能通过比赛记录接口写入**。提交统计字段会被直接拒绝，不会静默丢弃：

```json
{
  "error": "统计字段不能通过球员接口写入。累计数据只能由比赛记录推导，请改用 POST /api/game_records 或 POST /api/game_records/batch。",
  "rejected_fields": ["at_bats_total", "hits_total"]
}
```

拒绝的字段集合由 `Player` 上的 property proxy 清单推导（`database.py:_build_profile_proxy`），
以后给档案表加字段，这个接口自动跟着收紧。

> **为什么不是「静默忽略」**：静默忽略会出现「接口返回成功，但数据没进去」的情况 ——
> 队员以为改了，实际没改。响亮地失败更安全。

> **改 metadata 不会重算统计**：档案是 `game_records` 的派生值，
> 改资料不产生新记录，因此档案保持原样（恒等式 `profile == SUM(game_records)` 继续成立）。

### 3.1c 批量录入页面

`GET /batch_entry`（admin）—— 粘贴 box score 一次写入整场比赛。

- 打击粘贴框格式：`姓名 AB R H RBI BB SO`，尾部可选 `2B 3B HR HBP SB CS SF SH`
- 投球粘贴框格式：`姓名 IP H R ER BB SO`，尾部可选 `HR P ST BF WP`
- 页面在提交前做实时解析 + 逐行校验（姓名是否存在 / 是否投手 / 数值合法性 / 业务不变量），
  任何一行有问题就阻止提交，**不会静默跳过**
- 实际写入走 `POST /api/game_records/batch`（§3.2），语义与该端点完全一致

局数（IP）按 box score 上印的**字面数字**入库（中文记法 `.1` = 1/3 局），
与既有记录同口径 —— 不在 UI 层做换算。

### 3.2 批量写入整场比赛

一次提交整场比赛（9 名打击手 + 2-3 名投手）：

```bash
curl -X POST http://127.0.0.1:5000/api/game_records/batch \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{
    "game_date": "2025-11-22",
    "opponent": "北京科技大学",
    "records": [
      {"player_id": 7, "is_pitching": false, "at_bats": 3, "runs": 2, "hits": 3, "rbi": 3},
      {"player_id": 9, "is_pitching": false, "at_bats": 4, "runs": 1, "hits": 1, "rbi": 0},
      {"player_id": 9, "is_pitching": true,  "innings_pitched": 3.0, "hits_allowed": 4,
       "runs_allowed": 1, "earned_runs": 1, "walks_allowed": 2, "strikeouts": 6,
       "home_runs_allowed": 0, "pitches": 60, "strikes": 40, "batters_faced": 12, "win": true}
    ]
  }'
```

规则：
- `records` 里每项的字段名与单条新增**完全一致**
- 条目可以带自己的 `opponent` 覆盖批次级对手；不写就继承批次级的
- `game_date` / `opponent` 是批次级字段，所有条目共享
- **全有或全无**：任何一条不合法（球员不存在 / 场员录投球 / 日期格式错）→ 整批回滚，返回 400 且不留下任何记录

### 3.3 编辑已有记录

```bash
# 先取原始记录
curl http://127.0.0.1:5000/api/game_records/233

# 再 PUT 回去（只带要改的字段也可以，但建议全量带，避免意外清零）
curl -X PUT http://127.0.0.1:5000/api/game_records/233 \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{"player_id": 7, "game_date": "2025-11-22", "opponent": "北京科技大学",
       "is_pitching": false,
       "at_bats": 6, "runs": 3, "hits": 4, "rbi": 3}'
```

- 编辑是**替换**语义，不是叠加：原来 4 打数改成 6，档案变成 6 而不是 10
- 改 `player_id` 的话，旧球员和新球员的档案都会重算
- `is_pitching` 可以改（打击记录改成投球记录），但目标球员必须是投手

### 3.4 新增比赛记录

打击：

```bash
curl -X POST http://127.0.0.1:5000/api/game_records \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{"player_id": 7, "game_date": "2025-11-22", "opponent": "北京科技大学",
       "is_pitching": false,
       "at_bats": 3, "runs": 2, "hits": 3, "rbi": 3,
       "walks": 0, "strikeouts": 0,
       "doubles": 0, "triples": 0, "home_runs_game": 0,
       "hit_by_pitch": 0, "stolen_bases_game": 0, "caught_stealing": 0,
       "sacrifice_flys": 0, "sacrifice_hits": 0}'
```

投球：

```bash
curl -X POST http://127.0.0.1:5000/api/game_records \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{"player_id": 7, "game_date": "2025-11-22", "opponent": "北京科技大学",
       "is_pitching": true,
       "innings_pitched": 1.0, "hits_allowed": 1, "runs_allowed": 0,
       "earned_runs": 0, "walks_allowed": 0, "strikeouts": 3,
       "home_runs_allowed": 0, "pitches": 27, "strikes": 17,
       "hit_by_pitch_allowed": 0, "batters_faced": 3,
       "win": true, "loss": false, "save": false}'
```

注意：
- `is_pitching=true` 但该球员 `is_pitcher=false` → 400「当前球员是场员，不能录入投球记录」
- `game_date` 格式必须是 `YYYY-MM-DD`
- 字段名不统一：打击用 `home_runs_game` / `stolen_bases_game`，投球用 `strikeouts`（打击侧也叫 `strikeouts`）—— **这是已知的坑，见 §4.4**

---

## 4. 已知问题（接手前请先读）

### 4.1 ~~`PUT /api/players/<id>` 会直接覆盖累计统计~~ ✅ 已修复（2026-10-29）

**原问题**：它同时改姓名/背号/位置**和** 16 个打击 + 12 个投球累计字段，绕过 `GameRecord`。
这破坏了「GameRecord 是唯一真实源」的设计，且下次启动会被
`sync_stats_from_game_records()` 静默覆盖回去。

> `Player.at_bats_total` 等是 `database.py:_build_profile_proxy` 生成的 property proxy，
> 直接读写 `fielder_profiles` / `pitcher_profiles` —— 所以 `setattr` 是**真实写库**，
> 不是看起来像写库。

**现状**：Phase R2 已把该接口收窄为 **metadata-only**，
提交统计字段一律 400 拒绝（响应带 `rejected_fields`）。
契约见 **§3.1b**，实现见 `app.py:update_player`。

至此，**所有**统计写入口都收敛到 `game_records` 一条路径：
`POST /api/game_records`、`POST /api/game_records/batch`、`PUT /api/game_records/<id>`、
`DELETE /api/matchup/game_record/<id>` —— 四者写完都由 `rebuild_player_stats()` 重算档案。

> 遗留：`import_pdfs.py` 的 PDF 导入仍走 `+=` 增量写 profile（见 §4.3 之后的 backlog）。

### 4.2 `/api/players/batters` 不过滤投手

用的是 `_batting_query()` = `Player.query.join(FielderProfile)`，没加
`_is_pitcher.is_(False)` 过滤，所以返回全部 27 人。
而 `/api/players/pitchers` 是过滤过的（6 人）。**两者不对称。**

（棒球里投手也要打击，所以"打击球员 = 全队"在语义上说得通，但接口名不对称容易误解。）

### 4.3 `/api/pdf/confirm_import` 缺路径校验

其他 3 个 PDF 端点都用 `_safe_data_path()`（`realpath` + `commonpath` 严格校验），
只有它只做了 `os.path.exists()`。管理员可以让服务器解析任意绝对路径的 PDF。

### 4.4 字段命名不一致

| 概念 | GameRecord 字段 | API body 字段 | 冲突点 |
|---|---|---|---|
| 本垒打 | `home_runs_batting` | 打击 `home_runs_game` / 投球 `home_runs_allowed` | 三个名字 |
| 三振 | `strikeouts`（打击） / `strikeouts_pitched`（投球） | 两侧都叫 `strikeouts` | 靠 `is_pitching` 区分 |
| 盗垒 | `stolen_bases` | 打击 `stolen_bases_game` | — |
| 触身球 | `hit_by_pitch` | 打击 `hit_by_pitch` / 投球 `hit_by_pitch_allowed` | 拼写差一个字母，极易传错 |

> ⚠️ **2026-10-29 修**：`GET /api/game_records/<id>` 的响应里 `'strikeouts'` 这个键
> 曾写了两次（打击一次、投球一次），Python dict 后者覆盖前者 → **打击记录的三振恒返回 0**。
> 对局页用这个端点回填编辑表单再 PUT 回去，会把打击三振**抹成 0**（生涯三振跟着掉）。
> 现在按 `is_pitching` 返回对应列，与本表的约定一致。
> `tests/test_game_record_read_back.py::test_no_duplicate_keys_in_dict_literals`
> 会在同类问题复发时失败。

### 4.5 指标口径（**已统一到 `metrics.py`，以下是现行口径**）

| 指标 | 现行公式 | 备注 |
|---|---|---|
| WHIP | `(BB+H) / 真实IP` | 标准定义用 BF，但本项目的 BF（面对打席）只有部分比赛有值；现按 `(BB+H)/IP` |
| OBP | `(H+BB+HBP) / (AB+BB+HBP+SF+SH)` | 分母**已含 SH**（旧版漏了） |
| SLG | `总垒数 / AB` | 总垒数 = 一垒安打 + 2×二垒 + 3×三垒 + 4×本垒打 |
| OPS | `OBP + SLG` | 一次舍入，不是 `round(OBP)+round(SLG)` |
| ERA | `ER×9 / 真实IP` | IP 必须**逐条**把记法字面值换成真实局数（`.1` = 1/3 局） |
| AVG | `H / AB` | — |

> ⚠️ **局数是最容易搞错的一条**：`game_records.innings_pitched` 存的是
> **记法字面值**（PDF 上印的 `.1` 就是 1/3 局），而档案里的
> `innings_pitched_total` 是**真实局数**。两者差着 2/3 局。
> 换算**必须逐条做** —— 各场小数位相加可能 ≥10 而进位
> （0.5+0.5 → 字面合计 1.0，换算后应是 3.333 局）。

### 4.6 统计公式散落 5 处 → **已收敛为 1 处**

**现状（Phase R3 起）**：全项目只有 `metrics.py` 一份公式来源。
`database.py` · `import_pdfs.py` · `app.py` · `migrate_profiles_sqlite.py` ·
`static/js/script.js` 全部改为调用它。

- 局数（IP）口径：`game_records.innings_pitched` 存的是**记法字面值**
  （`.1` = 1/3 局），与 PDF 一致；**聚合时逐条换算**成真实局数
  （不能对合计换算 —— 各场小数位相加可能 ≥10 而进位）。
  档案里的 `innings_pitched_total` 是**真实局数**。
- OBP 分母已含牺牲触击(SH)：`(H+BB+HBP) / (AB+BB+HBP+SF+SH)`。
- 有自动检查兜底：`tests/test_r3_metrics_and_import.py` 里的
  「指标唯一性」用 AST 扫 Python **和** JS，任何地方再自己算 ERA 都会让测试失败。

### 4.7 PDF 解析器有静默错误 → **已修**

- ~~解析器不使用列坐标，把双栏 PDF 压平成文本行后靠启发式猜我方~~
  → 现在是 `pdf_parser_columns.py`（按词坐标切栏），`pdf_ingest.py` 统一对外。
- ~~三垒打永不提取，且污染二垒打~~ → 已提取（`3B` 标签）。
- ~~HBP 合并两队 → 幻影数据~~ → 按栏切分，HBP 只取我方栏。
- ~~我方在右栏时，`win` 会抓到对手的胜投~~ → 已按栏归属。
- 独立校验：`python scripts/validate_pdf_parse.py` 用 PDF **自己**的 Totals 行当真值
  （打击 Totals 17/17 吻合、投手局数 16/17 吻合 —— 第 17 份是源 PDF 自相矛盾）。
- 局数 `1.1` 被当成 1.1 而不是 1⅓ 局（全局少算 5.6%）

**"17/17 解析零失败"恰恰是最危险的地方**——错误全部静默。

---

## 5. 开发约定（给学弟）

### 5.1 分支策略

```
main          —— 稳定可运行的版本（当前状态）
feature/xxx   —— 你的功能分支，从 main 切出
```

- 合并前跑 `python -m pytest tests/ -q`（62 个测试，必须全绿）
- **不要在 feature 分支上改 `instance/baseball_players.db`**（gitignored，但会影响本地运行）
- 数据库 schema 变更走 `flask db migrate`（已配置 Flask-Migrate）或写一次性脚本放 `scripts/`

### 5.2 加新接口的 checklist

- [ ] 写操作加 `@admin_required`，读操作不加
- [ ] 读操作**不需要** CSRF；写操作前端用 `api.post/put/del`（自动带 CSRF）
- [ ] 错误一律 `jsonify({'error': '中文消息'}), 400`
- [ ] 参数校验用 `request.args.get('x', type=int)`，非法值给 400
- [ ] 路径参数先过 `_safe_data_path()`（PDF 相关）或直接查库判 404
- [ ] 新统计指标写进 `database.py` 的 `update_calculated_fields()`，**不要**在 app.py 里现算
- [ ] 补一个测试到 `tests/test_<你的功能>_baseline.py`
- [ ] 更新本文的端点清单 + `API_DOCUMENTATION.md`

### 5.3 目录职责

| 路径 | 职责 | 注意 |
|---|---|---|
| `app.py` | 所有路由（约 1800 行） | **不要再往里塞东西**，新路由建议开 `blueprints/` |
| `database.py` | 模型 + 档案重建 + 迁移 | 指标公式在 `metrics.py`，别在这里另写一份（§4.6） |
| `metrics.py` | **唯一的指标公式来源** | 改公式只改这里；有 AST 检查兜底（§4.6） |
| `config.py` | 三套配置 | `TestingConfig` 关闭 CSRF，测不出来 |
| `static/js/api.js` | **唯一的 API 调用层** | 新代码别用裸 `fetch` |
| `static/js/toast.js` | **唯一的提示组件** | 别再用 `alert()` |
| `scripts/` | 一次性 / 运维脚本 | 破坏性脚本要加安全闸（参考 `migrate_profiles_sqlite.py`） |
| `tests/` | pytest 回归测试 | 见 §5.4 |

### 5.4 测试的隔离机制（**极其重要**）

`tests/conftest.py` 在 `import app` **之前**通过 `DATABASE_FILE` 环境变量
把数据库指向临时文件。

> ⚠️ Flask-SQLAlchemy 在 `init_app()` 里就 eager 创建 engine，
> **之后**再改 `app.config['SQLALCHEMY_DATABASE_URI']` **不生效**
> （官方文档原话："Changes to application config after this call will not be reflected"）。
>
> 早期版本的 conftest 正是踩了这个坑，`db.drop_all()` 打在了真实生产库上，
> 造成 2026-04 数据事故。详见 `docs/PHASE_R0_REPORT.md`。
>
> **改 `tests/conftest.py` 之前，请先读那份报告。**

三重防线：
1. `DATABASE_FILE` 环境变量物理隔离（`import app` 之前）
2. `_is_test_safe_path()` 拒绝任何路径含 `instance` 的 URI
3. session 级 fixture 比对生产库 SHA256，不一致立即 `RuntimeError`

`app.py` 也支持 `DATABASE_FILE` 覆盖：

```bash
DATABASE_FILE=/abs/path/to.db python app.py       # 绝对路径
DATABASE_FILE=other.db python app.py               # 相对 instance/
```

### 5.5 前端约定

- 模板默认**不继承** `base.html`（13 个模板里只有 `login` 和 `import_pdf` 继承了）
  —— 这是历史包袱，**新页面请继承 `base.html`**
- 所有页面已包含 `<meta name="csrf-token">` + `api.js` + `toast.js`
- Tailwind CDN + `static/css/arena.css`；**Bootstrap 已移除**，不要用 `btn-close` / `alert alert-*` / `.card` / `table-success` 这些类
- 渲染用户数据进 HTML 前**必须转义**（`players.html` 里有 `escapeHtml()` 参考实现）

---

## 6. 部署

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
export INIT_DEFAULT_ADMIN=0     # 账号建好后必须改 0
export ADMIN_PASSWORD='...'     # 首次启动建账号时用
python app.py
```

**生产必读**：
- `SECRET_KEY` 缺失 → **生产模式拒绝启动**（这是故意的）
- `FLASK_DEBUG` 必须为 `0`
- `INIT_DEFAULT_ADMIN` 部署完必须改成 `0`
- 速率限制：登录 5 次/分钟、API 60 次/分钟
- `instance/` 和 `data/` 需要挂载持久化卷

**Docker**（`Dockerfile` / `docker-compose.yml`）保留为历史回退方案，未做主动测试。

---

## 7. 变更记录

| 日期 | 变更 | 影响 |
|---|---|---|
| 2026-10-29 | **新增** `GET /batch_entry` 批量录入页面（粘贴 box score 一次写入整场比赛） | 新增能力，写入走既有 `POST /api/game_records/batch` |
| 2026-10-29 | **修复** `GET /api/game_records/<id>` 的 `'strikeouts'` 重复键（后者覆盖前者） | **破坏性修复**：打击记录的三振曾恒返回 0，导致对局页编辑保存时把打击三振抹成 0。现在按记录类型返回对应列 |
| 2026-10-29 | **行为变化** `PUT /api/players/<id>` 收窄为 metadata-only | **破坏性**：提交统计字段不再被静默接受，改为 **400 拒绝**并回传 `rejected_fields`。资料字段（name / jersey_number / is_pitcher / player_type / positions / primary_position）不受影响。累计数据改用比赛记录接口写入 |
| 2026-10-28 | **新增** `PUT /api/game_records/<id>`（编辑）+ 对局页「编辑」按钮与弹窗 | 新增能力，不影响已有调用 |
| 2026-10-28 | **新增** `POST /api/game_records/batch`（整场一次写入） | 新增能力，全有或全无 |
| 2026-10-28 | **新增** `GET /api/game_records/<id>`（取原始记录供编辑） | 新增能力 |
| 2026-10-28 | 比赛记录写入语义改为「写记录 + 从 game_records 重算档案」 | **行为变化**：删除记录不再用 `max(0,x)` 增量扣减，改用重算。统计结果一致但实现不同 |
| 2026-10-28 | `players` 表删除 34 个 legacy 统计死列（42 → 8 列） | **schema 变化**：那些列恒为 0，删了不影响任何读取 |
| 2026-10-28 | 修复前端 CSRF 缺失（此前所有写操作在生产配置下 400） | **破坏性**：如果你的前端用了裸 `fetch`，请改用 `api.*` |
| 2026-10-28 | 加载 DataTables（此前 `/game_stats` 正常时也误报"加载失败"） | 新增分页/排序/搜索 |
| 2026-10-28 | 移除 Bootstrap 残留类名，统一 `static/js/toast.js` | 视觉微调 |
| 2026-10-28 | `pitching_leaderboard` 的 `wins`/`losses` 由 `'N/A'` 改为真实聚合，新增 `saves`/`win_pct` | **字段类型变化**：`'N/A'`(str) → `0`(int) |
| 2026-10-28 | `app.py` 支持 `DATABASE_FILE` 环境变量覆盖数据库路径 | 新增能力，默认行为不变 |
| 2026-10-28 | `.gitignore` 从 UTF-16 转 UTF-8（此前所有忽略规则失效） | `recovery/`、`*.db-wal` 等新增忽略规则 |
| 2026-10-28 | matplotlib 强制 `Agg` 后端（此前 `/api/visualization/pitching` 会崩整个进程） | 修复 |
