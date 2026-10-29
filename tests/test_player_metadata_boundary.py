"""
球员接口的字段边界测试 —— Phase R2

背景：Phase R1 之后，「统计档案」是 `game_records` 的派生值，只能由
`rebuild_player_stats()` 重算。但 `PUT /api/players/<id>` 仍然可以直接
覆盖 profile 累计字段（经 Player 的 property proxy 直通 FielderProfile /
PitcherProfile），是最后一个绕过 GameRecord 的统计写入口。

Phase R2 把该接口收窄为 **metadata-only**：
    允许：name / jersey_number / is_pitcher / player_type / positions / primary_position
    拒绝：任何统计字段 → 400 + 明确报错（不静默丢弃）

本文件锁住这一契约，并验证「拒绝之后档案与原始记录依然一致」。
"""
from sqlalchemy import func

from database import Player, GameRecord, db


def _create_player(client, **overrides):
    defaults = {
        'name': '边界测试',
        'jersey_number': '88',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _add_batting(client, player_id, at_bats=4, hits=2, date='2025-04-07'):
    resp = client.post('/api/game_records', json={
        'player_id': player_id,
        'game_date': date,
        'opponent': '清华大学',
        'is_pitching': False,
        'at_bats': at_bats,
        'runs': 1,
        'hits': hits,
        'rbi': 1,
    })
    assert resp.status_code == 201, resp.data
    return resp.get_json()['record_id']


def _profile_snapshot(app, player_id):
    """取该球员的档案累计快照（用于比对「有没有被动过」）。"""
    with app.app_context():
        player = db.session.get(Player, player_id)
        return {
            'at_bats_total': player.at_bats_total,
            'hits_total': player.hits_total,
            'rbi_total': player.rbi_total,
            'runs_total': player.runs_total,
            'innings_pitched_total': player.innings_pitched_total,
            'hits_allowed_total': player.hits_allowed_total,
            'earned_runs_total': player.earned_runs_total,
        }


def _record_sum(app, player_id, column):
    with app.app_context():
        return db.session.query(func.sum(column)).filter(
            GameRecord.player_id == player_id).scalar()


# ====== metadata 仍然可以正常改 ======

def test_put_player_updates_metadata(auth_client):
    """只带 metadata 的 PUT 必须成功，并真正落到数据库。"""
    pid = _create_player(auth_client, name='元数据改', jersey_number='21')

    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '元数据改新名',
        'jersey_number': '22',
        'is_pitcher': False,
        'positions': ['二垒手', '游击手'],
        'primary_position': '二垒手',
    })
    assert resp.status_code == 200, resp.data

    with auth_client.application.app_context():
        player = db.session.get(Player, pid)
        assert player.name == '元数据改新名'
        assert player.jersey_number == '22'
        assert player.primary_position == '二垒手'
        names = {pos.name for pos in player.positions}
        assert '二垒手' in names and '游击手' in names


def test_put_player_metadata_change_leaves_stats_untouched(auth_client):
    """改 metadata 不得影响任何累计值（累计只能由 game_records 推导）。"""
    pid = _create_player(auth_client, name='只改资料', jersey_number='23')
    _add_batting(auth_client, pid, at_bats=4, hits=2)

    before = _profile_snapshot(auth_client.application, pid)
    assert before['at_bats_total'] == 4

    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '只改资料新名',
        'jersey_number': '24',
        'positions': ['游击手'],
        'primary_position': '游击手',
    })
    assert resp.status_code == 200, resp.data

    after = _profile_snapshot(auth_client.application, pid)
    assert after == before, '改 metadata 不应触碰任何累计字段'
    assert after['at_bats_total'] == 4


# ====== 统计字段必须被拒绝 ======

def test_put_player_rejects_batting_stats_field(auth_client):
    """提交打击统计字段 → 400，并列出被拒字段。"""
    pid = _create_player(auth_client, name='拒绝打击', jersey_number='31')
    _add_batting(auth_client, pid, at_bats=4, hits=2)
    before = _profile_snapshot(auth_client.application, pid)

    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '拒绝打击',
        'jersey_number': '31',
        'positions': ['游击手'],
        'primary_position': '游击手',
        'at_bats_total': 999,
    })
    assert resp.status_code == 400, resp.data
    body = resp.get_json()
    assert '统计字段' in body['error']
    assert 'at_bats_total' in body['rejected_fields']

    after = _profile_snapshot(auth_client.application, pid)
    assert after == before, '被拒绝的写入不得改动任何累计字段'
    assert after['at_bats_total'] == 4, '打数不能被 PUT 改写'


def test_put_player_rejects_pitcher_stats_field(auth_client):
    """提交投手统计字段 → 400。"""
    pid = _create_player(auth_client, name='拒绝投球', jersey_number='32',
                         is_pitcher=True, positions=['投手'],
                         primary_position='投手')
    before = _profile_snapshot(auth_client.application, pid)

    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '拒绝投球',
        'jersey_number': '32',
        'positions': ['投手'],
        'primary_position': '投手',
        'innings_pitched_total': 9.0,
    })
    assert resp.status_code == 400, resp.data
    body = resp.get_json()
    assert 'innings_pitched_total' in body['rejected_fields']

    after = _profile_snapshot(auth_client.application, pid)
    assert after == before


def test_put_player_rejects_derived_rate_field(auth_client):
    """派生率（ERA / OPS 等）同样属于统计，必须拒绝。"""
    pid = _create_player(auth_client, name='拒绝派生率', jersey_number='33')
    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '拒绝派生率',
        'jersey_number': '33',
        'positions': ['游击手'],
        'primary_position': '游击手',
        'ops': 9.99,
    })
    assert resp.status_code == 400, resp.data
    assert 'ops' in resp.get_json()['rejected_fields']


def test_put_player_rejects_multiple_stats_fields(auth_client):
    """一次提交多个统计字段 → 全部列出。"""
    pid = _create_player(auth_client, name='拒绝多个', jersey_number='34')
    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '拒绝多个',
        'jersey_number': '34',
        'positions': ['游击手'],
        'primary_position': '游击手',
        'hits_total': 10,
        'era': 1.0,
        'total_bases': 20,
    })
    assert resp.status_code == 400, resp.data
    rejected = resp.get_json()['rejected_fields']
    assert rejected == ['era', 'hits_total', 'total_bases']


# ====== 拒绝之后，不变量仍然成立 ======

def test_profile_still_matches_game_records_after_rejected_put(auth_client):
    """被拒绝的写入不得留下任何痕迹：profile 依旧等于 game_records 之和。"""
    pid = _create_player(auth_client, name='不变量保持', jersey_number='35')
    _add_batting(auth_client, pid, at_bats=4, hits=2)
    _add_batting(auth_client, pid, at_bats=2, hits=1, date='2025-04-14')

    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '不变量保持',
        'jersey_number': '35',
        'positions': ['游击手'],
        'primary_position': '游击手',
        'at_bats_total': 500,
        'hits_total': 500,
    })
    assert resp.status_code == 400, resp.data

    rec_sum = _record_sum(auth_client.application, pid, GameRecord.at_bats)
    assert rec_sum == 6
    assert _profile_snapshot(auth_client.application, pid)['at_bats_total'] == 6


# ====== 认证与杂项 ======

def test_put_player_requires_auth(auth_client):
    """未登录 PUT → 跳登录（带合法 CSRF token，排除 CSRF 拦截的干扰）。"""
    pid = _create_player(auth_client, name='未登录', jersey_number='38')

    from app import app as flask_app
    import re
    anon = flask_app.test_client()
    html = anon.get('/login').data.decode()
    token = re.search(r'name="csrf-token"\s+content="([^"]+)"', html).group(1)

    resp = anon.put('/api/players/%d' % pid, json={
        'name': '未登录改名',
        'jersey_number': '38',
        'positions': ['游击手'],
        'primary_position': '游击手',
    }, headers={'X-CSRFToken': token})
    assert resp.status_code in (302, 401, 403), resp.status_code

    # 名称必须没被改掉
    with auth_client.application.app_context():
        assert db.session.get(Player, pid).name == '未登录'


def test_put_player_reports_ignored_fields(auth_client):
    """既不是 metadata 也不是统计的键 → 忽略并在响应里回报（便于自查拼写）。"""
    pid = _create_player(auth_client, name='忽略字段', jersey_number='36')
    resp = auth_client.put('/api/players/%d' % pid, json={
        'name': '忽略字段',
        'jersey_number': '36',
        'positions': ['游击手'],
        'primary_position': '游击手',
        'at_bats': 3,          # ← GameRecord 的字段名，不是 Player 的
    })
    assert resp.status_code == 200, resp.data
    assert resp.get_json()['ignored_fields'] == ['at_bats']


def test_put_player_rejects_non_object_body(auth_client):
    """请求体不是对象 → 400。"""
    pid = _create_player(auth_client, name='非对象体', jersey_number='37')
    resp = auth_client.put('/api/players/%d' % pid, json=['不是对象'])
    assert resp.status_code == 400, resp.data
