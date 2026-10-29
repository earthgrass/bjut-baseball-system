"""
Matchup characterization tests — Phase E0.5

锁定 /api/matchup/* 当前响应结构与行为：
- opponents list
- filter by player
- filter by opponent
- filter by player + opponent
- all game records
- empty result behavior
"""


def _create_player(client, **overrides):
    defaults = {
        'name': '默认球员',
        'jersey_number': '99',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    }
    defaults.update(overrides)
    resp = client.post('/api/players', json=defaults)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _add_batting(client, pid, *, date, opponent, at_bats=3, hits=1, rbi=0):
    return client.post('/api/game_records', json={
        'player_id': pid, 'game_date': date, 'opponent': opponent,
        'is_pitching': False, 'at_bats': at_bats, 'hits': hits, 'rbi': rbi,
    })


# ====== opponents list ======

def test_opponents_list_empty(auth_client):
    resp = auth_client.get('/api/matchup/opponents')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_opponents_list_dedup(auth_client):
    p1 = _create_player(auth_client, name='球员1', jersey_number='1')
    p2 = _create_player(auth_client, name='球员2', jersey_number='2')

    _add_batting(auth_client, p1, date='2025-04-01', opponent='清华')
    _add_batting(auth_client, p1, date='2025-04-08', opponent='清华')
    _add_batting(auth_client, p2, date='2025-04-15', opponent='北大')

    resp = auth_client.get('/api/matchup/opponents')
    assert resp.status_code == 200
    opps = resp.get_json()
    assert set(opps) == {'清华', '北大'}
    assert len(opps) == 2  # 去重


def test_opponents_sorted(auth_client):
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='北大')
    _add_batting(auth_client, p, date='2025-01-08', opponent='清华')
    _add_batting(auth_client, p, date='2025-01-15', opponent='上交')

    resp = auth_client.get('/api/matchup/opponents')
    opps = resp.get_json()
    assert opps == sorted(opps)


# ====== filter by player ======

def test_filter_by_player_only(auth_client):
    p1 = _create_player(auth_client, name='A球员', jersey_number='1')
    p2 = _create_player(auth_client, name='B球员', jersey_number='2')
    _add_batting(auth_client, p1, date='2025-01-01', opponent='X', at_bats=2, hits=1)
    _add_batting(auth_client, p2, date='2025-01-01', opponent='Y', at_bats=3, hits=2)

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p1}')
    assert resp.status_code == 200
    data = resp.get_json()
    # 应只返回 p1 的记录
    batting_records = data['batting_records']
    assert all(r['player_id'] == p1 for r in batting_records)
    assert len(batting_records) == 1


def test_filter_by_player_response_shape(auth_client):
    """锁定响应 JSON 结构 — Phase C 重构后必须保持兼容"""
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='Z', at_bats=4, hits=2, rbi=1)

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p}')
    data = resp.get_json()

    assert 'title' in data
    assert 'filters' in data
    assert data['filters']['player_id'] == p
    assert data['filters']['opponent'] == ''
    assert 'batting_records' in data
    assert 'pitching_records' in data
    assert 'batting_summary' in data or data['batting_summary'] is None
    assert 'pitching_summary' in data or data['pitching_summary'] is None

    rec = data['batting_records'][0]
    for field in ('id', 'player_id', 'player_name', 'player_jersey',
                  'game_date', 'opponent', 'at_bats', 'runs', 'hits',
                  'rbi', 'walks', 'strikeouts', 'doubles', 'triples',
                  'home_runs', 'stolen_bases', 'batting_average'):
        assert field in rec, f'missing field: {field}'


# ====== filter by opponent ======

def test_filter_by_opponent_only(auth_client):
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='Alpha', at_bats=2, hits=1)
    _add_batting(auth_client, p, date='2025-01-08', opponent='Beta', at_bats=3, hits=1)

    resp = auth_client.get('/api/matchup/search_records?opponent=Alpha')
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(r['opponent'] == 'Alpha' for r in data['batting_records'])
    assert len(data['batting_records']) == 1


# ====== filter by player + opponent ======

def test_filter_by_player_and_opponent(auth_client):
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='A', at_bats=2, hits=1)
    _add_batting(auth_client, p, date='2025-01-08', opponent='B', at_bats=3, hits=2)

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p}&opponent=A')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['batting_records']) == 1
    assert data['batting_records'][0]['opponent'] == 'A'


def test_filter_combined_no_match(auth_client):
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='A')

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p}&opponent=Z')
    data = resp.get_json()
    assert data['batting_records'] == []
    assert data['pitching_records'] == []
    assert data['batting_summary'] is None
    assert data['pitching_summary'] is None


# ====== error: no filter ======

def test_no_filter_returns_400(auth_client):
    resp = auth_client.get('/api/matchup/search_records')
    assert resp.status_code == 400


# ====== filter by invalid player ======

def test_filter_by_invalid_player(auth_client):
    resp = auth_client.get('/api/matchup/search_records?player_id=99999')
    assert resp.status_code == 404


# ====== all game records ======

def test_all_game_records_empty(auth_client):
    resp = auth_client.get('/api/matchup/all_game_records')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['batting_records'] == []
    assert data['pitching_records'] == []


def test_all_game_records_returns_both(auth_client):
    p = _create_player(auth_client, name='投手兼打者', jersey_number='1',
                       is_pitcher=True, positions=['投手'], primary_position='投手')
    _add_batting(auth_client, p, date='2025-01-01', opponent='X', at_bats=2, hits=1)

    auth_client.post('/api/game_records', json={
        'player_id': p, 'game_date': '2025-01-01', 'opponent': 'X',
        'is_pitching': True, 'innings_pitched': 5.0, 'hits_allowed': 3,
        'earned_runs': 1, 'strikeouts': 5,
    })

    resp = auth_client.get('/api/matchup/all_game_records')
    data = resp.get_json()
    assert len(data['batting_records']) == 1
    assert len(data['pitching_records']) == 1


# ====== summary aggregation ======

def test_batting_summary_aggregation(auth_client):
    p = _create_player(auth_client)
    _add_batting(auth_client, p, date='2025-01-01', opponent='X', at_bats=3, hits=1, rbi=0)
    _add_batting(auth_client, p, date='2025-01-08', opponent='X', at_bats=4, hits=2, rbi=1)

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p}&opponent=X')
    summary = resp.get_json()['batting_summary']
    assert summary['games'] == 2
    assert summary['at_bats'] == 7
    assert summary['hits'] == 3
    assert summary['rbi'] == 1
    assert summary['batting_average'] == 0.429  # 3/7 ≈ 0.4286


def test_pitching_summary_aggregation(auth_client):
    p = _create_player(auth_client, name='投手', jersey_number='1',
                       is_pitcher=True, positions=['投手'], primary_position='投手')

    # 2 场投球
    for d, ip, ha, er, so in [
        ('2025-01-01', 6.0, 5, 1, 5),
        ('2025-01-08', 7.0, 4, 0, 8),
    ]:
        auth_client.post('/api/game_records', json={
            'player_id': p, 'game_date': d, 'opponent': 'X',
            'is_pitching': True, 'innings_pitched': ip,
            'hits_allowed': ha, 'earned_runs': er, 'strikeouts': so,
            'walks_allowed': 2, 'pitches': 90, 'strikes': 60,
        })

    resp = auth_client.get(f'/api/matchup/search_records?player_id={p}&opponent=X')
    summary = resp.get_json()['pitching_summary']
    assert summary['games'] == 2
    assert summary['innings_pitched'] == 13.0
    assert summary['hits_allowed'] == 9
    assert summary['earned_runs'] == 1
    # ERA = 1 * 9 / 13 ≈ 0.69
    assert abs(summary['era'] - 0.69) < 0.01


# ====== CSRF ======

def test_search_records_does_not_require_csrf(client, api_csrf_token):
    """GET 不需要 CSRF"""
    resp = client.get('/api/matchup/opponents')
    assert resp.status_code == 200