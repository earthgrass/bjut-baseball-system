"""
GameRecord characterization tests — Phase E0
"""
import pytest
from database import Player, GameRecord


def _create_player(client, **overrides):
    defaults = {
        'name': '测试球员',
        'jersey_number': '99',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


# ====== 打击记录 ======

def test_add_batting_record(auth_client):
    pid = _create_player(auth_client, name='野手A', jersey_number='1')

    resp = auth_client.post('/api/game_records', json={
        'player_id': pid,
        'game_date': '2025-04-07',
        'opponent': '清华大学',
        'is_pitching': False,
        'at_bats': 4, 'runs': 2, 'hits': 3, 'rbi': 2,
        'walks': 1, 'strikeouts': 0, 'doubles': 1, 'triples': 0,
        'home_runs_game': 1, 'stolen_bases_game': 1, 'hit_by_pitch': 0,
    })
    assert resp.status_code == 201, resp.data
    record_id = resp.get_json()['record_id']

    with auth_client.application.app_context():
        rec = GameRecord.query.get(record_id)
        assert rec is not None
        assert rec.player_id == pid
        assert rec.opponent == '清华大学'
        assert not rec.is_pitching_record
        assert rec.at_bats == 4
        assert rec.hits == 3
        assert rec.total_bases == (
            (3 - 1 - 0 - 1) * 1 + 1 * 2 + 0 * 3 + 1 * 4
        )
        p = Player.query.get(pid)
        assert p.at_bats_total == 4
        assert p.hits_total == 3
        assert p.rbi_total == 2
        assert p.doubles == 1
        assert p.home_runs_batting == 1
        assert p.stolen_bases == 1
        assert p.batting_average == 0.750


# ====== 投球记录 ======

def test_add_pitching_record_requires_pitcher(auth_client):
    pid = _create_player(auth_client, name='野手B', jersey_number='2', is_pitcher=False)
    resp = auth_client.post('/api/game_records', json={
        'player_id': pid,
        'game_date': '2025-04-07',
        'opponent': '清华',
        'is_pitching': True,
        'innings_pitched': 5.0,
    })
    assert resp.status_code == 400


def test_add_pitching_record(auth_client):
    pid = _create_player(auth_client, name='投手A', jersey_number='20',
                         is_pitcher=True, positions=['投手'], primary_position='投手')

    resp = auth_client.post('/api/game_records', json={
        'player_id': pid,
        'game_date': '2025-04-07',
        'opponent': '清华大学',
        'is_pitching': True,
        'innings_pitched': 7.0,
        'hits_allowed': 5, 'runs_allowed': 2, 'earned_runs': 1,
        'walks_allowed': 2, 'strikeouts': 8, 'home_runs_allowed': 1,
        'pitches': 95, 'strikes': 62, 'win': True,
    })
    assert resp.status_code == 201

    with auth_client.application.app_context():
        p = Player.query.get(pid)
        assert p.innings_pitched_total == 7.0
        assert p.hits_allowed_total == 5
        assert p.earned_runs_total == 1
        assert p.strikeouts_total == 8
        assert abs(p.era - 1.29) < 0.01
        rec = GameRecord.query.filter_by(player_id=pid).first()
        assert rec.win is True
        assert rec.loss is False
        assert rec.save is False


# ====== 非法输入 ======

def test_invalid_player_id(auth_client):
    resp = auth_client.post('/api/game_records', json={
        'player_id': 99999,
        'game_date': '2025-04-07',
        'opponent': 'X',
        'is_pitching': False,
    })
    assert resp.status_code == 404


# ====== 同一球员多条历史 ======

def test_multiple_records_for_same_player(auth_client):
    pid = _create_player(auth_client, name='多场', jersey_number='5')

    for i, date_str in enumerate(['2025-04-01', '2025-04-08', '2025-04-15']):
        resp = auth_client.post('/api/game_records', json={
            'player_id': pid,
            'game_date': date_str,
            'opponent': f'对手{i}',
            'is_pitching': False,
            'at_bats': 4, 'hits': 1 + i,
        })
        assert resp.status_code == 201

    with auth_client.application.app_context():
        records = GameRecord.query.filter_by(player_id=pid).all()
        assert len(records) == 3
        p = Player.query.get(pid)
        assert p.at_bats_total == 12
        assert p.hits_total == 1 + 2 + 3


# ====== BASELINE BUG: 当前 API 入口无去重保护 ======

def test_duplicate_records_allowed(auth_client):
    """同球员+同日期+同对手 的重复添加当前被允许（KNOWN BASELINE BUG）"""
    pid = _create_player(auth_client, name='重复测试', jersey_number='6')

    payload = {
        'player_id': pid,
        'game_date': '2025-05-01',
        'opponent': 'X队',
        'is_pitching': False,
        'at_bats': 3, 'hits': 1,
    }
    r1 = auth_client.post('/api/game_records', json=payload)
    r2 = auth_client.post('/api/game_records', json=payload)

    assert r1.status_code == 201
    assert r2.status_code == 201, (
        'KNOWN BASELINE BUG: API 当前允许重复；'
        '重复入库会导致球员统计被多算。'
        'Phase C3 加唯一索引时会触发此 bug，需先 cleanup_db.py 处理。'
    )

    with auth_client.application.app_context():
        p = Player.query.get(pid)
        assert p.hits_total == 2


# ====== 删除比赛记录 ======

def test_delete_record_subtracts_stats(auth_client):
    pid = _create_player(auth_client, name='删除测', jersey_number='7')

    add_resp = auth_client.post('/api/game_records', json={
        'player_id': pid, 'game_date': '2025-06-01', 'opponent': 'Y',
        'is_pitching': False, 'at_bats': 5, 'hits': 2, 'rbi': 1,
    })
    rid = add_resp.get_json()['record_id']

    with auth_client.application.app_context():
        p = Player.query.get(pid)
        assert p.hits_total == 2
        assert p.rbi_total == 1

    del_resp = auth_client.delete(f'/api/matchup/game_record/{rid}')
    assert del_resp.status_code == 200

    with auth_client.application.app_context():
        assert GameRecord.query.get(rid) is None
        p = Player.query.get(pid)
        assert p.hits_total == 0
        assert p.rbi_total == 0
        assert p.at_bats_total == 0


# ====== CSRF ======

def test_add_record_without_csrf_fails(client, admin_logged_in):
    c, _ = admin_logged_in
    pid = 1
    resp = c.post('/api/game_records', json={
        'player_id': pid, 'game_date': '2025-01-01', 'opponent': 'X',
        'is_pitching': False, 'at_bats': 1,
    })
    assert resp.status_code == 400
    assert 'CSRF' in resp.get_data(as_text=True)