"""
比赛记录「读回来」契约测试 —— Phase R2

背景（真实 bug，Phase R1 引入）：
    `GET /api/game_records/<id>` 的响应 dict 里，`'strikeouts'` 这个键
    **出现了两次**（打击字段一次、投球字段一次）。Python 的 dict 字面量
    里重复键后者覆盖前者 —— 于是打击记录的三振永远返回投球列的值（=0）。

    后果：前端对局页用这个端点回填编辑表单（matchup_stats.js 的
    `editStrikeouts: record.strikeouts`），再 PUT 回去 → **打击三振被抹成 0**，
    并且因为档案是从 game_records 重算的，球员的生涯三振也跟着掉。

本文件锁住：
    1. GET 按记录类型返回对应列的三振
    2. GET → PUT 往返不丢字段
    3. 全项目 dict 字面量里没有重复键（防同类 bug 再犯）
"""
import ast
import io
import os

from database import Player, GameRecord, db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _create(client, name, jersey, is_pitcher=False):
    positions = ['投手'] if is_pitcher else ['游击手']
    resp = client.post('/api/players', json={
        'name': name, 'jersey_number': jersey,
        'is_pitcher': is_pitcher, 'positions': positions,
        'primary_position': positions[0],
    })
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _add_batting(client, player_id, **kw):
    payload = {
        'player_id': player_id, 'game_date': '2025-06-02',
        'opponent': '清华大学', 'is_pitching': False,
        'at_bats': 4, 'runs': 1, 'hits': 2, 'rbi': 1,
        'walks': 0, 'strikeouts': 3,
    }
    payload.update(kw)
    resp = client.post('/api/game_records', json=payload)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['record_id']


def _add_pitching(client, player_id, **kw):
    payload = {
        'player_id': player_id, 'game_date': '2025-06-02',
        'opponent': '清华大学', 'is_pitching': True,
        'innings_pitched': 3.0, 'hits_allowed': 4, 'runs_allowed': 1,
        'earned_runs': 1, 'walks_allowed': 2, 'strikeouts': 5,
    }
    payload.update(kw)
    resp = client.post('/api/game_records', json=payload)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['record_id']


# ====== 三振按记录类型返回 ======

def test_get_batting_record_returns_batting_strikeouts(auth_client):
    """打击记录的三振必须是打击列的值（曾因重复键恒为 0）。"""
    pid = _create(auth_client, '读回打击', '41')
    rid = _add_batting(auth_client, pid, strikeouts=3)

    resp = auth_client.get('/api/game_records/%d' % rid)
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body['strikeouts'] == 3, '打击三振应为 3，实际 %r' % body['strikeouts']
    assert body['is_pitching'] is False


def test_get_pitching_record_returns_pitching_strikeouts(auth_client):
    """投球记录的三振必须是投球列的值。"""
    pid = _create(auth_client, '读回投球', '42', is_pitcher=True)
    rid = _add_pitching(auth_client, pid, strikeouts=5)

    resp = auth_client.get('/api/game_records/%d' % rid)
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body['strikeouts'] == 5, '投球三振应为 5，实际 %r' % body['strikeouts']
    assert body['is_pitching'] is True


# ====== GET → PUT 往返不丢字段 ======

def test_get_then_put_roundtrip_keeps_strikeouts(auth_client):
    """GET 回来的内容原样 PUT 回去，三振必须还在。

    这正是对局页编辑弹窗的完整动作序列。
    """
    pid = _create(auth_client, '往返三振', '43')
    rid = _add_batting(auth_client, pid, at_bats=5, hits=3, strikeouts=3)

    record = auth_client.get('/api/game_records/%d' % rid).get_json()

    payload = {
        'player_id': record['player_id'],
        'game_date': record['game_date'],
        'opponent': record['opponent'],
        'is_pitching': record['is_pitching'],
        'at_bats': record['at_bats'],
        'runs': record['runs'],
        'hits': record['hits'],
        'rbi': record['rbi'],
        'walks': record['walks'],
        'strikeouts': record['strikeouts'],
        'doubles': record['doubles'],
        'triples': record['triples'],
        'home_runs_game': record['home_runs_game'],
        'stolen_bases_game': record['stolen_bases_game'],
        'caught_stealing': record['caught_stealing'],
        'hit_by_pitch': record['hit_by_pitch'],
    }
    resp = auth_client.put('/api/game_records/%d' % rid, json=payload)
    assert resp.status_code == 200, resp.data

    with auth_client.application.app_context():
        rec = db.session.get(GameRecord, rid)
        assert rec.strikeouts == 3, '往返之后打击三振被抹掉了：%r' % rec.strikeouts
        assert rec.at_bats == 5
        assert rec.hits == 3


def test_pitching_get_then_put_roundtrip_keeps_strikeouts(auth_client):
    """投球记录同样不能丢三振。"""
    pid = _create(auth_client, '往返投球三振', '44', is_pitcher=True)
    rid = _add_pitching(auth_client, pid, strikeouts=7)

    record = auth_client.get('/api/game_records/%d' % rid).get_json()
    assert record['strikeouts'] == 7

    resp = auth_client.put('/api/game_records/%d' % rid, json={
        'player_id': record['player_id'],
        'game_date': record['game_date'],
        'opponent': record['opponent'],
        'is_pitching': True,
        'innings_pitched': record['innings_pitched'],
        'hits_allowed': record['hits_allowed'],
        'runs_allowed': record['runs_allowed'],
        'earned_runs': record['earned_runs'],
        'walks_allowed': record['walks_allowed'],
        'strikeouts': record['strikeouts'],
        'home_runs_allowed': record['home_runs_allowed'],
        'pitches': record['pitches'],
        'strikes': record['strikes'],
        'batters_faced': record['batters_faced'],
    })
    assert resp.status_code == 200, resp.data

    with auth_client.application.app_context():
        rec = db.session.get(GameRecord, rid)
        assert rec.strikeouts_pitched == 7
        assert rec.innings_pitched == 3.0


# ====== 全项目：dict 字面量里不允许重复键 ======

def test_no_duplicate_keys_in_dict_literals():
    """重复键 = 后者静默覆盖前者 = 字段凭空消失。

    这道检查把整类 bug 挡在门外，比只修一个键更可靠。
    """
    offenders = []
    for filename in ['app.py', 'database.py', 'import_pdfs.py', 'sync_data.py']:
        path = os.path.join(REPO_ROOT, filename)
        if not os.path.exists(path):
            continue
        with io.open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen = {}
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    seen.setdefault(key.value, []).append(key.lineno)
            for key, linenos in seen.items():
                if len(linenos) > 1:
                    offenders.append('%s:%d 键 %r 重复于 %s' %
                                     (filename, node.lineno, key, linenos))
    assert not offenders, 'dict 字面量里出现重复键：\n' + '\n'.join(offenders)
