"""
测试基础设施 — Phase R0 Hardened

**绝对不能触碰 instance/baseball_players.db**（真实生产数据）

Phase R0 强化：
- session-scoped guard 监视真实 DB SHA256（每次 fixture 操作前后比对）
- 临时 DB 路径校验：必须位于 tests/.tmp/ 或 OS temp 目录
- 任何指向 instance/ 的 DB URI → fail-fast

历史教训（已记录于 Phase E0.5 commit message）：
原 conftest 用 sqlite:///:memory:，但 db.drop_all() 通过已绑定到真实 DB
的 SQLAlchemy engine 执行，把 instance/baseball_players.db 清空。
"""
import os
import tempfile
import shutil
import hashlib
from urllib.parse import unquote
import pytest


def _sqlite_path_from_uri(uri: str) -> str:
    """从 sqlite URI 里取出文件系统路径。

    ⚠️ **不能**直接 `uri.split('sqlite:///', 1)[-1]`：
    SQLAlchemy 2.1 起，`str(engine.url)` 会把 Windows 路径渲染成**百分号编码**
    （`sqlite:///C%3A%5CUsers%5C...`）。不解码就拿不到真实路径，
    路径判定会全线误判为「不安全」→ 所有用 app fixture 的测试集体 error
    （CI 首次运行就是这么红的）。

    这里用 SQLAlchemy 自己的 make_url 解析（取 url.database，它会解码），
    解析不了时再退回 split + unquote 兜底。
    """
    try:
        from sqlalchemy.engine import make_url
        url = make_url(uri)
        if url.get_backend_name() == 'sqlite':
            db_path = url.database
            if db_path:
                return db_path
    except Exception:
        pass

    path_part = uri.split('sqlite:///', 1)[-1]
    return unquote(path_part)


def _is_test_safe_path(uri: str) -> bool:
    """校验 SQLAlchemy URI 是否指向测试安全位置。

    规则：
    1. 必须是 sqlite:// URI
    2. :memory: 直接放行
    3. 解析出的绝对路径，其目录组件中不能出现 'instance'（真实生产库所在目录）
    4. 绝对路径必须位于 OS 临时目录或 tests/.tmp/ 之内

    注意：早期实现用子串匹配 '\\tmp\\'（大小写敏感），在 Windows 上临时目录是
    '...\\AppData\\Local\\Temp\\'，导致合法的临时库被误判为不安全。
    """
    if not uri:
        return False
    if not uri.lower().startswith('sqlite://'):
        return False

    if ':memory:' in uri.lower():
        return True

    path_part = _sqlite_path_from_uri(uri)
    if not path_part:
        return False
    abs_path = os.path.abspath(path_part)

    # 规则 3：按路径组件判断，避免 'myinstance' 之类的误伤
    if 'instance' in abs_path.lower().split(os.sep):
        return False

    # 规则 4：必须落在允许的临时根目录内
    allowed_roots = [
        os.path.abspath(tempfile.gettempdir()),
        os.path.abspath(os.path.join(os.path.dirname(__file__), '.tmp')),
    ]
    for root in allowed_roots:
        try:
            if os.path.commonpath([root, abs_path]) == root:
                return True
        except ValueError:
            # 不同盘符，commonpath 抛异常 → 该 root 不适用
            continue
    return False


# 在导入 app 之前，先把数据库指向临时文件
#
# 关键点：Flask-SQLAlchemy 在 init_app() 里就 eager 创建 engine，之后再改
# app.config['SQLALCHEMY_DATABASE_URI'] 不会生效。所以必须通过 DATABASE_FILE
# 环境变量在 import app 之前指定路径，否则 db.drop_all() 会打在真实生产库上。
_TMP_DB_DIR = tempfile.mkdtemp(prefix='baseball_test_')
_TMP_DB_PATH = os.path.join(_TMP_DB_DIR, 'test.db')

# 关键：在 app.py 加载之前禁用任何指向 instance/ 的 DB URI
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-do-not-use-in-prod'
os.environ['INIT_DEFAULT_ADMIN'] = '1'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'testpass'
os.environ['DATABASE_FILE'] = _TMP_DB_PATH  # ← 真正的隔离点（必须在 import app 之前）


def _real_db_sha256():
    real_db = os.path.join(os.path.dirname(__file__), '..', 'instance', 'baseball_players.db')
    real_db = os.path.abspath(real_db)
    if not os.path.exists(real_db):
        return None
    return hashlib.sha256(open(real_db, 'rb').read()).hexdigest()


@pytest.fixture(scope='session', autouse=True)
def patch_db_path():
    """session 级守卫：监控真实 DB 的 SHA256，启动任何测试前快照"""
    pre = _real_db_sha256()
    print(f'\\n[R0 canary] real DB SHA256 (pre-test): {pre}')

    yield

    post = _real_db_sha256()
    print(f'[R0 canary] real DB SHA256 (post-test): {post}')
    if pre != post:
        # FAIL-FAST: tests must never modify production DB
        raise RuntimeError(
            f'!!! PRODUCTION DB WAS MODIFIED DURING TESTS !!!\\n'
            f'pre  = {pre}\\n'
            f'post = {post}\\n'
            f'CHECK WHICH TEST WROTE TO instance/baseball_players.db'
        )


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

    # FAIL-FAST: assert URI is test-safe
    assert _is_test_safe_path(flask_app.config['SQLALCHEMY_DATABASE_URI']), (
        f'!!! UNSAFE DB URI: {flask_app.config["SQLALCHEMY_DATABASE_URI"]} !!! '
        f'Tests must use temp/test DB, never instance/'
    )

    with flask_app.app_context():
        # Dispose any engine that may have been created at import time
        db.engine.dispose()
        db.create_all()
        init_positions()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password('testpass')
            db.session.add(admin)
            db.session.commit()

        # Re-check URI after engine init
        actual_uri = str(db.engine.url)
        assert _is_test_safe_path(actual_uri), (
            f'!!! ENGINE BOUND TO UNSAFE URI: {actual_uri} !!!'
        )

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def pytest_sessionfinish(session, exitstatus):
    try:
        if os.path.exists(_TMP_DB_DIR):
            shutil.rmtree(_TMP_DB_DIR)
    except Exception as e:
        print(f'Warning: failed to clean temp dir: {e}')


# ============================================================
# Phase R0.10 — Canary test
# ============================================================
REAL_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                        'instance', 'baseball_players.db'))


@pytest.fixture
def real_db_sha_before():
    """快照真实 DB SHA256 在所有 fixture 之前"""
    if not os.path.exists(REAL_DB):
        return None
    return hashlib.sha256(open(REAL_DB, 'rb').read()).hexdigest()


@pytest.fixture
def real_db_sha_after(real_db_sha_before):
    """测试结束后 yield 之后验证 SHA256 未变"""
    yield
    if not os.path.exists(REAL_DB):
        assert real_db_sha_before is None
        return
    after = hashlib.sha256(open(REAL_DB, 'rb').read()).hexdigest()
    assert after == real_db_sha_before, (
        f'!!! REAL DB MODIFIED BY TESTS !!! '
        f'before={real_db_sha_before} after={after}'
    )


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