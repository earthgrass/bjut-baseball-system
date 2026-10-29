"""
Database forensics — Phase E0.5 (revised)

读取 instance/baseball_players.backup_20260405_165141.db（最近可用备份，含完整数据）。
**绝不修改任何 DB 文件。**

用法：python scripts/db_forensics.py
"""
import sqlite3
from pathlib import Path

# 优先用 backup（数据完整）；如果 real DB 有表就用 real DB
DB_PATHS = [
    Path('instance/baseball_players.backup_20260405_165141.db'),
    Path('instance/baseball_players.backup_20260405_125745.db'),
    Path('instance/baseball_players.db'),
]

# 选择第一个有数据的
def find_db():
    for p in DB_PATHS:
        if p.exists():
            try:
                conn = sqlite3.connect(str(p))
                cnt = conn.execute('SELECT COUNT(*) FROM sqlite_master WHERE type="table"').fetchone()[0]
                conn.close()
                if cnt > 0:
                    return p
            except Exception:
                continue
    return None


def main():
    db_path = find_db()
    if not db_path:
        print('No DB with tables found.')
        return

    print(f'Using DB: {db_path} (READ-ONLY)')
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ===== A. player 28 forensic =====
    print()
    print('=' * 70)
    print('A. player 28 on 2024-11-16 vs 北京交通大学 — full forensic')
    print('=' * 70)

    rows = cur.execute("""
        SELECT * FROM game_records
        WHERE player_id = 28 AND game_date = '2024-11-16'
          AND opponent = '北京交通大学' AND is_pitching_record = 0
        ORDER BY id
    """).fetchall()

    print(f'\n[A.1] Player 28 batting records (id={rows[0]["id"] if rows else "?"})')
    print(f'  found {len(rows)} records')
    for r in rows:
        nonzero = {k: r[k] for k in r.keys() if r[k] not in (None, 0, False, '') and k != 'id'}
        print(f'  id={r["id"]}: nonzero fields = {nonzero if nonzero else "(all zero)"}')

    print('\n[A.2] All records on 2024-11-16 vs 北京交通大学 (any team)')
    recs = cur.execute("""
        SELECT gr.*, p.name FROM game_records gr
        JOIN players p ON p.id = gr.player_id
        WHERE gr.game_date = '2024-11-16' AND gr.opponent = '北京交通大学'
        ORDER BY gr.player_id, gr.is_pitching_record, gr.id
    """).fetchall()
    print(f'  total: {len(recs)} records')
    for r in recs:
        label = 'BAT' if not r['is_pitching_record'] else 'PIT'
        if r['is_pitching_record']:
            line = f'  [{label}] pid={r["player_id"]:3d} {r["name"]:8s} rec={r["id"]:3d}  IP={r["innings_pitched"]}  HA={r["hits_allowed"]}  ER={r["earned_runs"]}'
        else:
            line = f'  [{label}] pid={r["player_id"]:3d} {r["name"]:8s} rec={r["id"]:3d}  AB={r["at_bats"]}  H={r["hits"]}  RBI={r["rbi"]}'
        print(line)

    # Are the two player 28 records field-for-field identical?
    print('\n[A.3] Are the two player 28 records field-for-field identical?')
    if len(rows) == 2:
        cols = [k for k in rows[0].keys() if k != 'id']
        diff = []
        for col in cols:
            if rows[0][col] != rows[1][col]:
                diff.append(col)
        if diff:
            print(f'  DIFFER in: {diff}')
            print(f'    rec 68: {[rows[0][c] for c in diff]}')
            print(f'    rec 69: {[rows[1][c] for c in diff]}')
        else:
            print('  IDENTICAL (all fields match)')

    print('\n[A.4] Sequential ids / surrounding context')
    if len(rows) == 2:
        ids = [rows[0]['id'], rows[1]['id']]
        print(f'  ids: {ids}, gap: {ids[1] - ids[0]}')
        surrounding = cur.execute("""
            SELECT id, player_id, game_date, opponent, is_pitching_record
            FROM game_records
            WHERE id BETWEEN ? AND ?
            ORDER BY id
        """, (ids[0] - 3, ids[1] + 3)).fetchall()
        for r in surrounding:
            mark = ' ←' if r['id'] in ids else ''
            label = 'BAT' if not r['is_pitching_record'] else 'PIT'
            print(f'    id={r["id"]:3d} pid={r["player_id"]:3d} {r["game_date"]} vs {r["opponent"]:10s} {label}{mark}')

    # ===== A.5 PDF source =====
    print('\n[A.5] PDF source candidates for 2024-11-16')
    data_dir = Path('data/2024')
    if data_dir.exists():
        for f in sorted(data_dir.iterdir()):
            if '11' in f.name and ('16' in f.name or '_16_' in f.name or '_16.' in f.name):
                size = f.stat().st_size
                print(f'  data/2024/{f.name}  ({size:,} bytes)  ← candidate')

    # Try to parse the 2024-11-16 PDF to see what box score says about player 28
    print('\n[A.5.1] Trying to find 2024-11-16 北京工业大学 vs 北京交通大学 PDF')
    candidates = []
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.suffix.lower() == '.pdf' and '16' in f.name:
                candidates.append(f)
    for c in candidates:
        print(f'  trying: data/2024/{c.name}')
        try:
            import pdfplumber
            with pdfplumber.open(c) as pdf:
                text = ''
                for page in pdf.pages:
                    text += (page.extract_text() or '') + '\n'
                # look for player 28 (欧阳X) — name unknown, look for 欧阳
                if '欧阳' in text or '欧' in text:
                    # extract batting section
                    print(f'    [HIT] found 欧 in {c.name}')
                    # print 30 lines around 欧
                    for i, line in enumerate(text.split('\n')):
                        if '欧' in line:
                            start = max(0, i-2)
                            end = min(len(text.split('\n')), i+3)
                            for j in range(start, end):
                                print(f'      L{j}: {text.split(chr(10))[j]}')
        except Exception as e:
            print(f'    error: {e}')

    # ===== B. Classification =====
    print('\n' + '=' * 70)
    print('B. CLASSIFICATION')
    print('=' * 70)

    if len(rows) == 2:
        # Check identicality
        cols = [k for k in rows[0].keys() if k != 'id']
        identical = all(rows[0][c] == rows[1][c] for c in cols)
        # Check non-zero stats
        non_zero_batting = any([rows[0]['at_bats'], rows[0]['hits'], rows[0]['rbi']])
        # Check players in same game
        game_players = cur.execute("""
            SELECT DISTINCT player_id FROM game_records
            WHERE game_date = '2024-11-16' AND opponent = '北京交通大学'
              AND is_pitching_record = 0 AND player_id != 28 AND at_bats > 0
        """).fetchall()
        other_batters_have_real_stats = len(game_players) > 0

        print(f'  identical fields: {identical}')
        print(f'  player 28 batting non-zero: {non_zero_batting}')
        print(f'  other batters on same day have non-zero AB: {other_batters_have_real_stats} ({len(game_players)} players)')
        if identical and not non_zero_batting and other_batters_have_real_stats:
            print()
            print('  >>> CLASSIFICATION: LIKELY_DUPLICATE')
            print('      Two field-identical all-zero rows where other batters in same')
            print('      game have non-zero stats. Strong evidence of double-import.')
            print()
            print('      Per Phase E0.5 directive: NO DELETE in this phase.')
            print('      Migration script for Phase C will:')
            print('      - Keep both records (zero data loss)')
            print('      - Note them as AMBIGUOUS in migration report')
            print('      - Allow Game entity to have game_number=1 and game_number=2')
            print('        so both records can be preserved separately')
        elif not identical:
            print('  >>> Classification: records differ — likely LIKELY_DOUBLEHEADER or LIKELY_DUPLICATE')
        else:
            print('  >>> Classification: AMBIGUOUS (insufficient evidence)')

    # ===== C. Impact on derived stats =====
    print('\n' + '=' * 70)
    print('C. Impact on derived stats')
    print('=' * 70)
    fp = cur.execute("SELECT * FROM fielder_profiles WHERE player_id = 28").fetchone()
    if fp:
        print(f'  player 28 fielder_profile: AB={fp["at_bats_total"]}, H={fp["hits_total"]}')
        print('  Both records contribute at_bats=0, hits=0 → stats UNCHANGED whether 1 or 2 records.')
        print('  → Cleanup or not, derived stats are equivalent.')

    # ===== D. Invariant check =====
    print('\n' + '=' * 70)
    print('D. Invariant check (profile sums = GameRecord sums)')
    print('=' * 70)
    inconsistencies = 0
    players = cur.execute('SELECT id, name FROM players').fetchall()
    for p in players:
        pid = p['id']
        bat = cur.execute("""
            SELECT COALESCE(SUM(at_bats), 0) as ab, COALESCE(SUM(hits), 0) as h
            FROM game_records WHERE player_id = ? AND is_pitching_record = 0
        """, (pid,)).fetchone()
        fp = cur.execute(
            'SELECT at_bats_total, hits_total FROM fielder_profiles WHERE player_id = ?',
            (pid,)).fetchone()
        if fp and (fp['at_bats_total'] != bat['ab'] or fp['hits_total'] != bat['h']):
            inconsistencies += 1
            if inconsistencies <= 10:
                print(f'  INCONSISTENT: {p["name"]} (id={pid}): '
                      f'profile=(AB={fp["at_bats_total"]},H={fp["hits_total"]}) vs '
                      f'game_records=(AB={bat["ab"]},H={bat["h"]})')
    print(f'  Total inconsistencies: {inconsistencies} / {len(players)} players')

    conn.close()
    print('\n' + '=' * 70)
    print('FORENSICS COMPLETE — read-only')
    print('=' * 70)


if __name__ == '__main__':
    main()