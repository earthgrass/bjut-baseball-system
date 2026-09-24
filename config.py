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
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    # CSRF
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 4  # 4 小时


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