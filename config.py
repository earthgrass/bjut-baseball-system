"""应用配置类（Phase B3）

集中管理从环境变量派生的所有配置项。
app.py 根据 FLASK_ENV 选择具体配置类。
"""
import os


class Config:
    """基础配置 — 所有环境共用"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY')  # app.py 已处理默认值
    JSON_AS_ASCII = False  # 中文 JSON 响应保持原样

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 速率限制
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_API', '60/minute')
    RATELIMIT_LOGIN = os.environ.get('RATELIMIT_LOGIN', '5/minute')
    # ⚠️ `memory://` 的限制（审计 #29）：限流计数存在**进程内存**里 ——
    #   多 worker / 多进程部署时每个进程各算各的（等效于没限流），
    #   进程重启即清零。当前部署（python app.py / run.py）是单进程线程模型，
    #   内存存储够用；一旦上 gunicorn -w 4 或多容器，必须换成共享存储：
    #       RATELIMIT_STORAGE_URI=redis://host:6379
    #   注意：limits 5.8 没有 filesystem 后端，只有 memory/redis/memcached/mongodb。
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    # 会话 Cookie（审计 #28）
    #   HttpOnly —— Flask 默认已是 True；显式写出来是为了让后来人知道它是有意的
    #   SameSite=Lax —— 默认是 None（偏弱），改成 Lax 挡掉大部分跨站带 cookie
    #   Secure —— 默认 0：本机开发走 http://127.0.0.1，设成 1 会让浏览器直接丢弃
    #              session cookie（表现为「登录后立刻掉登录」）。
    #              **走 HTTPS 的公网部署必须设 SESSION_COOKIE_SECURE=1。**
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.environ.get(
        'SESSION_COOKIE_SECURE', '0').strip().lower() in ('1', 'true', 'yes', 'on')

    # CSRF
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 4  # 4 小时

    # 上传大小上限（Phase R3 安全加固）—— 防止超大文件撑爆磁盘
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB


class ProductionConfig(Config):
    """生产环境 — 严格"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """测试环境 — 关闭 CSRF、宽松限制"""
    DEBUG = False
    TESTING = True
    WTF_CSRF_ENABLED = False  # 关闭 CSRF 方便测试
    RATELIMIT_ENABLED = False  # 关闭限流方便测试


class DevelopmentConfig(Config):
    """开发环境 — 宽松"""
    DEBUG = True
    TESTING = False


# 映射表
CONFIG_MAP = {
    'production': ProductionConfig,
    'development': DevelopmentConfig,
    'testing': TestingConfig,
}


def get_config():
    """根据 FLASK_ENV 返回配置类实例"""
    env = os.environ.get('FLASK_ENV', 'production').lower()
    cls = CONFIG_MAP.get(env, ProductionConfig)
    return cls()