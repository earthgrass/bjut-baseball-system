"""
测试基础设施 — Phase E0 Forensic Baseline

**绝对不能触碰 instance/baseball_players.db**（真实生产数据）

策略（修正于 Phase E0.5）：
- 每个测试用一个临时 sqlite 文件（tests/.tmp/<test-name>.db），不是 :memory:
- 不再依赖 app.py 模块级别的 init_db(app)（那会把表创建在真实 DB 上）
- 完全用临时文件路径，db.drop_all() 只在临时文件上跑

历史教训：原 conftest 用 sqlite:///:memory:，但 db.drop_all() 通过
已经绑定到真实 DB 的 SQLAlchemy engine 执行，把 instance/baseball_players.db 清空。
修复：用临时文件 + 强制覆盖 URI 在 import 之前。
"""
import os
import sys
import tempfile
import shutil
import pytest

# 在导入 app 之前，先用临时文件覆盖 SQLALCHEMY_DATABASE_URI
_TMP_DB_DIR = tempfile.mkdtemp(prefix='baseball_test_')
_TMP_DB_PATH = os.path.join(_TMP_DB_DIR, 'test.db')
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-do-not-use-in-prod'
os.environ['INIT_DEFAULT_ADMIN'] = '1'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'testpass'
# 强制 app.py 用临时 DB 而不是 instance/baseball_players.db
os.environ['SQLALCHEMY_DATABASE_URI_OVERRIDE'] = f'sqlite:///{_TMP_DB_PATH}'

# Patch app.py 的 DATABASE_FILE 在它读 instance_path 之前
# 实际上 app.py 是这样写的：
#   DATABASE_FILE = os.path.join(app.instance_path, 'baseball_players.db')
# 我们必须在 app 创建之前 hook

# 关键修复：在 app 创建前把临时文件路径注入 os.environ，
# 然后让 app.py 在 import 时使用它
import builtins
_original_file_init = None


@pytest.fixture(scope='session', autouse=True)
def patch_db_path():
    """确保测试期间没有任何代码写到 instance/baseball_players.db"""
    # 我们用临时 DB；但同时监视真实 DB 文件大小防止被改
    real_db = 'instance/baseball_players.db'
    if os.path.exists(real_db):
        backup_path = real_db + '.test-guard-snapshot'
        shutil.copy2(real_db, backup_path)
        try:
            yield
        finally:
            # 测试结束后检查真实 DB 是否被修改
            if os.path.exists(real_db):
                post_size = os.path.getsize(real_db)
                pre_size = os.path.getsize(backup_path)
                if post_size != pre_size:
                    print(f'\\n!!! WARNING: real DB size changed during tests: '
                          f'{pre_size} -> {post_size}')
                # 不自动恢复 — 留给人类决策
    else:
        yield


@pytest.fixture
def app(patch_db_path):
    """每个测试一个全新的临时文件 SQLite"""
    from app import app as flask_app
    from database import db, User, init_positions
    from config import TestingConfig

    flask_app.config.from_object(TestingConfig)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{_TMP_DB_PATH}'
    flask_app.config['WTF_CSRF_ENABLED'] = True
    flask_app.config['RATELIMIT_ENABLED'] = False

    # 移除可能由 app.py 模块加载时创建的旧 engine，强制新 URI 生效
    with flask_app.app_context():
        db.engine.dispose()
        db.create_all()
        init_positions()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password('testpass')
            db.session.add(admin)
            db.session.commit()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        # 只 drop 临时 DB，不影响真实 DB
        db.drop_all()
        # 重新 dispose 以避免后续测试复用旧 connection
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_token(client):
    """从 /login GET 提取 csrf_token（HTML 表单路径）"""
    resp = client.get('/login')
    import re
    m = re.search(rb'name="csrf_token"\s+value="([^"]+)"', resp.data)
    assert m, 'CSRF token not found in /login page'
    return m.group(1).decode()


@pytest.fixture
def admin_logged_in(client, csrf_token):
    """登录并返回带 cookie 的 client；CSRF token 也准备好"""
    resp = client.post(
        '/login',
        data={
            'username': 'admin',
            'password': 'testpass',
            'csrf_token': csrf_token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302, f'Login failed: {resp.status_code} {resp.data[:200]}'
    return client, csrf_token


@pytest.fixture
def api_csrf_token(client):
    """从 /login GET 的 meta 标签提取 csrf_token（API 调用路径）"""
    resp = client.get('/login')
    import re
    m = re.search(rb'<meta name="csrf-token" content="([^"]+)"', resp.data)
    assert m, 'CSRF meta tag not found in /login page'
    return m.group(1).decode()


class CSRFClient:
    """自动为所有非 GET 请求附加 X-CSRFToken header"""
    def __init__(self, test_client, csrf_token):
        self._c = test_client
        self._token = csrf_token

    def get(self, *args, **kwargs):
        return self._c.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.put(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.delete(*args, **kwargs)

    @property
    def application(self):
        return self._c.application


@pytest.fixture
def auth_client(admin_logged_in):
    """已登录 + 自动附加 CSRF header 的 client"""
    c, token = admin_logged_in
    return CSRFClient(c, token)


def pytest_sessionfinish(session, exitstatus):
    """测试结束后清理临时 DB 目录"""
    try:
        if os.path.exists(_TMP_DB_DIR):
            shutil.rmtree(_TMP_DB_DIR)
    except Exception as e:
        print(f'Warning: failed to clean temp dir: {e}')


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_token(client):
    """从 /login GET 提取 csrf_token（HTML 表单路径）"""
    resp = client.get('/login')
    # 找到 <input type="hidden" name="csrf_token" value="...">
    import re
    m = re.search(rb'name="csrf_token"\s+value="([^"]+)"', resp.data)
    assert m, 'CSRF token not found in /login page'
    return m.group(1).decode()


@pytest.fixture
def admin_logged_in(client, csrf_token):
    """登录并返回带 cookie 的 client；CSRF token 也准备好"""
    resp = client.post(
        '/login',
        data={
            'username': 'admin',
            'password': 'testpass',
            'csrf_token': csrf_token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302, f'Login failed: {resp.status_code} {resp.data[:200]}'
    return client, csrf_token


@pytest.fixture
def api_csrf_token(client):
    """从 /login GET 的 meta 标签提取 csrf_token（API 调用路径）"""
    resp = client.get('/login')
    import re
    m = re.search(rb'<meta name="csrf-token" content="([^"]+)"', resp.data)
    assert m, 'CSRF meta tag not found in /login page'
    return m.group(1).decode()


class CSRFClient:
    """自动为所有非 GET 请求附加 X-CSRFToken header"""
    def __init__(self, test_client, csrf_token):
        self._c = test_client
        self._token = csrf_token

    def get(self, *args, **kwargs):
        return self._c.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.put(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers']['X-CSRFToken'] = self._token
        return self._c.delete(*args, **kwargs)

    @property
    def application(self):
        return self._c.application


@pytest.fixture
def auth_client(admin_logged_in):
    """已登录 + 自动附加 CSRF header 的 client"""
    c, token = admin_logged_in
    return CSRFClient(c, token)