# 交接说明 — 2026-10-28 存档点

> 这是**明天的起点**。从这里接着做即可，不必从头回溯。

---

## 一、当前状态：可运行

```bash
pip install -r requirements.txt
cp .env.example .env          # SECRET_KEY 已填好；SECRET_KEY 是本机自签名的，泄露无所谓
python run_local.py           # → http://127.0.0.1:5000
```

管理员：`admin` / `admin123`（本机开发用；公网前必须改）

**验证状态**：
- 74 个 pytest 全绿
- 11 个页面 + 27 个 API 端点全部 200
- 端到端验证：登录 → 新增 → 编辑 → 批量 → 删除 → 登出 全通
- 不变量 `profile == SUM(game_records)` 成立（351 = 351）

---

## 二、这一轮做完了什么

### 修好了（此前系统是"只能读不能写"）

| 问题 | 原因 |
|---|---|
| **所有写操作 400** | `app.py:126` 全局 CSRF，但 `static/js/api.js` 从没被任何模板 include，`<meta name="csrf-token">` 只有 `base.html` 有。而 `config.py:38` 的 TestingConfig 关掉了 CSRF，**测试测不出来** |
| **登出也是坏的** | 20 个 POST 表单全无 CSRF 字段 |
| `/api/visualization/pitching` 崩整个进程 | matplotlib 在 Windows 选 TkAgg，worker 线程建图时 Tk 清理 abort 进程 → 强制 `Agg` |
| `/game_stats` 正常时也报"加载失败" | DataTables 的 CDN 一次都没引过 |
| Toast / 图表卡 / 排行榜榜首无样式 | Bootstrap 已移除但类名残留 |
| 表单 `required`/`min` 永不触发 | 提交按钮是 `type="button"` |
| 首页 API 失败时显示编造数据 | 「张伟/李强/王磊/.312」→ 换成明确错误态 |
| 存储型 XSS | `${player.name}` 直接进 innerHTML |
| `.gitignore` 全部失效 | 文件是 UTF-16 编码，Git 解析不了 → `.env`、真实数据库都能被误提交 |
| `players` 表 34 个 legacy 死列 | 已删（42 → 8 列），你之前看到"数据是空的"就是因为它们恒为 0 |
| `migrate_profiles_sqlite.py` 是地雷 | 现在跑会把**全队统计清零** → 已加安全闸 |

### 新增了写入能力

| 端点 | 说明 |
|---|---|
| `PUT /api/game_records/<id>` | **编辑**比赛记录（此前只能新增/删除）—— 对局页已有「编辑」按钮 + 弹窗 |
| `POST /api/game_records/batch` | **整场比赛一次写入**（打击+投球混合），全有或全无 |
| `GET /api/game_records/<id>` | 取原始记录供编辑 |

**写入语义重构**（重要）：写操作现在**只写 `game_records`**，统计档案一律用
`rebuild_player_stats()` 从 `game_records` 重算，**不做增量 +/-**。
恒等式 `profile == SUM(game_records)` 永远成立。
旧的 DELETE 用 `max(0,x)` 扣减会掩盖漂移，已改。

---

## 三、明天接着做（按建议顺序）

### 立刻能做的（约 1-2 小时）

1. **批量录入的前端界面** —— 后端接口已就绪（`API_CONTRACT.md` §3.2），
   但还没有 UI。可选方案：
   - 多行表格（像 Excel）
   - **粘贴框**：接受与 PDF 打击表相同的格式 `姓名 AB R H RBI BB SO`
     （这个团队本来就在看这种 box score，复制粘贴最顺手）
2. **`PUT /api/players/<id>` 收窄** —— 目前它仍会直接覆盖 profile 累计，
   是**唯一**还在绕过 GameRecord 的写入口。改成只允许改
   `name`/`jersey_number`/`positions`/`primary_position`
   （`docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` 的 Phase C5）

### 中等工程量（1-2 天）

3. **PDF 解析器改用列坐标**（`FEATURE_PROPOSALS.md` F7a）——
   **性价比最高的一项**，能一次性修掉 8 个静默数据错误，
   并且**重导 17 份 PDF 就能修正全部 230 条历史数据**
   （局数少算 5.6%、三垒打全丢、HBP 幻影、投球数丢失、胜负记错）
4. **指标引擎**（F3）—— 把散在 5 处的公式收成一处，顺带修 WHIP 分母、
   OBP 漏 SH。依赖第 3 步（BF 数据要靠列坐标才有）
5. **DataTables 加到 players / matchup 页面** —— 现在只有 game_stats 有分页

### 需要先跟你确认的

6. **player 28 在 2024-11-16 对北京交通大学的 2 条重复** —— 重复导入（删一条）
   还是双赛日（归入两场 Game）？取证报告标为 AMBIGUOUS，脚本不能自动判
7. **`欧阳` vs `欧阳翦`** —— PDF 里两人都是 #23，同一人被拆成两行还是两人共用号码？
8. **赛季怎么切** —— 4 月春季 + 10/11 月秋季的学期制是否成立？

---

## 四、必须知道的坑（别踩）

### Flask-SQLAlchemy 的 engine 绑定时机

`init_app()` 里就 eager 创建 engine，**之后**再改
`app.config['SQLALCHEMY_DATABASE_URI']` **不生效**（官方文档原话：
"Changes to application config after this call will not be reflected"）。

早期版本的 `tests/conftest.py` 正是在 `import app` **之后**才覆盖 URI，
导致 `db.drop_all()` 打中真实生产库 → 2026-04 数据事故。

**现在**：用 `DATABASE_FILE` 环境变量，在 `import app` **之前**指定路径。
改 `tests/conftest.py` 之前请先读 `docs/PHASE_R0_REPORT.md`。

### 测试测不出 CSRF 问题

`config.py` 的 `TestingConfig` 有 `WTF_CSRF_ENABLED = False`。
写新接口请**在浏览器里实际点一次**，别只看测试。

### PDF 解析"零失败"是最危险的

17/17 解析成功、0 异常，但数据静默错误。**解析成功 ≠ 数据正确。**

### 公式有 5 份拷贝

`database.py:334-418`（权威）· `import_pdfs.py` · `app.py` ·
`static/js/script.js`（前端预览）· `migrate_profiles_sqlite.py`。
**改一个指标要同步改 5 处**（含前端那份）。

### `recovery/` 是只读取证快照

绝对不要改动或删除。`git_bb429ba_db.bin` 是 R0 恢复源。

---

## 五、文档地图

| 文档 | 内容 |
|---|---|
| `README.md` | 项目总览、快速开始、功能、已知问题 |
| `API_CONTRACT.md` | **接手必读** —— 接口契约、认证/CSRF、已知问题、开发约定 |
| `API_DOCUMENTATION.md` | curl 调用示例 |
| `FEATURE_PROPOSALS.md` | 10 个新功能提案 + 四维评估 + PDF 根因分析 |
| `docs/PHASE_R0_REPORT.md` | 数据事故时间线与取证（改 conftest 前必读） |
| `docs/DB_INVENTORY.md` | 16 个数据库文件盘点 |
| `docs/DOMAIN_AND_ARCHITECTURE_DESIGN.md` | 作者的 Phase C 蓝图（Game 实体 / Service 层） |

---

## 六、Git 状态

本轮改动已提交到 `main`（见 `git log`）。学弟从 `main` 切分支：

```bash
git checkout main && git pull
git checkout -b feature/xxx
```
