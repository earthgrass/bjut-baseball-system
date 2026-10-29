"""
数据库对比报告 —— 迁移前后逐条比对（Phase R4，审计 #25 / 规范 §25）
==================================================================
为什么需要这个：
    规范 §25 要求任何 schema/data 迁移先在**生产库副本**上跑，
    并出「迁移报告」。这份报告必须是**可复算**的，不能靠人肉 diff。

做什么：
    给定两个 SQLite 文件（迁移前 / 迁移后），输出：
      · 每张表的行数变化
      · 比赛记录：逐条对齐（日期 + 对手 + 球员 + 记录类型），列出
        新增 / 消失 / 字段变化，并按字段汇总变化次数
      · 球员名单变化（有没有凭空多出人）
      · 完整性检查：integrity_check / foreign_key_check / 负值 / 业务不变量
      · 「档案 == SUM(game_records)」的漂移（迁移前 vs 迁移后）

用法：
    python scripts/compare_db.py instance/baseball_players.db instance/_after.db
"""
import os
import sys
import io
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if __name__ == '__main__':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

from metrics import innings_to_true  # noqa: E402  (需要项目根在 sys.path)

TABLES = ['players', 'game_records', 'fielder_profiles', 'pitcher_profiles',
          'users', 'positions', 'player_positions']

BAT_FIELDS = [
    ('at_bats', 'at_bats'), ('runs', 'runs'), ('hits', 'hits'), ('rbi', 'rbi'),
    ('walks', 'walks'), ('strikeouts', 'strikeouts'), ('doubles', 'doubles'),
    ('triples', 'triples'), ('home_runs_batting', 'home_runs_batting'),
    ('total_bases', 'total_bases'), ('hit_by_pitch', 'hit_by_pitch'),
    ('stolen_bases', 'stolen_bases'), ('caught_stealing', 'caught_stealing'),
    ('sacrifice_flys', 'sacrifice_flys'), ('sacrifice_hits', 'sacrifice_hits'),
    ('errors_fielding', 'errors_fielding'),
]
PIT_FIELDS = [
    ('innings_pitched', 'innings_pitched'), ('hits_allowed', 'hits_allowed'),
    ('runs_allowed', 'runs_allowed'), ('earned_runs', 'earned_runs'),
    ('walks_allowed', 'walks_allowed'), ('strikeouts_pitched', 'strikeouts_pitched'),
    ('home_runs_allowed', 'home_runs_allowed'), ('pitches', 'pitches'),
    ('strikes', 'strikes'), ('batters_faced', 'batters_faced'),
    ('wild_pitches', 'wild_pitches'), ('hit_by_pitch_allowed', 'hit_by_pitch_allowed'),
]


def _connect(path):
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def _counts(con):
    out = {}
    for table in TABLES:
        try:
            out[table] = con.execute(f'select count(*) from "{table}"').fetchone()[0]
        except sqlite3.Error:
            out[table] = None
    return out


def _records(con):
    rows = con.execute(
        'select id, player_id, game_date, opponent, is_pitching_record, '
        + ', '.join(f'{f}' for f, _ in BAT_FIELDS + PIT_FIELDS)
        + ' from game_records').fetchall()
    out = {}
    for r in rows:
        key = (r['game_date'], r['opponent'], r['player_id'],
               'pitching' if r['is_pitching_record'] else 'batting')
        out.setdefault(key, []).append(dict(r))
    return out


def _players(con):
    return {r['id']: r['name'] for r in con.execute('select id, name from players')}


def _integrity(con):
    report = {
        'integrity': con.execute('PRAGMA integrity_check').fetchone()[0],
        'fk_violations': len(con.execute('PRAGMA foreign_key_check').fetchall()),
    }
    negatives = con.execute(
        'select count(*) from game_records where '
        'coalesce(at_bats,0) < 0 or coalesce(hits,0) < 0 or '
        'coalesce(innings_pitched,0) < 0 or coalesce(earned_runs,0) < 0').fetchone()[0]
    report['negative_values'] = negatives
    bad_ab = con.execute(
        'select count(*) from game_records where is_pitching_record = 0 and '
        'coalesce(hits,0) > coalesce(at_bats,0)').fetchone()[0]
    report['hits_gt_at_bats'] = bad_ab
    bad_tb = con.execute(
        'select count(*) from game_records where is_pitching_record = 0 and '
        'coalesce(hits,0) < coalesce(doubles,0) + coalesce(triples,0) '
        '+ coalesce(home_runs_batting,0)').fetchone()[0]
    report['hits_lt_extra_bases'] = bad_tb
    return report


def _drift(con):
    """档案 vs SUM(game_records) 的漂移条数（含局数按真实局数换算）。"""
    players = con.execute('select id from players').fetchall()
    drift = 0
    details = []
    for p in players:
        pid = p['id']
        fp = con.execute('select * from fielder_profiles where player_id=?',
                          (pid,)).fetchone()
        if fp:
            for column, agg in (('at_bats_total', 'at_bats'), ('hits_total', 'hits'),
                                ('rbi_total', 'rbi'), ('walks_total', 'walks'),
                                ('doubles', 'doubles'), ('triples', 'triples'),
                                ('home_runs_batting', 'home_runs_batting'),
                                ('stolen_bases', 'stolen_bases'),
                                ('hit_by_pitch', 'hit_by_pitch'),
                                ('sacrifice_flys', 'sacrifice_flys'),
                                ('errors_fielding', 'errors_fielding')):
                expected = con.execute(
                    'select coalesce(sum(%s),0) from game_records where '
                    'player_id=? and is_pitching_record = 0' % agg, (pid,)).fetchone()[0]
                actual = fp[column] or 0
                if actual != expected:
                    drift += 1
                    details.append((pid, column, actual, expected))
        pp = con.execute('select * from pitcher_profiles where player_id=?',
                          (pid,)).fetchone()
        if pp:
            rows = con.execute(
                'select innings_pitched from game_records where player_id=? '
                'and is_pitching_record = 1', (pid,)).fetchall()
            true_ip = sum(innings_to_true(r[0]) for r in rows)
            if abs((pp['innings_pitched_total'] or 0.0) - true_ip) > 1e-6:
                drift += 1
                details.append((pid, 'innings_pitched_total',
                                pp['innings_pitched_total'], round(true_ip, 4)))
    return drift, details


def compare(before_path, after_path):
    b_con, a_con = _connect(before_path), _connect(after_path)
    print('=' * 70)
    print('迁移报告：%s  →  %s' % (os.path.basename(before_path),
                                   os.path.basename(after_path)))
    print('=' * 70)

    b_counts, a_counts = _counts(b_con), _counts(a_con)
    print('\n【1】表行数')
    for table in TABLES:
        b, a = b_counts.get(table), a_counts.get(table)
        mark = '' if b == a else ('   ← 变了 (%+d)' % (a - b) if b is not None and a is not None else '')
        print(f'    {table:20} {b} → {a}{mark}')

    b_players, a_players = _players(b_con), _players(a_con)
    added = set(a_players) - set(b_players)
    removed = set(b_players) - set(a_players)
    renamed = [(b_players[i], a_players[i]) for i in set(b_players) & set(a_players)
               if b_players[i] != a_players[i]]
    print('\n【2】球员名单')
    print(f'    新增球员: {len(added)}  删除球员: {len(removed)}  改名: {len(renamed)}')
    for i in sorted(added):
        print(f'      + #{i} {a_players[i]}')
    for i in sorted(removed):
        print(f'      - #{i} {b_players[i]}')
    for old, new in renamed:
        print(f'      ~ {old} → {new}')

    b_recs, a_recs = _records(b_con), _records(a_con)
    added_recs = sorted(set(a_recs) - set(b_recs))
    removed_recs = sorted(set(b_recs) - set(a_recs))
    changed = []
    field_counter = defaultdict(int)
    for key in set(b_recs) & set(a_recs):
        b_row, a_row = b_recs[key][0], a_recs[key][0]
        diffs = []
        fields = BAT_FIELDS if key[3] == 'batting' else PIT_FIELDS
        for col, _ in fields:
            bv, av = b_row.get(col), a_row.get(col)
            if bv is None and av is None:
                continue
            if isinstance(bv, float) or isinstance(av, float):
                if abs(float(bv or 0) - float(av or 0)) > 1e-9:
                    diffs.append((col, bv, av))
            elif (bv or 0) != (av or 0):
                diffs.append((col, bv, av))
        if diffs:
            changed.append((key, diffs))
            for col, _bv, _av in diffs:
                field_counter[col] += 1

    print('\n【3】比赛记录')
    print(f'    迁移前 {len(b_recs)} 条（去重后） / 迁移后 {len(a_recs)} 条')
    print(f'    新增 {len(added_recs)} 条 / 消失 {len(removed_recs)} 条 / '
          f'有字段变化 {len(changed)} 条')
    if removed_recs:
        print('    ⚠ 消失的记录（必须逐条解释）：')
        for key in removed_recs:
            print(f'      - {key[0]} {key[1]} player_id={key[2]} {key[3]}')
    print('\n    字段变化汇总：')
    for col, n in sorted(field_counter.items(), key=lambda kv: -kv[1]):
        print(f'      {col:24} {n:4} 处')

    print('\n【4】完整性（迁移前 → 迁移后）')
    b_int, a_int = _integrity(b_con), _integrity(a_con)
    for key in b_int:
        flag = '' if b_int[key] == a_int[key] else '   ← 变了'
        print(f'    {key:22} {b_int[key]} → {a_int[key]}{flag}')

    print('\n【5】不变量：档案 == SUM(game_records)')
    b_drift, b_details = _drift(b_con)
    a_drift, a_details = _drift(a_con)
    print(f'    漂移字段数: {b_drift} → {a_drift}')
    if a_details:
        print('    ⚠ 迁移后仍有漂移：')
        for pid, col, actual, expected in a_details[:20]:
            print(f'      player_id={pid} {col}: {actual} ≠ {expected}')

    b_con.close()
    a_con.close()
    return {
        'counts_before': b_counts, 'counts_after': a_counts,
        'players_added': len(added), 'players_removed': len(removed),
        'records_added': len(added_recs), 'records_removed': len(removed_recs),
        'records_changed': len(changed), 'field_changes': dict(field_counter),
        'integrity_before': b_int, 'integrity_after': a_int,
        'drift_before': b_drift, 'drift_after': a_drift,
    }


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
