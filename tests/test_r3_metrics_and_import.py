"""
Phase R3 测试 —— 指标引擎 + 导入路径 + PDF 解析
============================================================
覆盖本轮三块改动：
    1. metrics.py：局数换算与统一公式（含 OBP 补上 SH）
    2. import_pdfs.py：只写记录+重建档案、覆盖模式、未知姓名不建球员
    3. pdf_parser_columns.py：按列坐标解析（不把对方球员混进我方）
"""
import os

import pytest

from database import Player, GameRecord, db
from metrics import (
    innings_to_true, format_innings, era, whip, on_base_percentage, total_bases, ops, strike_percentage,
)


# ====== 1. 指标引擎 ======

def test_innings_to_true_chinese_notation():
    """中文记法：.1 = 1/3 局，.2 = 2/3 局。"""
    assert innings_to_true(3.0) == 3.0
    assert innings_to_true(0.0) == 0.0
    assert round(innings_to_true(1.1), 4) == 1.3333      # 1⅓
    assert round(innings_to_true(0.1), 4) == 0.3333      # ⅓
    assert round(innings_to_true(0.2), 4) == 0.6667      # ⅔
    assert round(innings_to_true(1.2), 4) == 1.6667      # 1⅔
    assert round(innings_to_true(2.1), 4) == 2.3333      # 2⅓


def test_innings_to_true_handles_garbage():
    assert innings_to_true(None) == 0.0
    assert innings_to_true('') == 0.0
    assert innings_to_true('abc') == 0.0
    assert innings_to_true(-1) == 0.0


def test_format_innings_roundtrip():
    """真实局数 ↔ 记法显示。"""
    assert format_innings(3.0) == '3'
    assert format_innings(1 + 1 / 3) == '1.1'
    assert format_innings(2 + 2 / 3) == '2.2'
    assert format_innings(0) == '0'


def test_era_uses_true_innings():
    """ERA 必须用真实局数：1⅓ 局失 1 分 → 1*9/1.333 = 6.75。"""
    assert era(1, innings_to_true(1.1)) == 6.75
    # 旧算法（用字面 1.1）会算成 8.18 —— 偏高 21%
    assert era(1, 1.1) == 8.18


def test_whip_uses_true_innings():
    assert whip(3, 2, innings_to_true(1.1)) == 3.75
    assert whip(3, 2, 0) == 0.0


def test_on_base_percentage_includes_sacrifice_hits():
    """OBP 分母必须含牺牲触击(SH) —— 修复前漏了。"""
    # H=1, BB=0, HBP=0, SF=0, SH=1, AB=1 → PA=2 → OBP=0.5
    assert on_base_percentage(1, 0, 0, 0, 1, 1) == 0.5
    # 修复前分母只有 1 → 会算成 1.0
    assert on_base_percentage(1, 0, 0, 0, 0, 1) == 1.0


def test_total_bases_and_ops():
    assert total_bases(3, 1, 0, 1) == 7      # 1一垒+1二垒+1本垒打
    assert total_bases(3, 1, 1, 1) == 9
    assert ops(0.300, 0.400) == 0.7
    assert strike_percentage(40, 60) == 66.7


def test_metrics_module_is_the_only_source():
    """指标公式只应在 metrics.py 里 —— 其它地方不许再自己算 ERA。

    扫 Python **和** JS：前端曾有一份 ERA/WHIP/OBP 的拷贝（static/js/script.js），
    而且用的是**局数字面值**（1.1 当成 1.1 局而不是 1⅓ 局）——
    网页上预览的 ERA 和服务器存下来的 ERA 对不上。
    """
    import re
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    offenders = []
    # metrics.py 是权威来源本身，不在扫描范围内
    py_files = ['app.py', 'database.py', 'import_pdfs.py', 'cleanup_db.py',
                'migrate_profiles_sqlite.py', 'sync_data.py']
    for name in py_files:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as fh:
            for lineno, line in enumerate(fh, 1):
                # 形如 earned_runs * 9 / ... 的自算公式
                if re.search(r'\*\s*9\s*\)\s*/|\*\s*9\s*/', line):
                    offenders.append('%s:%d %s' % (name, lineno, line.strip()))
    js_dir = os.path.join(root, 'static', 'js')
    if os.path.isdir(js_dir):
        for name in sorted(os.listdir(js_dir)):
            if not name.endswith('.js'):
                continue
            path = os.path.join(js_dir, name)
            with open(path, encoding='utf-8') as fh:
                for lineno, line in enumerate(fh, 1):
                    if re.search(r'\*\s*9\s*\)\s*/|\*\s*9\s*/', line):
                        offenders.append('static/js/%s:%d %s'
                                         % (name, lineno, line.strip()))
    assert not offenders, '这些地方还在自己算 ERA，应改用 metrics.era：\n' + '\n'.join(offenders)


# ====== 2. 导入路径 ======

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


def _parsed_pitching(name, **kw):
    data = {'name': name, 'jersey_number': '22', 'position': 'P',
            'innings_pitched': 3.0, 'hits_allowed': 4, 'runs_allowed': 1,
            'earned_runs': 1, 'walks_allowed': 2, 'strikeouts': 5,
            'home_runs_allowed': 0, 'pitches': 60, 'strikes': 40,
            'hit_by_pitch_allowed': 0, 'batters_faced': 12,
            'wild_pitches': 0, 'win': False, 'loss': False, 'save': False}
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


def test_import_writes_records_and_rebuilds_profile(auth_client):
    """导入后档案必须精确等于 game_records 之和（不是增量累加的结果）。"""
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        pid = _create_player(auth_client, '导入测试', '31')
        result = import_game_record(_parsed_game(batting=[_parsed_batting('导入测试')]))
        assert result['status'] == 'ok'
        assert result['batting'] == 1

        player = db.session.get(Player, pid)
        assert player.at_bats_total == 4
        assert player.hits_total == 2
        assert player.rbi_total == 1
        # 派生率由档案算出
        assert player.batting_average == 0.5


def test_import_is_idempotent_without_replace(auth_client):
    """默认模式下重复导入同��场 → 跳过，不产生重复记录。"""
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        pid = _create_player(auth_client, '幂等测试', '32')
        game = _parsed_game(batting=[_parsed_batting('幂等测试')])
        import_game_record(game)
        import_game_record(game)
        count = db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == pid).scalar()
        assert count == 1
        player = db.session.get(Player, pid)
        assert player.at_bats_total == 4, '重复导入不得让累计翻倍'


def test_import_replace_mode_replaces_records(auth_client):
    """覆盖模式：同场比赛的旧记录被新解析的数据替换。"""
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        pid = _create_player(auth_client, '覆盖测试', '33')
        import_game_record(_parsed_game(batting=[_parsed_batting('覆盖测试', at_bats=9)]))
        assert db.session.get(Player, pid).at_bats_total == 9

        result = import_game_record(
            _parsed_game(batting=[_parsed_batting('覆盖测试', at_bats=2, hits=1)]),
            replace=True)
        assert result['replaced'] == 1

        count = db.session.query(db.func.count(GameRecord.id)).filter(
            GameRecord.player_id == pid).scalar()
        assert count == 1, '覆盖模式应替换而不是追加'
        player = db.session.get(Player, pid)
        assert player.at_bats_total == 2, '档案必须跟着新记录重算'
        assert player.hits_total == 1


def test_import_does_not_create_unknown_players(auth_client):
    """未知姓名不得凭空建球员（Phase R3 修的幽灵球员 bug）。"""
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        before = Player.query.count()
        result = import_game_record(
            _parsed_game(batting=[_parsed_batting('齐佳王佳帅')]),
            allow_new_players=False)
        assert result['unknown_names']
        assert result['unknown_names'][0]['name'] == '齐佳王佳帅'
        assert Player.query.count() == before, '未知姓名不该建出新球员'


def test_import_never_increments_profile(auth_client):
    """导入走的是「写记录 + 重建」，档案必须恒等于记录之和。

    旧实现是 `player.at_bats_total += ...`，一旦历史上有漂移就会越积越错。
    """
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        pid = _create_player(auth_client, '不增量', '34')
        import_game_record(_parsed_game(batting=[_parsed_batting('不增量')]))
        # 手动把档案改坏，模拟历史漂移
        player = db.session.get(Player, pid)
        player.at_bats_total = 999
        db.session.commit()

        import_game_record(_parsed_game(batting=[_parsed_batting('不增量')]))
        db.session.refresh(player)
        # 若用增量，档案会是 999+4=1003；用重建则回到 4
        assert player.at_bats_total == 4


# ====== 3. PDF 解析（列坐标版） ======

PDF_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))


def _pdf(name):
    return os.path.join(PDF_DIR, name)


REPRESENTATIVE_PDFS = [
    '2023/北京工业大学_vs_北京交通大学_Apr_9_2023.pdf',        # 2023 窄版式
    '2024/北京工业大学_vs_北京交通大学_Nov_16_2024(2).pdf',   # 2024 宽版式
    '2025/中国地质大学_vs_北京工业大学_Oct_18_2025(1).pdf',   # 我方在右栏
]


# 队里 27 名球员（2026-10-29 的名单）。
# 固化成特征测试基准 —— 测试库是空的，不能靠查库得到名单；
# 而"解析出的名字必须都是队里的人"正是要锁住的不变量。
ROSTER = {
    '于凯泽', '仇志豪', '刘孝宇', '吴鸿硕', '夏诚明', '尹端毅', '崔博宇',
    '崔洲齐', '左昊童', '张家昊', '张宸', '朱骏骋', '李昊宇', '杨宇轩',
    '杨景旭', '杨润琦', '欧阳翦', '王家润', '田潇宇', '白云箫', '翁奇雁',
    '聂千盛', '蒙佳慕', '韩登越', '马绍翔', '黄钰洲', '齐佳',
}

# PDF 里出现、但队里没有对应球员的名字 —— 都是**已知的记分卡歧义**，
# 不是解析错误：
#   '欧阳'：2024-11-16 的记分卡上有两行都是 #23 —— '欧阳 #23 (RF)' 和
#           '欧阳翦 #23 (P)'。是同一人列了两行，还是两个共用号码的人？
#           **尚未定论**（HANDOFF 待确认项）。
#           导入时它会模糊匹配并入「欧阳翦」，并在导入报告里显式报出来。
KNOWN_PDF_AMBIGUITIES = {'欧阳'}


@pytest.mark.parametrize('relpath', REPRESENTATIVE_PDFS)
def test_parser_does_not_mix_in_opponent_players(app, relpath):
    """解析结果里不得出现对方球员 —— 旧版会混进 '子非陈'/'孙世铎'/'齐佳王佳帅'。"""
    from pdf_ingest import parse_pdf
    path = _pdf(relpath)
    if not os.path.exists(path):
        pytest.skip('PDF 不存在: %s' % relpath)

    result = parse_pdf(path)
    assert 'error' not in result, result.get('error')

    names = [p['name'].replace(' ', '') for p in result['my_team_batting']]
    names += [p['name'].replace(' ', '') for p in result['my_team_pitching']]
    assert names, '应该解析出球员'
    for name in names:
        assert name in ROSTER or name in KNOWN_PDF_AMBIGUITIES, \
            '解析出了队里没有的球员: %r' % name


def test_fuzzy_match_is_reported_not_silent(auth_client):
    """模糊匹配必须出现在导入报告里 —— 不许静默把两个名字合并。"""
    from import_pdfs import import_game_record
    with auth_client.application.app_context():
        _create_player(auth_client, '欧阳翦', '23', is_pitcher=True)
        result = import_game_record(
            _parsed_game(batting=[_parsed_batting('欧阳')]),
            allow_new_players=False)
        assert result['fuzzy_matches'], '模糊匹配必须被记录'
        match = result['fuzzy_matches'][0]
        assert match['parsed'] == '欧阳'
        assert match['matched'] == '欧阳翦'
        # 并且没有凭空建出新球员
        assert Player.query.filter_by(name='欧阳').first() is None


def test_parser_totals_match_pdf_totals_row():
    """解析出的球员合计必须等于 PDF 自己的 Totals 行（独立真值）。"""
    from pdf_ingest import parse_pdf
    from scripts.validate_pdf_parse import our_totals
    path = _pdf(REPRESENTATIVE_PDFS[1])
    if not os.path.exists(path):
        pytest.skip('PDF 不存在')

    bat_totals, _pit_totals = our_totals(path)
    result = parse_pdf(path)
    mine = [sum(x[k] for x in result['my_team_batting'])
            for k in ('at_bats', 'runs', 'hits', 'rbi', 'walks', 'strikeouts')]
    assert [int(v) for v in bat_totals] == mine


def test_parser_total_bases_self_check():
    """解析器自校验：自算 TB 必须等于 PDF 的 TB 标签（2B/3B/HR 归属正确）。"""
    from pdf_ingest import parse_pdf
    path = _pdf(REPRESENTATIVE_PDFS[1])
    if not os.path.exists(path):
        pytest.skip('PDF 不存在')
    result = parse_pdf(path)
    checked = [p for p in result['my_team_batting'] if 'tb_from_pdf' in p]
    assert checked, '应该有可核对的球员'
    for player in checked:
        assert player['tb_matches'], (
            'TB 不符: %s 自算=%s PDF=%s (H=%s 2B=%s 3B=%s HR=%s)'
            % (player['name'], player['total_bases'], player['tb_from_pdf'],
               player['hits'], player['doubles'], player['triples'],
               player['home_runs']))
