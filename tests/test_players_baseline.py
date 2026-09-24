"""
Player characterization tests — Phase E0
使用 auth_client fixture 自动附加 CSRF header
"""
import pytest
from database import Player, Position, FielderProfile, PitcherProfile


# ====== 创建 ======

def test_create_fielder(auth_client):
    resp = auth_client.post('/api/players', json={
        'name': '张三',
        'jersey_number': '7',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '游击手',
    })
    assert resp.status_code == 201, resp.data
    data = resp.get_json()
    player_id = data['player']['id']

    with auth_client.application.app_context():
        p = Player.query.get(player_id)
        assert p is not None
        assert p.name == '张三'
        assert p.jersey_number == '7'
        assert p._is_pitcher is False
        assert p.primary_position == '游击手'
        assert [pos.name for pos in p.positions] == ['游击手']
        assert p.fielder_profile is not None
        assert p.pitcher_profile is None


def test_create_pitcher_auto_gets_pitcher_position(auth_client):
    resp = auth_client.post('/api/players', json={
        'name': '李四',
        'jersey_number': '10',
        'is_pitcher': True,
        'positions': ['外野手'],
        'primary_position': '投手',
    })
    assert resp.status_code == 201
    player_id = resp.get_json()['player']['id']

    with auth_client.application.app_context():
        p = Player.query.get(player_id)
        assert p._is_pitcher is True
        position_names = [pos.name for pos in p.positions]
        assert '投手' in position_names
        assert '外野手' in position_names
        assert p.primary_position == '投手'
        assert p.fielder_profile is not None
        assert p.pitcher_profile is not None


def test_pitcher_can_have_extra_positions(auth_client):
    resp = auth_client.post('/api/players', json={
        'name': '王五',
        'jersey_number': '11',
        'is_pitcher': True,
        'positions': ['投手', '一垒手'],
        'primary_position': '投手',
    })
    assert resp.status_code == 201

    with auth_client.application.app_context():
        p = Player.query.filter_by(name='王五').first()
        names = sorted(pos.name for pos in p.positions)
        assert names == ['一垒手', '投手']


def test_multiple_positions(auth_client):
    resp = auth_client.post('/api/players', json={
        'name': '赵六',
        'jersey_number': '5',
        'is_pitcher': False,
        'positions': ['游击手', '三垒手', '二垒手'],
        'primary_position': '游击手',
    })
    assert resp.status_code == 201

    with auth_client.application.app_context():
        p = Player.query.filter_by(name='赵六').first()
        names = sorted(pos.name for pos in p.positions)
        assert names == ['三垒手', '二垒手', '游击手']


def test_primary_position_must_be_in_positions(auth_client):
    """主位置必须属于已选位置（baseline 行为）"""
    resp = auth_client.post('/api/players', json={
        'name': '钱七',
        'jersey_number': '8',
        'is_pitcher': False,
        'positions': ['游击手'],
        'primary_position': '捕手',
    })
    assert resp.status_code == 201

    with auth_client.application.app_context():
        p = Player.query.filter_by(name='钱七').first()
        position_names = [pos.name for pos in p.positions]
        assert '捕手' in position_names


def test_missing_required_fields(auth_client):
    resp = auth_client.post('/api/players', json={'name': '', 'jersey_number': '1'})
    assert resp.status_code == 400


def test_create_requires_admin(client, api_csrf_token):
    """未登录访问被重定向到 login"""
    resp = client.post('/api/players',
                       json={'name': 'X', 'jersey_number': '1'},
                       headers={'X-CSRFToken': api_csrf_token})
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


# ====== 修改 ======

def test_update_player(auth_client):
    create_resp = auth_client.post('/api/players', json={
        'name': '孙八', 'jersey_number': '3',
        'is_pitcher': False, 'positions': ['游击手'], 'primary_position': '游击手',
    })
    pid = create_resp.get_json()['player']['id']

    upd_resp = auth_client.put(f'/api/players/{pid}', json={
        'name': '孙八改', 'jersey_number': '3',
        'is_pitcher': False, 'positions': ['三垒手'], 'primary_position': '三垒手',
    })
    assert upd_resp.status_code == 200

    with auth_client.application.app_context():
        p = Player.query.get(pid)
        assert p.name == '孙八改'
        assert [pos.name for pos in p.positions] == ['三垒手']
        assert p.primary_position == '三垒手'


def test_update_player_with_stats(auth_client):
    """通过 PUT 端点直接更新统计字段（BASELINE：当前允许，Phase C5 限制）"""
    create_resp = auth_client.post('/api/players', json={
        'name': '周九', 'jersey_number': '9',
        'is_pitcher': False, 'positions': ['外野手'], 'primary_position': '外野手',
    })
    pid = create_resp.get_json()['player']['id']

    auth_client.put(f'/api/players/{pid}', json={
        'name': '周九', 'jersey_number': '9',
        'is_pitcher': False, 'positions': ['外野手'], 'primary_position': '外野手',
        'at_bats_total': 100, 'hits_total': 30, 'rbi_total': 15,
    })

    with auth_client.application.app_context():
        p = Player.query.get(pid)
        assert p.at_bats_total == 100
        assert p.hits_total == 30
        assert p.rbi_total == 15
        assert p.batting_average == 0.300


# ====== 删除 ======

def test_delete_player(auth_client):
    """必须先创建 2 名球员（因最后一名不可删规则）"""
    # 创建 2 名球员以满足"非最后一名"约束
    _ = auth_client.post('/api/players', json={
        'name': '保留球员', 'jersey_number': '1',
        'is_pitcher': False, 'positions': ['外野手'], 'primary_position': '外野手',
    })
    create_resp = auth_client.post('/api/players', json={
        'name': '吴十', 'jersey_number': '2',
        'is_pitcher': False, 'positions': ['外野手'], 'primary_position': '外野手',
    })
    pid = create_resp.get_json()['player']['id']

    del_resp = auth_client.delete(f'/api/players/{pid}')
    assert del_resp.status_code == 200

    with auth_client.application.app_context():
        assert Player.query.get(pid) is None


def test_cannot_delete_last_player(auth_client):
    create_resp = auth_client.post('/api/players', json={
        'name': '唯一', 'jersey_number': '0',
        'is_pitcher': False, 'positions': ['外野手'], 'primary_position': '外野手',
    })
    pid = create_resp.get_json()['player']['id']

    del_resp = auth_client.delete(f'/api/players/{pid}')
    assert del_resp.status_code == 400
    body = del_resp.get_json()
    assert '最后一名' in body['error']


# ====== CSRF ======

def test_create_player_without_csrf_fails(client, admin_logged_in):
    """mutation API 无 CSRF token 应被拒绝"""
    c, _ = admin_logged_in
    resp = c.post('/api/players', json={'name': 'X', 'jersey_number': '1'})
    assert resp.status_code == 400
    assert 'CSRF' in resp.get_data(as_text=True)