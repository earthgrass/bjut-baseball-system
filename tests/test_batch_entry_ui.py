"""
批量录入界面的服务端测试 —— Phase R2

页面是「批量录入整场比赛」的前端入口，后端写入走
POST /api/game_records/batch（全有或全无）。

这里锁三件事：
  1. 页面权限：只有管理员能进
  2. 页面结构：两个粘贴框 + 预览表 + 提交按钮都在
  3. 一次批量写入（打击 + 投球混合）之后，档案依然等于 game_records 之和

解析器本身的单元测试在 tests/js/batch_entry.test.js（node --test）。
本文件在有 node 的环境里会把它一起跑一遍。
"""
import os
import shutil
import subprocess

import pytest
from sqlalchemy import func

from database import Player, GameRecord, db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
JS_TEST = os.path.join(os.path.dirname(__file__), 'js', 'batch_entry.test.js')


# ====== 页面权限 ======

def test_batch_entry_requires_auth(client):
    """未登录访问批量录入页 → 跳登录。"""
    resp = client.get('/batch_entry')
    assert resp.status_code == 302, resp.status_code


def test_batch_entry_requires_admin(auth_client):
    """非管理员访问 → 也跳登录（admin_required 覆盖 login_required）。"""
    from database import User
    with auth_client.application.app_context():
        user = User.query.filter_by(username='admin').first()
        user.is_admin = False
        db.session.commit()

    resp = auth_client.get('/batch_entry')
    assert resp.status_code == 302, resp.status_code


def test_batch_entry_renders_for_admin(auth_client):
    """管理员能看到页面：两个粘贴框、预览表、提交按钮。"""
    resp = auth_client.get('/batch_entry')
    assert resp.status_code == 200, resp.status_code

    html = resp.data.decode('utf-8')
    assert 'id="battingInput"' in html
    assert 'id="pitchingInput"' in html
    assert 'id="batchGameDate"' in html
    assert 'id="batchOpponent"' in html
    assert 'id="battingPreview"' in html
    assert 'id="pitchingPreview"' in html
    assert 'id="batchSubmitBtn"' in html
    # CSRF token meta 必须存在（api.js 靠它给写操作加 X-CSRFToken）
    assert 'name="csrf-token"' in html


def test_navbar_links_to_batch_entry(auth_client):
    """导航栏要有「批量录入」入口（桌面 + 移动端两处）。"""
    resp = auth_client.get('/batch_entry')
    html = resp.data.decode('utf-8')
    assert '/batch_entry' in html
    assert '批量录入' in html


# ====== 批量写入后不变量仍然成立 ======

def _create(client, name, jersey, is_pitcher=False):
    positions = ['投手'] if is_pitcher else ['游击手']
    resp = client.post('/api/players', json={
        'name': name, 'jersey_number': jersey,
        'is_pitcher': is_pitcher, 'positions': positions,
        'primary_position': positions[0],
    })
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def test_batch_entry_write_keeps_invariant(auth_client):
    """一次批量写入（打击 + 投球混合）后，两个档案都必须等于记录之和。

    这正是批量录入页面提交后的路径。
    """
    batter = _create(auth_client, '批量打击手', '71')
    pitcher = _create(auth_client, '批量投手', '72', is_pitcher=True)

    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025-05-06',
        'opponent': '北京科技大学',
        'records': [
            {'player_id': batter, 'is_pitching': False,
             'at_bats': 4, 'runs': 1, 'hits': 2, 'rbi': 1,
             'walks': 0, 'strikeouts': 1},
            {'player_id': pitcher, 'is_pitching': True,
             'innings_pitched': 3.0, 'hits_allowed': 4, 'runs_allowed': 1,
             'earned_runs': 1, 'walks_allowed': 2, 'strikeouts': 5},
        ],
    })
    assert resp.status_code == 201, resp.data
    assert resp.get_json()['created'] == 2

    with auth_client.application.app_context():
        b = db.session.get(Player, batter)
        p = db.session.get(Player, pitcher)

        bat_sum = db.session.query(func.sum(GameRecord.at_bats)).filter(
            GameRecord.player_id == batter).scalar()
        assert b.at_bats_total == bat_sum == 4
        assert b.hits_total == 2

        pit_sum = db.session.query(func.sum(GameRecord.innings_pitched)).filter(
            GameRecord.player_id == pitcher).scalar()
        assert p.innings_pitched_total == pit_sum == 3.0
        assert p.earned_runs_total == 1
        assert p.era == round(1 * 9 / 3.0, 2)


def test_batch_entry_write_rejects_fielder_as_pitcher(auth_client):
    """页面会在客户端拦这一条，后端也必须拦（不能只靠前端校验）。"""
    batter = _create(auth_client, '不是投手', '73')

    resp = auth_client.post('/api/game_records/batch', json={
        'game_date': '2025-05-07',
        'opponent': '北京科技大学',
        'records': [
            {'player_id': batter, 'is_pitching': True,
             'innings_pitched': 3.0, 'hits_allowed': 0, 'runs_allowed': 0,
             'earned_runs': 0, 'walks_allowed': 0, 'strikeouts': 0},
        ],
    })
    assert resp.status_code == 400, resp.data

    with auth_client.application.app_context():
        assert db.session.query(func.count(GameRecord.id)).filter(
            GameRecord.player_id == batter).scalar() == 0


# ====== JS 解析器单测（node 存在时一并跑） ======

@pytest.mark.skipif(shutil.which('node') is None,
                    reason='未安装 node，无法运行 static/js 的解析器单测')
def test_batch_entry_parser_unit_tests():
    """跑 tests/js/batch_entry.test.js —— 解析器是「粘贴→写入」之间唯一的转换环节。"""
    result = subprocess.run(
        ['node', '--test', JS_TEST],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding='utf-8',
        errors='replace',
    )
    assert result.returncode == 0, (
        'node --test 失败：\n' + (result.stdout or '') + (result.stderr or '')
    )
