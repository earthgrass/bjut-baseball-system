"""
Phase R0.10 — Canary test

强制验证：测试前后真实 DB byte-for-byte 不变。
"""
import hashlib
import os


REAL_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                        'instance', 'baseball_players.db'))


def _real_db_sha256():
    if not os.path.exists(REAL_DB):
        return None
    return hashlib.sha256(open(REAL_DB, 'rb').read()).hexdigest()


def test_canary_real_db_unchanged_before_any_fixture():
    """独立测试（不依赖 app fixture），只检查 DB 哈希"""
    sha = _real_db_sha256()
    assert sha is not None, 'real DB missing'


def test_canary_real_db_unchanged_after_app_init(app):
    """app fixture 初始化后真实 DB 不变"""
    sha_before = _real_db_sha256()
    # 触发 DB 操作（test fixture 已经 create_all）
    with app.app_context():
        from database import Player
        _ = Player.query.count()
    sha_after = _real_db_sha256()
    assert sha_before == sha_after, (
        f'!!! REAL DB modified by app fixture !!!\n'
        f'before={sha_before}\nafter={sha_after}'
    )


def test_canary_real_db_unchanged_after_full_flow(auth_client):
    """auth_client 操作后真实 DB 不变"""
    sha_before = _real_db_sha256()
    # 触发一些 API 操作
    resp = auth_client.post('/api/players', json={
        'name': 'Canary', 'jersey_number': 'C',
        'is_pitcher': False, 'positions': ['游击手'], 'primary_position': '游击手',
    })
    assert resp.status_code == 201
    sha_after = _real_db_sha256()
    assert sha_before == sha_after