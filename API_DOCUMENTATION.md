# 棒球队管理系统 API 文档

> 📌 **先读 [`API_CONTRACT.md`](API_CONTRACT.md)** —— 那里是正式的接口契约
> （认证 / CSRF 规则、响应格式约定、状态码、已知问题、开发约定）。
> 本文只提供 curl 调用示例。

## 启动服务

### 本地开发（推荐，仅本机可访问）

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 SECRET_KEY
python run_local.py         # → http://127.0.0.1:5000
```

### 服务器部署

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
export INIT_DEFAULT_ADMIN=0
python app.py               # 绑定 0.0.0.0
```

### Docker（历史回退方案，未做主动测试）

```bash
docker-compose up -d --build
docker-compose logs -f
docker-compose down
```

---

## API 调用示例

以下使用 `curl` 命令演示，你也可以使用 Postman、Insomnia 或其他 API 测试工具。

> **认证说明**：所有 `POST`/`PUT`/`DELETE` 的写接口需要管理员登录获取 session cookie（`POST /login`）。
> 登录后浏览器会自动带 cookie；使用 curl 时用 `-c cookies.txt -b cookies.txt` 保存/携带。
> 所有写接口均通过 `@admin_required` 装饰器保护，未登录返回 302 重定向到 `/login`。
>
> **CSRF 说明（重要）**：后端全局启用了 `CSRFProtect`，且 `/api/*` 没有豁免。
> **所有写接口必须额外带 `X-CSRFToken` 请求头**，否则返回 400「The CSRF token is missing」。
> Token 从任意页面的 `<meta name="csrf-token" content="...">` 取得。
>
> ```bash
> # 取 token 并登录
> TOKEN=$(curl -s -c cookies.txt http://127.0.0.1:5000/login \
>         | grep -oP 'name="csrf-token" content="\K[^"]+')
> curl -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:5000/login \
>     -d "csrf_token=$TOKEN" -d "username=admin" -d "password=你的密码"
>
> # 之后写操作都要带 header
> curl -b cookies.txt -X POST http://127.0.0.1:5000/api/players \
>     -H "Content-Type: application/json" \
>     -H "X-CSRFToken: $TOKEN" \
>     -d '{"name":"张三","jersey_number":"18","player_type":"fielder","positions":["游击手"],"primary_position":"游击手"}'
> ```

### 1. 球员管理

#### 获取所有球员
```bash
curl http://localhost:5000/api/players
```

#### 添加球员
```bash
curl -X POST http://localhost:5000/api/players \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "jersey_number": "18",
    "player_type": "pitcher",
    "positions": ["投手", "外野手"],
    "primary_position": "投手"
  }'
```

#### 更新球员（只改资料）

> **2026-10-29 起**：该接口**只接受资料字段**。统计字段（`at_bats_total` 等）
> 会被 **400 拒绝** —— 累计数据是 `game_records` 的派生值，只能通过比赛记录接口写入
> （`POST /api/game_records` / `POST /api/game_records/batch` / `PUT /api/game_records/<id>`）。

```bash
curl -X PUT http://localhost:5000/api/players/1 \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" -b cookies.txt \
  -d '{
    "name": "张三",
    "jersey_number": "18",
    "is_pitcher": true,
    "positions": ["投手"],
    "primary_position": "投手"
  }'
```

提交统计字段会得到：

```json
{
  "error": "统计字段不能通过球员接口写入。累计数据只能由比赛记录推导，请改用 POST /api/game_records 或 POST /api/game_records/batch。",
  "rejected_fields": ["at_bats_total"]
}
```

#### 删除球员
```bash
curl -X DELETE http://localhost:5000/api/players/1
```

#### 获取打击球员列表
```bash
curl http://localhost:5000/api/players/batters
```

#### 获取投手列表
```bash
curl http://localhost:5000/api/players/pitchers
```

---

### 2. 比赛记录

#### 添加打击记录
```bash
curl -X POST http://localhost:5000/api/game_records \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": 1,
    "game_date": "2025-04-07",
    "opponent": "清华大学",
    "is_pitching": false,
    "at_bats": 4,
    "runs": 2,
    "hits": 3,
    "rbi": 2,
    "walks": 1,
    "strikeouts": 0,
    "doubles": 1,
    "triples": 0,
    "home_runs_game": 1,
    "stolen_bases_game": 1,
    "hit_by_pitch": 0
  }'
```

#### 添加投手记录
```bash
curl -X POST http://localhost:5000/api/game_records \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": 1,
    "game_date": "2025-04-07",
    "opponent": "清华大学",
    "is_pitching": true,
    "innings_pitched": 7.0,
    "hits_allowed": 5,
    "runs_allowed": 2,
    "earned_runs": 1,
    "walks_allowed": 2,
    "strikeouts": 8,
    "home_runs_allowed": 1,
    "pitches": 95,
    "strikes": 62,
    "win": true
  }'
```

---

### 3. 统计数据

#### 打击统计
```bash
curl http://localhost:5000/api/stats/batting
```

#### 投球统计
```bash
curl http://localhost:5000/api/stats/pitching
```

#### 打击排行榜
```bash
curl http://localhost:5000/api/stats/batting_leaderboard
```

#### 投手排行榜
```bash
curl http://localhost:5000/api/stats/pitching_leaderboard
```

#### 可视化图表（返回 base64 图片）
```bash
curl http://localhost:5000/api/stats/visualization
```

#### 打击可视化
```bash
curl http://localhost:5000/api/visualization/batting
```

#### 投球可视化
```bash
curl http://localhost:5000/api/visualization/pitching
```

---

### 4. 对局信息

#### 获取所有对手
```bash
curl http://localhost:5000/api/matchup/opponents
```

#### 按球员查询比赛记录
```bash
curl "http://localhost:5000/api/matchup/search_records?player_id=1"
```

#### 按对手查询比赛记录
```bash
curl "http://localhost:5000/api/matchup/search_records?opponent=清华大学"
```

#### 按球员+对手组合查询
```bash
curl "http://localhost:5000/api/matchup/search_records?player_id=1&opponent=清华大学"
```

#### 获取全队所有比赛记录
```bash
curl http://localhost:5000/api/matchup/all_game_records
```

#### 删除比赛记录
```bash
curl -X DELETE http://localhost:5000/api/matchup/game_record/1
```

---

### 5. PDF 相关

#### 获取 PDF 文件列表
```bash
curl http://localhost:5000/api/pdf/files
```

#### 解析单个 PDF（预览，不写入数据库）
```bash
curl http://localhost:5000/api/pdf/parse/2025/北京工业大学_vs_北京科技大学_Nov_15_2025.pdf
```

#### 导入单个 PDF 到数据库
```bash
curl -X POST http://localhost:5000/api/pdf/import_one \
  -H "Content-Type: application/json" \
  -d '{"filepath": "2025/北京工业大学_vs_北京科技大学_Nov_15_2025.pdf"}'
```

#### 批量导入所有 PDF（预览模式）
```bash
curl -X POST http://localhost:5000/api/pdf/import_all \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

#### 批量导入所有 PDF（实际导入）
```bash
curl -X POST http://localhost:5000/api/pdf/import_all \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

---

### 6. 数据导出

#### 导出 CSV
```bash
curl http://localhost:5000/api/export/csv -o players.csv
```

---

### 7. 调试接口（已删除）

> ⚠️ 以下调试接口已移除以提升安全性，请使用对应的正式接口：
> - ~~`/api/debug/players`~~ → 用 `/api/players`
> - ~~`/api/test/update_player`~~ → 用 `PUT /api/players/<id>`（需登录）

---

## 常见问题

### Q: Docker 启动后无法访问？
检查端口是否被占用：
```bash
# Windows
netstat -ano | findstr :5000

# 如果被占用，修改 docker-compose.yml 中的端口映射
# 例如改为 "5001:5000"
```

### Q: 如何查看容器日志？
```bash
docker-compose logs -f
```

### Q: 如何进入容器内部调试？
```bash
docker exec -it baseball-team-management bash
```

### Q: 如何重置数据库？
```bash
# 停止容器
docker-compose down

# 删除数据库文件
rm -rf instance/baseball_players.db

# 重新启动（会自动创建新数据库）
docker-compose up -d

# 或者在容器内执行
docker exec -it baseball-team-management python init_db.py
```

---

## Python 调用示例

```python
import requests

BASE_URL = "http://localhost:5000"

# 获取所有球员
response = requests.get(f"{BASE_URL}/api/players")
players = response.json()
print(players)

# 添加球员
new_player = {
    "name": "李四",
    "jersey_number": "10",
    "player_type": "fielder",
    "positions": ["游击手"],
    "primary_position": "游击手"
}
response = requests.post(f"{BASE_URL}/api/players", json=new_player)
print(response.json())

# 添加比赛记录
game_record = {
    "player_id": 1,
    "game_date": "2025-04-07",
    "opponent": "清华大学",
    "is_pitching": False,
    "at_bats": 4,
    "hits": 2,
    "rbi": 1
}
response = requests.post(f"{BASE_URL}/api/game_records", json=game_record)
print(response.json())
```