"""
端到端验证 —— 打在**副本**上，绝不打生产库（Phase R4，审计 #14）
=================================================================
为什么重写：
    仓库里原来的 `instance/_verify_e2e.py` / `instance/_verify_writes.py` 用
    硬编码的 `admin/admin123` 打 `127.0.0.1:5000` —— 那个服务器通常就是连着
    **生产库**跑起来的，谁跑一次就真的写坏统计。
    「端到端验证」本身是有价值的，危险的是它打在哪。

做什么：
    1. 记下生产库 SHA256；
    2. 把生产库**复制**一份到临时目录；
    3. 让应用连着副本跑（`DATABASE_FILE` 指向副本，且在 import app 之前设好）；
    4. 用 Flask test_client 走一遍真实流程：登录 → CSRF → 写入 → 读回 → 删除；
    5. 校验「档案 == SUM(game_records)」等不变量；
    6. 复验生产库 SHA256 未变，清理副本。

用法：
    python scripts/verify_e2e.py
"""
import os
import sys
import io
import shutil
import json
import hashlib
import tempfile
import re
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

# ⚠️ 只在**直接运行**时重定向 stdout —— 作为模块被 import 时劫持 sys.stdout
# 会破坏 pytest 的输出捕获（实测整个测试会话崩在 teardown）。
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


PROD_DB = os.path.join(ROOT, 'instance', 'baseball_players.db')

RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    print(f'  {"PASS" if ok else "FAIL"}  {name}' + (f'  — {detail}' if detail else ''))
    return ok


def sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class CsrfClient:
    """自动带 CSRF token 的 test_client（应用走的是真实的 Flask 栈）。"""

    def __init__(self, app):
        self.app = app
        self.client = app.test_client()
        self.token = None

    def get(self, path, **kw):
        return self.client.get(path, **kw)

    def _csrf(self):
        if self.token:
            return self.token
        resp = self.client.get('/login')
        html = resp.data.decode('utf-8', 'replace')
        m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.token = m.group(1) if m else None
        return self.token

    def post(self, path, json_body=None, **kw):
        headers = kw.pop('headers', {})
        token = self._csrf()
        if token:
            headers['X-CSRFToken'] = token
        if json_body is not None:
            headers['Content-Type'] = 'application/json'
            kw['data'] = json.dumps(json_body)
        return self.client.post(path, headers=headers, **kw)

    def post_form(self, path, fields):
        """表单 POST（登录走这条：login_submit 读的是 request.form）。"""
        token = self._csrf()
        data = dict(fields)
        if token:
            data['csrf_token'] = token
        headers = {}
        if token:
            headers['X-CSRFToken'] = token
        return self.client.post(path, data=data, headers=headers)

    def put(self, path, json_body=None, **kw):
        headers = kw.pop('headers', {})
        token = self._csrf()
        if token:
            headers['X-CSRFToken'] = token
        if json_body is not None:
            headers['Content-Type'] = 'application/json'
            kw['data'] = json.dumps(json_body)
        return self.client.put(path, headers=headers, **kw)

    def delete(self, path, **kw):
        headers = kw.pop('headers', {})
        token = self._csrf()
        if token:
            headers['X-CSRFToken'] = token
        return self.client.delete(path, headers=headers, **kw)


def main():
    prod_before = sha256(PROD_DB)
    print(f'生产库 SHA256 (验证前): {prod_before}')

    if not os.path.exists(PROD_DB):
        print('✗ 生产库不存在，无法验证')
        return 1

    scratch_dir = tempfile.mkdtemp(prefix='baseball_e2e_')
    scratch_db = os.path.join(scratch_dir, 'scratch.db')
    shutil.copy2(PROD_DB, scratch_db)
    print(f'副本: {scratch_db}\n')

    # ⚠️ DATABASE_FILE 必须在 import app **之前**设好（engine 在 init_app 里就绑定了）
    os.environ['DATABASE_FILE'] = scratch_db
    os.environ.setdefault('SECRET_KEY', 'e2e-verify-local-only')
    os.environ['INIT_DEFAULT_ADMIN'] = '1'
    os.environ['ADMIN_USERNAME'] = 'admin'
    os.environ['ADMIN_PASSWORD'] = 'admin123'

    from app import app
    from database import Player, GameRecord, db

    print('=== 1. 页面渲染（匿名） ===')
    c = CsrfClient(app)
    resp = c.get('/login')
    record('页面 /login 可渲染', resp.status_code == 200, f'HTTP {resp.status_code}')
    # 管理页在未登录时**应该**重定向到登录页（302），这是正确行为
    resp = c.get('/batch_entry')
    record('未登录访问管理页被拦截 (302)', resp.status_code == 302,
           f'HTTP {resp.status_code}')

    print('\n=== 2. 登录 ===')
    # login_submit 读的是 request.form —— 必须用表单 POST，不是 JSON
    resp = c.post_form('/login', {'username': 'admin', 'password': 'admin123'})
    record('管理员可登录', resp.status_code in (200, 302), f'HTTP {resp.status_code}')

    print('\n=== 2b. 页面渲染（登录后） ===')
    for path in ['/players', '/add_player', '/game_stats', '/add_game_record',
                 '/batch_entry', '/stats', '/matchup_stats', '/pdf_viewer',
                 '/import_pdf', '/upload_pdf']:
        resp = c.get(path)
        record(f'页面 {path} 可渲染', resp.status_code == 200, f'HTTP {resp.status_code}')

    print('\n=== 3. 写入 → 读回 ===')
    stamp = date.today().isoformat()
    resp = c.post('/api/players', json_body={
        'name': 'E2E验证员', 'jersey_number': '99', 'is_pitcher': False,
        'positions': ['游击手'], 'primary_position': '游击手'})
    ok = resp.status_code == 201
    player_id = resp.get_json()['player']['id'] if ok else None
    record('创建球员', ok, f'HTTP {resp.status_code}')

    resp = c.post('/api/game_records', json_body={
        'player_id': player_id, 'game_date': stamp, 'opponent': 'E2E对手',
        'is_pitching': False, 'at_bats': 4, 'runs': 1, 'hits': 2,
        'rbi': 1, 'walks': 1, 'strikeouts': 0, 'doubles': 1, 'triples': 0,
        'home_runs': 0, 'total_bases': 3, 'stolen_bases': 0, 'caught_stealing': 0,
        'hit_by_pitch': 0})
    ok = resp.status_code == 201
    record_id = resp.get_json().get('record_id') if ok else None
    record('创建比赛记录', ok, f'HTTP {resp.status_code}')

    if record_id:
        resp = c.get(f'/api/game_records/{record_id}')
        data = resp.get_json() if resp.status_code == 200 else {}
        record('记录可读回', resp.status_code == 200 and data.get('at_bats') == 4,
               f'HTTP {resp.status_code} at_bats={data.get("at_bats")}')
        record('打击三振字段不丢（重复键 bug 回归）',
               'strikeouts' in data and 'strikeouts_batting' not in data,
               f'keys={sorted(k for k in data if "strike" in k)}')

    print('\n=== 4. 不变量：档案 == SUM(game_records) ===')
    with app.app_context():
        pid = player_id
        player = db.session.get(Player, pid) if pid else None
        total = db.session.query(db.func.coalesce(db.func.sum(GameRecord.at_bats), 0)).filter(
            GameRecord.player_id == pid,
            GameRecord.is_pitching_record.is_(False)).scalar() if pid else 0
        profile_ab = player.at_bats_total if player else None
        record('档案累计 == 记录之和', profile_ab == total,
               f'profile={profile_ab} sum={total}')

    print('\n=== 5. PUT /api/players 只允许 metadata ===')
    # 档案字段名（如 at_bats_total）→ 直接 400 拒绝
    resp = c.put(f'/api/players/{player_id}',
                 json_body={'name': 'E2E改名', 'at_bats_total': 999})
    record('档案统计字段被拒绝 (400)', resp.status_code == 400, f'HTTP {resp.status_code}')
    # 比赛记录风格的字段名（如 at_bats）→ 不写库，但必须在响应里点名
    resp = c.put(f'/api/players/{player_id}', json_body={'at_bats': 999})
    body = resp.get_json() if resp.status_code == 200 else {}
    record('未知字段被显式点名 (ignored_fields)',
           resp.status_code == 200 and 'at_bats' in (body.get('ignored_fields') or []),
           f'HTTP {resp.status_code} ignored={body.get("ignored_fields")}')

    print('\n=== 6. 删除清理 ===')
    if record_id:
        # 删除比赛记录的路由在 matchup 蓝图下（DELETE /api/game_records/<id> 不存在）
        resp = c.delete(f'/api/matchup/game_record/{record_id}')
        record('删除比赛记录', resp.status_code in (200, 204), f'HTTP {resp.status_code}')
    if player_id:
        resp = c.delete(f'/api/players/{player_id}')
        record('删除球员', resp.status_code in (200, 204), f'HTTP {resp.status_code}')

    print('\n=== 7. 只读端点抽查 ===')
    for path in ['/api/players', '/api/stats/batting', '/api/stats/pitching',
                 '/api/pdf/files', '/api/matchup/opponents']:
        resp = c.get(path)
        record(f'端点 {path}', resp.status_code == 200, f'HTTP {resp.status_code}')

    print('\n=== 8. PDF 解析端点 ===')
    pdf_dir = os.path.join(ROOT, 'data')
    pdfs = []
    for root, _dirs, files in os.walk(pdf_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdfs.append(os.path.join(root, f))
    if pdfs:
        rel = os.path.relpath(sorted(pdfs)[0], pdf_dir).replace('\\', '/')
        resp = c.get(f'/api/pdf/parse/{rel}')
        body = resp.get_json() if resp.status_code in (200, 400) else {}
        has_error = 'error' in body
        record('PDF 解析端点可用', resp.status_code in (200, 400),
               f'HTTP {resp.status_code} {rel}')
        record('解析失败时不泄漏服务器绝对路径',
               not has_error or ROOT not in str(body.get('error', '')),
               str(body.get('error', ''))[:80])

    print('\n=== 9. 生产库未被触碰 ===')
    prod_after = sha256(PROD_DB)
    record('生产库 SHA256 未变', prod_before == prod_after,
           f'{str(prod_before)[:16]}… → {str(prod_after)[:16]}…')

    shutil.rmtree(scratch_dir, ignore_errors=True)

    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    total_n = len(RESULTS)
    print(f'\n结果: {passed}/{total_n} 通过')
    if passed != total_n:
        print('✗ 有检查未通过')
        return 1
    print('✓ 全部通过（生产库未变）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
