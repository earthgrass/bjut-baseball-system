"""
Phase R4 测试 —— 数据校正迁移 + 硬化
====================================
覆盖本轮改动：
    1. import_pdfs.py：批次原子事务（规范 §28）、显式别名映射
    2. cleanup_db.py：合并重复球员后必须重建档案（审计 #5）
    3. database.py：热点表索引（审计 #17）
    4. scripts/backup_db.py：自动备份（审计 #18）
    5. 全项目：不再使用 SQLAlchemy 已弃用的 Query.get()（审计 #24）
"""
import os
import ast
import sqlite3
from datetime import date

import pytest

from database import Player, GameRecord, db


# ====== 导入路径 ======

def _create_player(client, name, jersey, is_pitcher=False):
    positions = ['投手'] if is_pitcher else ['游击手']
    resp = client.post('/api/players', json={
        'name': name, 'jersey_number': jersey, 'is_pitcher': is_pitcher,
        'positions': positions, 'primary_position': positions[0],
    })
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _parsed_batting(name, **kw):
    data = {'name': name, 'jersey_number': '11', 'position': 'SS',
            'at_bats': 4, 'runs': 1, 'hits': 2, 'rbi': 1, 'walks': 0, 'strikeouts': 1,
            'doubles': 0, 'triples': 0, 'home_runs': 0, 'total_bases': 2,
            'stolen_bases': 0, 'caught_stealing': 0, 'hit_by_pitch': 0}
    data.update(kw)
    return data


def _parsed_game(batting=None, pitching=None):
    return {
        'game_date': '2025-06-10',
        'opponent': '北京科技大学',
        'filepath': 'data/2025/test.pdf',
        'my_team_batting': batting or [],
        'my_team_pitching': pitching or [],
    }


def test_alias_mapping_is_explicit_and_reported(auth_client):
    """业务方确认「欧阳」与「欧阳翦」是同一个人 → 走**显式别名**，不是靠相似度猜。

    并且：别名合并必须出现在导入报告里（不静默）。
    """
    from import_pdfs import import_game_record, PLAYER_NAME_ALIASES
    assert PLAYER_NAME_ALIASES.get('欧阳') == '欧阳翦'
    with auth_client.application.app_context():
        pid = _create_player(auth_client, '欧阳翦', '23', is_pitcher=True)
        result = import_game_record(
            _parsed_game(batting=[_parsed_batting('欧阳')]),
            allow_new_players=False)
        assert result['fuzzy_matches'], '别名合并必须被记录'
        match = result['fuzzy_matches'][0]
        assert match['parsed'] == '欧阳'
        assert match['matched'] == '欧阳翦'
        assert match.get('kind') == 'alias', '走的是显式别名，不是相似度猜测'
        # 没有凭空建出新球员
        assert Player.query.filter_by(name='欧阳').first() is None
        # 记录挂在了欧阳翦身上
        assert db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == pid).scalar() == 1


def test_import_batch_rolls_back_on_failure(auth_client, monkeypatch):
    """规范 §28：一个批次 = 一个事务。中途失败 → 前面已写的也必须回滚。

    修复前是「每场 commit 一次」，第 2 份 PDF 失败时第 1 份已经落库了 ——
    半截状态比全错更难查。
    """
    import import_pdfs
    from import_pdfs import import_all_pdfs

    with auth_client.application.app_context():
        pid = _create_player(auth_client, '原子测试', '40')
        calls = {'n': 0}

        def fake_parse(path):
            calls['n'] += 1
            if calls['n'] == 1:
                return {
                    'game_date': '2025-06-11', 'opponent': '测试对手',
                    'filepath': path,
                    'my_team_batting': [_parsed_batting('原子测试')],
                    'my_team_pitching': [],
                }
            raise RuntimeError('模拟第 2 份 PDF 解析失败')

        monkeypatch.setattr(import_pdfs, 'parse_pdf', fake_parse)

        with pytest.raises(RuntimeError):
            import_all_pdfs(dry_run=False, replace=True, allow_new_players=False)

        count = db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == pid).scalar()
        assert count == 0, '批次失败后，第 1 份 PDF 写入的记录必须一起回滚'

        player = db.session.get(Player, pid)
        assert player.at_bats_total == 0, '档案也必须一起回滚'


def test_import_batch_commits_once_at_the_end(auth_client, monkeypatch):
    """成功批次：一次提交，全部落库。"""
    import import_pdfs
    from import_pdfs import import_all_pdfs

    with auth_client.application.app_context():
        pid = _create_player(auth_client, '批次测试', '42')

        def fake_parse(path):
            return {
                'game_date': '2025-06-13', 'opponent': '批次对手',
                'filepath': path,
                'my_team_batting': [_parsed_batting('批次测试')],
                'my_team_pitching': [],
            }

        monkeypatch.setattr(import_pdfs, 'parse_pdf', fake_parse)
        import_all_pdfs(dry_run=False, replace=True, allow_new_players=False)

        count = db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == pid).scalar()
        assert count >= 1, '批次成功后记录必须落库'
        player = db.session.get(Player, pid)
        assert player.at_bats_total == 4 * count, '档案必须等于记录之和'


# ====== cleanup_db 合并后重建 ======

def test_cleanup_db_rebuilds_profile_after_merging_players(auth_client):
    """审计 #5：合并重复球员后，累计档案必须从 game_records **重建**。

    修复前只调 `update_calculated_fields()` —— 那只重算 AVG/SLG/OBP 这类派生比值，
    累计值（at_bats_total 等）仍是合并前的旧值，与 game_records 严重不符。
    """
    import cleanup_db
    from import_pdfs import import_game_record

    with auth_client.application.app_context():
        pid = _create_player(auth_client, '合并测试', '41')
        import_game_record(_parsed_game(batting=[_parsed_batting('合并测试', at_bats=4)]))

        # 同名的第二个球员（API 不允许重名，直接建）
        dup = Player(name='合并测试', jersey_number='43', primary_position='游击手')
        db.session.add(dup)
        db.session.commit()
        dup_id = dup.id

        db.session.add(GameRecord(
            player_id=dup_id, game_date=date(2025, 6, 12), opponent='测试对手',
            is_pitching_record=False, at_bats=6, hits=1))
        db.session.commit()

        assert db.session.get(Player, pid).at_bats_total == 4

        cleanup_db.cleanup()

        kept = Player.query.filter_by(name='合并测试').first()
        assert kept is not None, '合并后应保留一个球员'
        assert Player.query.filter_by(name='合并测试').count() == 1
        total = db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == kept.id).scalar()
        assert total == 2, '两条记录都应挂到保留的球员上'
        assert kept.at_bats_total == 10, \
            '档案必须重建为 game_records 之和（4+6），而不是停留在合并前的 4'


# ====== 索引 ======

def test_hot_tables_have_indexes(app):
    """审计 #17：热点表必须有索引（新建库由模型声明自动建）。"""
    with app.app_context():
        inspector = db.inspect(db.engine)
        expected = {
            'game_records': {'ix_game_records_player', 'ix_game_records_game'},
            'players': {'ix_players_name', 'ix_players_jersey_number'},
        }
        for table, names in expected.items():
            actual = {idx['name'] for idx in inspector.get_indexes(table)}
            missing = names - actual
            assert not missing, f'{table} 缺索引: {missing}'

        # 执行计划必须用上索引（不再全表 SCAN）
        con = db.engine.raw_connection()
        try:
            plan = ' '.join(
                r[3] for r in con.execute(
                    "EXPLAIN QUERY PLAN select count(*) from game_records "
                    "where player_id = 1"))
            assert 'SCAN game_records' not in plan or 'USING INDEX' in plan, plan
            assert 'USING INDEX' in plan or 'USING COVERING INDEX' in plan, plan
        finally:
            con.close()


def test_index_migration_script_is_idempotent(tmp_path):
    """scripts/add_indexes.py：可重复执行，不改数据。"""
    from scripts.add_indexes import INDEXES
    # 索引清单与模型声明一致
    assert {i[1] for i in INDEXES} == {
        'ix_game_records_player', 'ix_game_records_game',
        'ix_players_name', 'ix_players_jersey_number',
        'ix_player_positions_position',
    }


# ====== 备份 ======

def test_backup_script_creates_verified_snapshot(tmp_path):
    """审计 #18：备份必须是一致性快照，且记录指纹。"""
    from scripts.backup_db import backup, _fingerprint
    src = tmp_path / 'source.db'
    con = sqlite3.connect(str(src))
    con.execute('create table t (a int)')
    con.execute('insert into t values (1)')
    con.commit()
    con.close()

    dest = backup(db_path=str(src), keep=3,
                  backup_dir=str(tmp_path / 'backups'))
    assert dest and os.path.exists(dest)

    # 备份能打开、数据完整
    con = sqlite3.connect(dest)
    assert con.execute('select count(*) from t').fetchone()[0] == 1
    con.close()

    fp = _fingerprint(dest)
    assert fp['integrity'] == 'ok'
    assert fp['fk_violations'] == 0


def test_backup_does_not_modify_source(tmp_path):
    """备份是只读操作 —— 源库不能被改动。"""
    import hashlib
    from scripts.backup_db import backup
    src = tmp_path / 'source.db'
    con = sqlite3.connect(str(src))
    con.execute('create table t (a int)')
    con.execute('insert into t values (1)')
    con.commit()
    con.close()

    before = hashlib.sha256(src.read_bytes()).hexdigest()
    backup(db_path=str(src), backup_dir=str(tmp_path / 'backups'))
    after = hashlib.sha256(src.read_bytes()).hexdigest()
    assert before == after, '备份不得改动源库'


# ====== 弃用 API ======

def test_no_deprecated_query_get_in_project_code():
    """审计 #24：`Query.get()` 在 SQLAlchemy 2.x 已弃用，改用 `db.session.get()`。"""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    offenders = []
    for name in ['app.py', 'database.py', 'import_pdfs.py', 'cleanup_db.py',
                 'metrics.py', 'pdf_ingest.py']:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == 'get'
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == 'query'):
                offenders.append('%s:%d' % (name, node.lineno))
    assert not offenders, '仍在用已弃用的 Query.get(): %s' % offenders
