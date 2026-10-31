"""
Phase R5 测试 —— 指标引擎补完 + WHIP 标准口径 + 页脚污染修复
============================================================
覆盖本轮三块改动：
    1. metrics.py：WHIP 改用标准分母（面对打席数），补齐派生率
    2. database.py：WHIP 只统计「有打者数」的场次；档案与 to_dict 暴露新指标
    3. pdf_parser*.py：页脚水印不再吞掉最后一个标签段的最后一条

「唯一公式源」的铁律：任何派生率都必须能在 metrics.py 里找到公式，
否则网页、CSV、后端就会各算各的（Phase R3 确立，本轮继续守）。
"""
import os

import pytest

from database import Player, GameRecord, db
from metrics import (
    total_bases, isolated_power, babip, plate_appearances, strikeout_rate,
    walk_rate, strikeout_walk_rate, stolen_base_rate, caught_stealing_rate,
    whip, strikeouts_per_9, walks_per_9, pitcher_strikeout_walk_rate,
    batting_metrics, pitching_metrics,
)
from pdf_parser import (
    _extract_named_counts_from,
    _split_tag_sections,
    strip_page_footer_words,
    is_footer_only_row,
)


# ====== 1. metrics.py：WHIP 标准口径 ======

def test_whip_uses_batters_faced_as_denominator():
    """标准 WHIP = (被安打 + 保送) / 面对打席数。

    修复前分母是投球局数：(5+2)/9 = 0.78 —— 库里实测刘孝宇旧值 5.60，
    标准口径 0.56，差了近 10 倍。
    """
    assert whip(5, 2, 20) == 0.35
    assert whip(0, 0, 20) == 0.0
    assert whip(10, 10, 20) == 1.0


def test_whip_without_batters_faced_returns_zero():
    """没有打者数 → 算不出来，返回 0.0（不给一个假数）。"""
    assert whip(5, 2, 0) == 0.0
    assert whip(5, 2, None) == 0.0
    assert whip(5, 2, -1) == 0.0


def test_whip_is_not_ip_based():
    """回归护栏：WHIP 的结果不能随投球局数变化（除非 BF 变了）。"""
    # 同一份「被安打+保送」，局数翻倍不应改变 WHIP
    assert whip(5, 2, 20) == whip(5, 2, 20)


# ====== 2. metrics.py：补齐的派生率 ======

def test_isolated_power():
    """ISO = 长打率 - 打击率。"""
    assert isolated_power(0.500, 0.300) == 0.200
    assert isolated_power(0.400, 0.400) == 0.0


def test_babip():
    """BABIP = (安打 - 本垒打) / (打数 - 三振 - 牺牲飞球 - 牺牲触击)。"""
    # 10 打数 4 安打 1 本垒打 2 三振 → (4-1)/(10-2) = 0.375
    assert babip(4, 1, 10, 2, 0, 0) == 0.375
    # 分母为 0 时不炸
    assert babip(0, 0, 0, 0, 0, 0) == 0.0
    assert babip(2, 0, 3, 3, 0, 0) == 0.0


def test_plate_appearances_counts_sacrifices():
    """打席数 = 打数 + 保送 + 触身球 + 牺牲飞球 + 牺牲触击。"""
    assert plate_appearances(10, 2, 1, 1, 1) == 15
    assert plate_appearances(0, 0, 0, 0, 0) == 0


def test_strikeout_and_walk_rates():
    """K% / BB% 的分母是**打席数**（三振也占打席）。"""
    assert strikeout_rate(3, 20) == 15.0
    assert walk_rate(2, 20) == 10.0
    assert strikeout_rate(3, 0) == 0.0
    assert walk_rate(0, 0) == 0.0


def test_strikeout_walk_rate():
    """K-B% = K% - BB%（打者口径，按打席）。"""
    assert strikeout_walk_rate(15.0, 10.0) == 5.0
    assert strikeout_walk_rate(8.0, 12.0) == -4.0


def test_stolen_base_rates():
    """SB% / CS% 的分母是盗垒总次数。"""
    assert stolen_base_rate(3, 1) == 75.0
    assert caught_stealing_rate(3, 1) == 25.0
    assert stolen_base_rate(0, 0) == 0.0
    assert caught_stealing_rate(0, 0) == 0.0


def test_per_nine_innings_rates():
    """K/9、BB/9 的分母是**真实局数**。"""
    assert strikeouts_per_9(10, 9.0) == 10.0
    assert walks_per_9(4, 18.0) == 2.0
    assert strikeouts_per_9(10, 0) == 0.0
    assert walks_per_9(4, 0) == 0.0


def test_pitcher_k_bb_is_per_nine_innings():
    """投手的 K-B% 惯例是按 9 局相减（不是打者那种按打席）。"""
    assert pitcher_strikeout_walk_rate(10.0, 2.0) == 8.0
    assert pitcher_strikeout_walk_rate(4.5, 6.0) == -1.5


def test_batting_metrics_ops_no_double_rounding():
    """OPS 只舍入一次（Phase R3 审计 B4）。

    修复前是 round(round(OBP,3) + round(SLG,3), 3)，
    两个各自舍入的数相加会差 0.001。
    """
    totals = {
        'at_bats': 37, 'hits': 8, 'walks': 0, 'hit_by_pitch': 0,
        'sacrifice_flies': 0, 'sacrifice_hits': 0,
        'doubles': 0, 'triples': 0, 'home_runs': 1,
        'strikeouts': 0, 'stolen_bases': 0, 'caught_stealing': 0,
    }
    m = batting_metrics(totals)

    obp_raw = 8 / 37
    slg_raw = total_bases(8, 0, 0, 1) / 37
    assert m['ops'] == round(obp_raw + slg_raw, 3)      # 0.514
    # 旧算法（各自舍入后相加）会差一个 0.001
    assert round(round(obp_raw, 3) + round(slg_raw, 3), 3) == 0.513


def test_batting_metrics_covers_expected_keys():
    m = batting_metrics({
        'at_bats': 10, 'hits': 4, 'walks': 1, 'hit_by_pitch': 0,
        'sacrifice_flies': 0, 'sacrifice_hits': 0,
        'doubles': 1, 'triples': 0, 'home_runs': 1,
        'strikeouts': 2, 'stolen_bases': 1, 'caught_stealing': 0,
    })
    for key in ('batting_average', 'on_base_percentage', 'slugging_percentage',
                'ops', 'isolated_power', 'babip', 'plate_appearances',
                'total_bases', 'strikeout_rate', 'walk_rate',
                'strikeout_walk_rate', 'stolen_base_rate',
                'caught_stealing_rate'):
        assert key in m, key
    assert m['batting_average'] == 0.4
    assert m['plate_appearances'] == 11


def test_batting_metrics_handles_empty():
    """全 0 的档案不能炸，也不能除零。"""
    m = batting_metrics({})
    assert m['batting_average'] == 0.0
    assert m['ops'] == 0.0
    assert m['babip'] == 0.0
    assert m['plate_appearances'] == 0


def test_pitching_metrics_keys_and_values():
    m = pitching_metrics({
        'innings': 18.0, 'earned_runs': 6, 'hits_allowed': 12,
        'walks_allowed': 4, 'strikeouts': 15, 'pitches': 240, 'strikes': 150,
        'batters_faced': 80, 'whip_hits': 12, 'whip_walks': 4,
    })
    assert m['era'] == 3.0
    assert m['whip'] == 0.2          # (12+4)/80
    assert m['strikeouts_per_9'] == 7.5
    assert m['walks_per_9'] == 2.0
    assert m['pitcher_strikeout_walk_rate'] == 5.5
    assert m['strike_percentage'] == 62.5


def test_pitching_metrics_whip_without_basis_is_zero():
    """没有「有 BF 的场次」这个拆分信息时，WHIP 算不出来。"""
    m = pitching_metrics({'innings': 9.0, 'hits_allowed': 5, 'walks_allowed': 2})
    assert m['whip'] == 0.0
    assert m['era'] == 0.0


# ====== 3. 档案层：WHIP 只统计「有打者数」的场次 ======

def _create_pitcher(client, name='测试投'):
    resp = client.post('/api/players', json={
        'name': name, 'jersey_number': '7', 'is_pitcher': True,
        'positions': ['投手'], 'primary_position': '投手',
    })
    assert resp.status_code == 201, resp.data
    return resp.get_json()['player']['id']


def _add_pitching(client, pid, *, date, ip, ha=0, bba=0, bf=0, er=0,
                  opponent='对手'):
    return client.post('/api/game_records', json={
        'player_id': pid, 'game_date': date, 'opponent': opponent,
        'is_pitching': True,
        'innings_pitched': ip, 'hits_allowed': ha, 'walks_allowed': bba,
        'batters_faced': bf, 'pitches': 90, 'strikes': 60,
        'earned_runs': er, 'runs_allowed': er, 'strikeouts': 0,
        'home_runs_allowed': 0,
    })


def test_profile_whip_only_counts_games_with_batters_faced(auth_client):
    """分子分母必须同源：没有 BF 的场次不参与 WHIP。

    场景：一场有 BF（2 安打 + 1 保送 / 10 个打席），一场没有 BF。
    正确 WHIP = (2+1)/10 = 0.30；
    若分子把无 BF 那场也算进去（+3 安打 +2 保送），会得到 0.6 —— 错。
    """
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=5.0,
                  ha=2, bba=1, bf=10)
    _add_pitching(auth_client, pid, date='2025-01-08', ip=4.0,
                  ha=3, bba=2, bf=0)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.batters_faced == 10
        assert p.whip == 0.3
        # 档案的总计仍然记录**全部**场次（不能为了 WHIP 把数据丢掉）
        assert p.hits_allowed_total == 5
        assert p.walks_allowed_total == 3


def test_profile_whip_is_reproducible_from_game_records(auth_client):
    """不变量：profile.whip 必须能从 game_records 反推出来。

    这条是「Stats 可解释」（规范 §17）的护栏 —— 档案里的每个派生值
    都必须能从源数据重新算出来。
    """
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=3.0,
                  ha=2, bba=1, bf=8)
    _add_pitching(auth_client, pid, date='2025-01-08', ip=2.1,
                  ha=1, bba=2, bf=6)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        records = GameRecord.query.filter_by(
            player_id=pid, is_pitching_record=True).all()
        qualified = [r for r in records if (r.batters_faced or 0) > 0]
        bf = sum(r.batters_faced for r in qualified)
        hits = sum(r.hits_allowed or 0 for r in qualified)
        walks = sum(r.walks_allowed or 0 for r in qualified)
        assert p.whip == whip(hits, walks, bf)


def test_player_dict_exposes_new_metrics(auth_client):
    """to_dict() 必须带上新指标（前端与 CSV 导出都读它）。"""
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=9.0,
                  ha=6, bba=3, bf=30)
    resp = auth_client.get('/api/players')
    assert resp.status_code == 200
    player = next(p for p in resp.get_json() if p['id'] == pid)

    for key in ('whip', 'era', 'strikeouts_per_9', 'walks_per_9',
                'pitcher_strikeout_walk_rate', 'batters_faced'):
        assert key in player, key
    assert player['whip'] == 0.3          # (6+3)/30
    assert player['strikeouts_per_9'] == 0.0


def test_player_dict_exposes_batting_metrics(auth_client):
    resp = auth_client.post('/api/players', json={
        'name': '测试打', 'jersey_number': '3', 'is_pitcher': False,
        'positions': ['游击手'], 'primary_position': '游击手',
    })
    assert resp.status_code == 201
    pid = resp.get_json()['player']['id']
    auth_client.post('/api/game_records', json={
        'player_id': pid, 'game_date': '2025-01-01', 'opponent': '对手',
        'is_pitching': False,
        'at_bats': 10, 'hits': 4, 'rbi': 2, 'walks': 1, 'strikeouts': 2,
        'doubles': 1, 'triples': 0, 'home_runs_game': 1,
        'stolen_bases_game': 2, 'caught_stealing': 1,
    })

    resp = auth_client.get('/api/players')
    player = next(p for p in resp.get_json() if p['id'] == pid)
    for key in ('isolated_power', 'babip', 'plate_appearances',
                'strikeout_rate', 'walk_rate', 'strikeout_walk_rate',
                'stolen_base_rate', 'caught_stealing_rate'):
        assert key in player, key
    assert player['plate_appearances'] == 11
    assert player['stolen_base_rate'] == 66.7
    assert player['caught_stealing_rate'] == 33.3


def test_stats_endpoints_carry_new_metrics(auth_client):
    """统计接口也要带上新指标（前端排行榜直接读它们）。"""
    pid = _create_pitcher(auth_client)
    # 自责分要 > 0，否则接口的 `era > 0` 过滤会把这个投手滤掉
    _add_pitching(auth_client, pid, date='2025-01-01', ip=9.0,
                  ha=6, bba=3, bf=30, er=3)

    resp = auth_client.get('/api/stats/pitching')
    assert resp.status_code == 200
    row = next(r for r in resp.get_json() if r['name'] == '测试投')
    assert row['whip'] == 0.3
    assert 'strikeouts_per_9' in row
    assert 'walks_per_9' in row


# ====== 4. 解析器：页脚污染 ======

def test_extract_named_counts_tolerates_trailing_junk():
    """尾部有杂物时，取开头的「名字 + 数字」，不要整条丢掉。

    修复前这一条会变成垃圾键 {「仇志豪4Scorekeeping...」: 1}，
    投手凭空少一个面对打席数（静默丢数）。
    """
    counts = _extract_named_counts_from('仇志豪 4 Scorekeeping. Stats. Live Game Updates.')
    assert counts.get('仇志豪') == 4
    assert '仇志豪4Scorekeeping.Stats.LiveGameUpdates.' not in counts


def test_extract_named_counts_still_handles_bare_names():
    """没有数字的条目仍然是「1 次」（如 WP: 邹庆）。"""
    counts = _extract_named_counts_from('邹庆')
    assert counts.get('邹庆') == 1


def test_split_tag_sections_strips_page_footer():
    """页脚不该出现在任何标签段的内容里。"""
    text = ('BF: 白云箫 9, 李昊宇 3, 韩登越 11, 仇志豪 4 '
            'Scorekeeping. Stats. Live Game Updates.')
    sections = _split_tag_sections(text)
    content = ', '.join(sections.get('BF', []))
    assert 'Scorekeeping' not in content
    counts = _extract_named_counts_from(content)
    assert counts.get('仇志豪') == 4
    assert counts.get('白云箫') == 9


def test_strip_page_footer_words_truncates_at_footer():
    words = [{'text': '仇志豪'}, {'text': '4'},
             {'text': 'Scorekeeping.'}, {'text': 'Stats.'}]
    assert [w['text'] for w in strip_page_footer_words(words)] == ['仇志豪', '4']


def test_is_footer_only_row():
    assert is_footer_only_row([{'text': 'Stats.'}, {'text': 'Live'},
                                {'text': 'Game'}, {'text': 'Updates.'}])
    assert not is_footer_only_row([{'text': '仇志豪'}, {'text': '4'}])


@pytest.mark.parametrize('relpath,expect_name,expect_bf', [
    ('data/2023/对外经济贸易大学_vs_北京工业大学_Apr_1_2023.pdf', '仇志豪', 4),
    ('data/2024/首都经济贸易大学_vs_北京工业大学_Oct_20_2024(2).pdf', '刘孝宇', 14),
    ('data/2025/中国地质大学_vs_北京工业大学_Oct_18_2025(1).pdf', '李昊宇', 8),
])
def test_real_pdf_last_bf_entry_is_not_swallowed(relpath, expect_name, expect_bf):
    """真实 PDF 回归：页脚曾经吞掉的最后一条必须解析出来。

    这些 PDF 的最后一个标签段的最后一条正好被页脚粘住，
    修复前这 5 名投手各少一个面对打席数（进而 WHIP 算不准）。
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(root, relpath.replace('/', os.sep))
    if not os.path.exists(path):
        pytest.skip('PDF 不存在: %s' % relpath)

    from pdf_parser_columns import parse_pdf
    result = parse_pdf(path)
    if 'error' in result:
        pytest.skip('PDF 解析失败: %s' % result['error'])

    pitchers = {p['name']: p for p in result.get('my_team_pitching', [])}
    assert expect_name in pitchers, '没解析出投手: %s' % list(pitchers)
    assert pitchers[expect_name].get('batters_faced') == expect_bf

# ====== 5. 回归护栏：legacy 迁移路径不能改写 WHIP ======
#
# R5 踩过的坑（2026-10-31）：
#   legacy 迁移路径（每次应用启动都会跑）曾用档案的**总计数**
#   hits_allowed_total / walks_allowed_total 除以 batters_faced 算 WHIP。
#   但 batters_faced 只累计「有面对打席数」的场次 —— 两者**不同源**，
#   结果把正确的 0.56 改成了 0.70（实测：吴鸿硕）。
#   而且这段代码每次启动都跑，一跑就把档案里正确的值覆盖掉。
#
#   WHIP 只能由聚合器写（它逐条累加，知道哪些场次有 BF）。

def test_legacy_migration_path_does_not_change_whip(auth_client):
    """跑一遍启动时的 legacy 迁移路径，WHIP 必须纹丝不动。"""
    from database import migrate_legacy_player_stats

    pid = _create_pitcher(auth_client)
    # 一场有 BF（2 安打 + 1 保送 / 10 个打席），一场没有 BF（还有 3 安打 + 2 保送）
    _add_pitching(auth_client, pid, date='2025-01-01', ip=5.0,
                  ha=2, bba=1, bf=10)
    _add_pitching(auth_client, pid, date='2025-01-08', ip=4.0,
                  ha=3, bba=2, bf=0)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        before = p.whip
        assert before == 0.3          # (2+1)/10 —— 只算有 BF 的那场

        migrate_legacy_player_stats()
        db.session.commit()

        p = db.session.get(Player, pid)
        assert p.whip == before, (
            'legacy 迁移路径把 WHIP 从 %s 改成了 %s —— '
            '档案的总计数与 BF 不同源，不能这样相除' % (before, p.whip))


def test_profile_whip_is_owned_by_the_aggregator(auth_client):
    """档案的 WHIP 必须能从 game_records 反推（聚合器是唯一写入者）。"""
    pid = _create_pitcher(auth_client)
    _add_pitching(auth_client, pid, date='2025-01-01', ip=5.0,
                  ha=2, bba=1, bf=10)
    _add_pitching(auth_client, pid, date='2025-01-08', ip=4.0,
                  ha=3, bba=2, bf=0)

    with auth_client.application.app_context():
        p = db.session.get(Player, pid)
        assert p.whip == 0.3
        # 档案的总计数仍然包含**全部**场次（不能为了 WHIP 把数据丢掉）
        assert p.hits_allowed_total == 5
        assert p.walks_allowed_total == 3
        assert p.batters_faced == 10
