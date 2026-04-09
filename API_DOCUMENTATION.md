# 棒球队管理系统 API 文档

## 启动服务

### Docker 方式（推荐）

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务启动后访问：`http://localhost:5000`

---

## API 调用示例

以下使用 `curl` 命令演示，你也可以使用 Postman、Insomnia 或其他 API 测试工具。

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

#### 更新球员
```bash
curl -X PUT http://localhost:5000/api/players/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "jersey_number": "18",
    "is_pitcher": true,
    "positions": ["投手"],
    "primary_position": "投手",
    "at_bats_total": 50,
    "hits_total": 15,
    "home_runs_batting": 3,
    "rbi_total": 10
  }'
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

### 7. 调试接口

#### 查看所有球员（简化版）
```bash
curl http://localhost:5000/api/debug/players
```

#### 测试更新球员数据
```bash
curl -X POST http://localhost:5000/api/test/update_player \
  -H "Content-Type: application/json" \
  -d '{"home_runs_batting": 5, "rbi_total": 20}'
```

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