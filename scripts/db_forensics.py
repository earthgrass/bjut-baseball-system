"""
Database forensics script — Phase E0

**只读**分析 instance/baseball_players.db。
- 输出每个表的 row count / PK / FK / unique / index
- 检测 (player_id, game_date, opponent, is_pitching_record) 重复
- 不 DELETE / 不 UPDATE / 不 ALTER
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path('instance/baseball_players.db')

if not DB_PATH.exists():
    print(f'DB not found: {DB_PATH}')
    sys.exit(1)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print('=' * 70)
    print('DATABASE FORENSICS — READ ONLY')
    print('=' * 70)

    # 1. 表清单
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f'\n## 1. Tables ({len(tables)})')
    for t in tables:
        tbl = t['name']
        cnt = cur.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
        print(f'  {tbl}: {cnt} rows')

    # 2. Schema 详情
    print(f'\n## 2. Schema details')
    for t in tables:
        tbl = t['name']
        print(f'\n  [{tbl}]')
        cols = cur.execute(f'PRAGMA table_info("{tbl}")').fetchall()
        for c in cols:
            print(f'    {c["name"]:30s} {c["type"]:15s} pk={c["pk"]} null={c["notnull"]}')
        # 索引
        idx = cur.execute(f'PRAGMA index_list("{tbl}")').fetchall()
        for i in idx:
            print(f'    [INDEX] {i["name"]}')

    # 3. 主表 row count
    print(f'\n## 3. Main entities')
    for tbl in ['players', 'positions', 'player_positions', 'game_records',
                'fielder_profiles', 'pitcher_profiles', 'users']:
        try:
            cnt = cur.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
            print(f'  {tbl}: {cnt}')
        except Exception as e:
            print(f'  {tbl}: ERROR {e}')

    # 4. Duplicate candidates in game_records
    print(f'\n## 4. Duplicate candidates')
    print('  Key: (player_id, game_date, opponent, is_pitching_record)')
    dups = cur.execute('''
        SELECT player_id, game_date, opponent, is_pitching_record, COUNT(*) as n
        FROM game_records
        GROUP BY player_id, game_date, opponent, is_pitching_record
        HAVING COUNT(*) > 1
        ORDER BY n DESC, game_date DESC
        LIMIT 50
    ''').fetchall()
    print(f'  Found {len(dups)} candidate groups')
    for d in dups[:20]:
        player = cur.execute('SELECT name FROM players WHERE id=?', (d['player_id'],)).fetchone()
        player_name = player['name'] if player else '<deleted>'
        print(f'    {player_name:10s} | {d["game_date"]} | {d["opponent"] or "":15s} | '
              f'pitching={d["is_pitching_record"]} | x{d["n"]}')

    # 5. Per-player duplicate detail
    print(f'\n## 5. Per-player duplicate stats')
    player_dup_count = cur.execute('''
        SELECT player_id, COUNT(*) as dup_groups
        FROM (
            SELECT player_id
            FROM game_records
            GROUP BY player_id, game_date, opponent, is_pitching_record
            HAVING COUNT(*) > 1
        )
        GROUP BY player_id
        ORDER BY dup_groups DESC
    ''').fetchall()
    print(f'  Players with duplicates: {len(player_dup_count)}')
    for p in player_dup_count[:10]:
        player = cur.execute('SELECT name FROM players WHERE id=?', (p['player_id'],)).fetchone()
        player_name = player['name'] if player else '<deleted>'
        total_recs = cur.execute('SELECT COUNT(*) FROM game_records WHERE player_id=?',
                                 (p['player_id'],)).fetchone()[0]
        print(f'    {player_name} (id={p["player_id"]}): '
              f'{p["dup_groups"]} dup groups / {total_recs} total records')

    # 6. Date range
    print(f'\n## 6. Game date range')
    dr = cur.execute('SELECT MIN(game_date), MAX(game_date) FROM game_records').fetchone()
    print(f'  Earliest: {dr[0]}, Latest: {dr[1]}')

    # 7. Opponent diversity
    print(f'\n## 7. Opponents')
    opps = cur.execute('''
        SELECT opponent, COUNT(*) as n
        FROM game_records
        WHERE opponent IS NOT NULL
        GROUP BY opponent
        ORDER BY n DESC
    ''').fetchall()
    print(f'  {len(opps)} unique opponents:')
    for o in opps[:15]:
        print(f'    {o["opponent"] or "<empty>":20s}: {o["n"]} records')

    # 8. AMBIGUOUS detection: same player same day but DIFFERENT opponent
    print(f'\n## 8. AMBIGUOUS: same player + same day but different opponent')
    ambig = cur.execute('''
        SELECT player_id, game_date, COUNT(DISTINCT opponent) as opponents
        FROM game_records
        GROUP BY player_id, game_date
        HAVING COUNT(DISTINCT opponent) > 1
    ''').fetchall()
    print(f'  Found {len(ambig)} ambiguous groups')
    for a in ambig[:10]:
        player = cur.execute('SELECT name FROM players WHERE id=?', (a['player_id'],)).fetchone()
        player_name = player['name'] if player else '<deleted>'
        print(f'    {player_name} | {a["game_date"]} | {a["opponents"]} different opponents')

    # 9. Same player same day same opponent but DIFFERENT pitching type
    print(f'\n## 9. AMBIGUOUS: same player+day+opponent but different pitching type')
    mix = cur.execute('''
        SELECT player_id, game_date, opponent, COUNT(DISTINCT is_pitching_record) as types
        FROM game_records
        GROUP BY player_id, game_date, opponent
        HAVING COUNT(DISTINCT is_pitching_record) > 1
    ''').fetchall()
    print(f'  Found {len(mix)} groups with both batting and pitching records for same game')
    for m in mix[:10]:
        player = cur.execute('SELECT name FROM players WHERE id=?', (m['player_id'],)).fetchone()
        player_name = player['name'] if player else '<deleted>'
        print(f'    {player_name} | {m["game_date"]} | vs {m["opponent"]}')

    # 10. Stats consistency check (invariant)
    print(f'\n## 10. Stats consistency check (invariant)')
    inconsistencies = 0
    players = cur.execute('SELECT id, name FROM players').fetchall()
    for p in players:
        pid = p['id']
        # Sum from game_records
        bat = cur.execute('''
            SELECT COALESCE(SUM(at_bats), 0) as ab, COALESCE(SUM(hits), 0) as h
            FROM game_records WHERE player_id=? AND is_pitching_record=0
        ''', (pid,)).fetchone()
        fp = cur.execute('SELECT at_bats_total, hits_total FROM fielder_profiles WHERE player_id=?',
                         (pid,)).fetchone()
        if fp and (fp['at_bats_total'] != bat['ab'] or fp['hits_total'] != bat['h']):
            inconsistencies += 1
            if inconsistencies <= 10:
                print(f'    INCONSISTENT: {p["name"]} (id={pid}): '
                      f'profile=(AB={fp["at_bats_total"]},H={fp["hits_total"]}) vs '
                      f'game_records=(AB={bat["ab"]},H={bat["h"]})')
    print(f'  Total inconsistencies: {inconsistencies} / {len(players)} players')

    conn.close()
    print('\n' + '=' * 70)
    print('FORENSICS COMPLETE — no writes performed')
    print('=' * 70)


if __name__ == '__main__':
    main()