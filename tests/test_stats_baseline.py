"""
Statistics characterization tests — Phase E0
"""
from database import Player, db


def _create_player(client, **overrides):
    defaults = {
        'name': '统计测',
        'jersey_number': '99',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _add_batting(client, pid, *, date, at_bats, hits, rbi=0, walks=0,
                 doubles=0, triples=0, hr=0, sb=0, hbp=0, opponent='测试对手'):
    return client.post('/api/game_records', json={
        'player_id': pid, 'game_date': date, 'opponent': opponent,
        'is_pitching': False,
        'at_bats': at_bats, 'hits': hits, 'rbi': rbi, 'walks': walks,
        'doubles': doubles, 'triples': triples, 'home_runs_game': hr,
        'stolen_bases_game': sb, 'hit_by_pitch': hbp, 'strikeouts': 0,
    })


def test_batting_average_exact(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=4, hits=3)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 4
        assert p.hits_total == 3
        assert p.batting_average == 0.750


def test_batting_average_zero_ab(auth_client):
    pid = _create_player(auth_client)
    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 0
        assert p.batting_average == 0.0


def test_total_bases_calculation(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=5, hits=5,
                 doubles=2, triples=1, hr=1)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.total_bases == 12


def test_obp_calculation(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=10, hits=3, walks=2)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert abs(p.on_base_percentage - 0.417) < 0.001


def test_add_record_increases_stats(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=10, hits=3, rbi=2, hr=1)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 10
        assert p.hits_total == 3
        assert p.home_runs_batting == 1
        assert p.batting_average == 0.300

    _add_batting(auth_client, pid, date='2025-01-08', at_bats=10, hits=4, rbi=3, hr=0)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 20
        assert p.hits_total == 7
        assert p.rbi_total == 5
        assert p.home_runs_batting == 1
        assert p.batting_average == 0.350


def test_delete_record_restores_stats(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=10, hits=3, rbi=2)
    r2 = _add_batting(auth_client, pid, date='2025-01-08', at_bats=10, hits=4, rbi=3)
    rid2 = r2.get_json()['record_id']

    auth_client.delete(f'/api/matchup/game_record/{rid2}')

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 10
        assert p.hits_total == 3
        assert p.rbi_total == 2


def _create_pitcher(client, **overrides):
    defaults = {
        'name': '投手统计',
        'jersey_number': '1',
        'is_pitcher': True,
        'positions': ['投手'],
        'primary_position': '投手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    return resp.get_json()['player']['id']


def _add_pitching(client, pid, *, date, ip, ha=0, ra=0, er=0, bba=0, so=0,
                  hra=0, bf=0, opponent='对手'):
    return client.post('/api/game_records', json={
        'player_id': pid, 'game_date': date, 'opponent': opponent,
        'is_pitching': True,
        'innings_pitched': ip, 'hits_allowed': ha, 'runs_allowed': ra,
        'earned_runs': er, 'walks_allowed': bba, 'strikeouts': so,
        'home_runs_allowed': hra, 'batters_faced': bf,
        'pitches': 90, 'strikes': 60,
    })


def test_era_calculation(auth_client):
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=9.0, er=3)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.innings_pitched_total == 9.0
        assert p.earned_runs_total == 3
        assert p.era == 3.0


def test_whip_calculation(auth_client):
    """WHIP = (被安打 + 保送) / 面对打席数（标准口径，Phase R5）。

    修复前分母用的是投球局数：(5+2)/9 = 0.78 —— 那是错的，
    库里的投球记录几乎都带着小数局数，用局数当分母会离谱地偏高。
    """
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=9.0, ha=5, bba=2, bf=20)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert abs(p.whip - 0.35) < 0.01      # (5+2)/20


def test_whip_without_batters_faced_is_zero(auth_client):
    """没有面对打席数的场次 → WHIP 算不出来（0.0），而不是退回局数口径。"""
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=9.0, ha=5, bba=2, bf=0)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.whip == 0.0


def test_pitcher_zero_ip_returns_zero_era(auth_client):
    pid = _create_pitcher(auth_client)
    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.innings_pitched_total == 0.0
        assert p.era == 0.0
        assert p.whip == 0.0


def test_batting_average_three_decimals(auth_client):
    pid = _create_player(auth_client)
    _add_batting(auth_client, pid, date='2025-01-01', at_bats=3, hits=1)
    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.batting_average == 0.333


def test_era_two_decimals(auth_client):
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=7.0, er=1)
    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.era == 1.29


def test_cumulative_after_five_games(auth_client):
    pid = _create_player(auth_client)
    for i in range(5):
        _add_batting(auth_client, pid, date=f'2025-0{i+1}-01', at_bats=4, hits=1)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.at_bats_total == 20
        assert p.hits_total == 5
        assert p.batting_average == 0.250