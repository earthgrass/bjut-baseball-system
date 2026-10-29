"""
比赛记录写入路径测试 —— 编辑（PUT）与批量（batch）

覆盖 2026-10-28 新增的写入能力，并锁定「profile == SUM(game_records)」
这一核心不变量：任何写操作之后，统计档案都必须与原始记录一致。
"""
from database import Player, GameRecord, db


def _create_player(client, **overrides):
    defaults = {
        'name': '写入测试',
        'jersey_number': '99',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _batting(player_id, date='2025-04-07', opponent='清华大学', **kw):
    payload = {
        'player_id': player_id,
        'game_date': date,
        'opponent': opponent,
        'is_pitching': False,
        'at_bats': 4, 'runs': 2, 'hits': 3, 'rbi': 2,
    }
    payload.update(kw)
    return payload


def _batch_batting(player_id, **kw):
    """批量里的打击条目 —— 不带 opponent，用来继承批次的对手。"""
    payload = {
        'player_id': player_id,
        'is_pitching': False,
        'at_bats': 4, 'hits': 3,
    }
    payload.update(kw)
    return payload


# ====== 编辑：PUT /api/game_records/<id> ======

def test_update_game_record_changes_fields(auth_client):
    pid = _create_player(auth_client, name='编辑目标', jersey_number='1')
    resp = auth_client.post('/api/game_records', json=_batting(pid))
    assert resp.status_code == 201, resp.data
    rid = resp.get_json()['record_id']

    resp = auth_client.put('/api/game_records/%d' % rid, json=_batting(
        pid, opponent='北京科技大学', at_bats=6, hits=4, rbi=3))
    assert resp.status_code == 200, resp.data
    assert resp.get_json()['message'] == '比赛记录更新成功'

    with auth_client.application.app_context():
        rec = db.session.get(GameRecord, rid)
        assert rec.opponent == '北京科技大学'
        assert rec.at_bats == 6
        assert rec.hits == 4
        assert rec.rbi == 3


def test_update_game_record_recomputes_stats(auth_client):
    """编辑后统计必须跟着变（不是叠加）。"""
    pid = _create_player(auth_client, name='编辑统计', jersey_number='2')
    resp = auth_client.post('/api/game_records', json=_batting(pid))
    rid = resp.get_json()['record_id']

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 4
        assert p.hits_total == 3
        assert p.batting_average == 0.750

    auth_client.put('/api/game_records/%d' % rid, json=_batting(
        pid, at_bats=8, hits=2))

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        # 不是 4+8=12，而是替换成 8
        assert p.at_bats_total == 8
        assert p.hits_total == 2
        assert p.batting_average == 0.250


def test_update_game_record_can_change_date_and_opponent(auth_client):
    pid = _create_player(auth_client, name='改日期', jersey_number='3')
    resp = auth_client.post('/api/game_records', json=_batting(pid))
    rid = resp.get_json()['record_id']

    resp = auth_client.put('/api/game_records/%d' % rid, json=_batting(
        pid, date='2025-11-22', opponent='北京交通大学'))
    assert resp.status_code == 200

    with auth_client.application.app_context():
        rec = db.session.get(GameRecord, rid)
        assert rec.game_date.strftime('%Y-%m-%d') == '2025-11-22'
        assert rec.opponent == '北京交通大学'


def test_update_game_record_can_change_player(auth_client):
    """改球员后，两个人的档案都要重算。"""
    pid_a = _create_player(auth_client, name='原球员', jersey_number='4')
    pid_b = _create_player(auth_client, name='新球员', jersey_number='5')
    resp = auth_client.post('/api/game_records', json=_batting(pid_a))
    rid = resp.get_json()['record_id']

    resp = auth_client.put('/api/game_records/%d' % rid, json=_batting(pid_b))
    assert resp.status_code == 200

    with auth_client.application.app_context():
        a = db.session.get(Player, pid_a)
        b = db.session.get(Player, pid_b)
        assert a.at_bats_total == 0      # 原球员不再有这条记录
        assert b.at_bats_total == 4      # 新球员接手
        assert b.hits_total == 3


def test_update_missing_record_returns_404(auth_client):
    resp = auth_client.put('/api/game_records/999999', json=_batting(1))
    assert resp.status_code == 404


def test_update_requires_auth(auth_client):
    """未登录不能编辑（带合法 CSRF token，排除 CSRF 拦截的干扰）。"""
    pid = _create_player(auth_client, name='未登录', jersey_number='6')
    resp = auth_client.post('/api/game_records', json=_batting(pid))
    rid = resp.get_json()['record_id']

    # 用一个全新的匿名 client（只拿 CSRF token，不登录）
    from app import app as flask_app
    import re
    anon = flask_app.test_client()
    html = anon.get('/login').data.decode()
    token = re.search(r'name="csrf-token"\s+content="([^"]+)"', html).group(1)

    resp = anon.put('/api/game_records/%d' % rid, json=_batting(pid),
                    headers={'X-CSRFToken': token})
    assert resp.status_code in (302, 401, 403), resp.status_code


# ====== 批量：POST /api/game_records/batch ======

def test_batch_write_creates_all_records(auth_client):
    pid = _create_player(auth_client, name='批量野手', jersey_number='7')
    ppid = _create_player(auth_client, name='批量投手', jersey_number='8',
                          is_pitcher=True, positions=['投手'],
                          primary_position='投手')

    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025-11-22',
        'opponent': '北京科技大学',
        'records': [
            _batch_batting(pid, at_bats=3, hits=2),
            _batch_batting(pid, at_bats=4, hits=1),
            {
                'player_id': ppid,
                'is_pitching': True,
                'innings_pitched': 3.0, 'hits_allowed': 4, 'runs_allowed': 1,
                'earned_runs': 1, 'walks_allowed': 2, 'strikeouts': 6,
                'home_runs_allowed': 0, 'pitches': 60, 'strikes': 40,
                'batters_faced': 12, 'win': True,
            },
        ],
    })
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['created'] == 3
    assert len(body['record_ids']) == 3

    with auth_client.application.app_context():
        recs = GameRecord.query.filter_by(opponent='北京科技大学').all()
        assert len(recs) == 3
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 7
        assert p.hits_total == 3
        pp = db.session.get(Player, ppid)
        assert pp.innings_pitched_total == 3.0
        assert pp.strikeouts_total == 6


def test_batch_write_is_all_or_nothing(auth_client):
    """一条不合法就整批回滚。"""
    pid = _create_player(auth_client, name='回滚测试', jersey_number='9')

    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025-11-22',
        'opponent': '北京科技大学',
        'records': [
            _batch_batting(pid, at_bats=3),
            _batch_batting(999999, at_bats=3),   # 球员不存在
        ],
    })
    assert resp.status_code == 400, resp.data

    with auth_client.application.app_context():
        recs = GameRecord.query.filter_by(opponent='北京科技大学').all()
        assert len(recs) == 0, '失败的批次不应留下任何记录'
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 0


def test_batch_write_rejects_empty_records(auth_client):
    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025-11-22',
        'opponent': 'X',
        'records': [],
    })
    assert resp.status_code == 400


def test_batch_write_rejects_bad_date(auth_client):
    pid = _create_player(auth_client, name='日期校验', jersey_number='10')
    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025/11/22',
        'opponent': 'X',
        'records': [_batch_batting(pid)],
    })
    assert resp.status_code == 400


# ====== 不变量：profile 必须等于 game_records 的聚合 ======

def test_profile_matches_game_records_after_writes(auth_client):
    """写操作之后，档案累计必须精确等于原始记录之和。"""
    pid = _create_player(auth_client, name='不变量', jersey_number='11')

    auth_client.post('/api/game_records', json=_batting(pid, at_bats=4, hits=1))
    auth_client.post('/api/game_records', json=_batting(
        pid, date='2025-04-14', at_bats=2, hits=2))

    with auth_client.application.app_context():
        from sqlalchemy import func
        p = db.session.get(Player, pid)
        rec_sum = db.session.query(func.sum(GameRecord.at_bats)).filter(
            GameRecord.player_id == pid).scalar()
        assert p.at_bats_total == rec_sum
        assert p.at_bats_total == 6


def test_delete_then_stats_are_rebuilt(auth_client):
    """删除后档案要精确回落到剩余记录之和。"""
    pid = _create_player(auth_client, name='删除回算', jersey_number='12')
    r1 = auth_client.post('/api/game_records', json=_batting(
        pid, at_bats=4, hits=1)).get_json()['record_id']
    auth_client.post('/api/game_records', json=_batting(
        pid, date='2025-04-14', at_bats=6, hits=3))

    resp = auth_client.delete('/api/matchup/game_record/%d' % r1)
    assert resp.status_code == 200, resp.data

    with auth_client.application.app_context():
        from sqlalchemy import func
        p = db.session.get(Player, pid)
        rec_sum = db.session.query(func.sum(GameRecord.at_bats)).filter(
            GameRecord.player_id == pid).scalar()
        assert p.at_bats_total == 6
        assert p.at_bats_total == rec_sum
