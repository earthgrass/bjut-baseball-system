"""
测试基础设施 — Phase E0 Forensic Baseline

**绝对不能触碰 instance/baseball_players.db**（真实生产数据）

策略：
- 每个测试用 :memory: SQLite，db.create_all() 重建 schema
- 注入最小初始数据（位置字典 + 1 个 admin 用户）
- 通过 Flask test_client 走 HTTP 层（验证完整请求/响应/CSRF 链）
- CSRF token 从 HTML 表单或 meta 标签提取，模拟真实浏览器
"""
import os
import pytest

# 在导入 app 之前设置关键环境变量
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-do-not-use-in-prod'
os.environ['INIT_DEFAULT_ADMIN'] = '1'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'testpass'

from app import app as flask_app  # noqa: E402
from database import db, User, Position, init_positions  # noqa: E402
from config import TestingConfig  # noqa: E402


@pytest.fixture
def app():
    """每个测试一个全新的内存数据库"""
    flask_app.config.from_object(TestingConfig)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['WTF_CSRF_ENABLED'] = True  # 测试也走 CSRF（与生产对齐）
    flask_app.config['RATELIMIT_ENABLED'] = False  # 限流测试另写

    with flask_app.app_context():
        db.create_all()
        init_positions()
        # 创建 admin
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password('testpass')
            db.session.add(admin)
            db.session.commit()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


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