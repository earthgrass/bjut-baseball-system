"""
R6-2026 迁移 —— 2026 赛季数据导入（副本验证 + 迁移报告）
=========================================================
背景：
    2026 赛季的 5 份记分卡 PDF 已放进 `data/2026/`，但还没进库。
    本脚本在**生产库副本**上做增量导入并出报告（规范 §25：
    任何迁移先在副本上跑，row loss 必须为 0，报告要可复算）。

做法：
    1. 复制生产库 → instance/_r6_2026.db
    2. 在副本上跑 `import_pdfs.py --dir 2026 --allow-new-players`
       （**不带 --replace** —— 2026 是新日期，历史数据一根手指都不碰）
    3. 逐条比对：历史 240 条记录是否**逐字段不变**、球员名单变化、新记录明细
    4. 打印迁移报告 + 完整性检查

⚠️ 本脚本**不会**写生产库。要落库请显式加 --apply（会自动备份）。

用法：
    python scripts/migrate_r6_2026.py          # 只在副本上跑 + 出报告
    python scripts/migrate_r6_2026.py --apply   # 验证通过后写生产库（自动备份）
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INSTANCE = os.path.join(ROOT, 'instance')
PROD_DB = os.path.join(INSTANCE, 'baseball_players.db')
COPY_DB = os.path.join(INSTANCE, '_r6_2026.db')

sys.path.insert(0, ROOT)

# 控制台编码：Windows 默认 GBK，遇到子进程输出里的 '✓' 会 UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _log(msg=''):
    print(msg, flush=True)


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _rows(path, sql, params=()):
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(path):
    out = {}
    for table in ('players', 'game_records', 'fielder_profiles', 'pitcher_profiles'):
        out[table] = _rows(path, 'SELECT COUNT(*) FROM %s' % table)[0][0]
    return out


def _by_year(path):
    return dict(_rows(path, """
        SELECT strftime('%Y', game_date), COUNT(*) FROM game_records
        GROUP BY 1 ORDER BY 1"""))


def _historical_records(path):
    """历史记录（2026 之前）的完整指纹 —— 按 (日期, 对手, 球员, 记录类型) 排序。

    用来证明「不带 --replace 的增量导入没有碰历史数据」。
    """
    return _rows(path, """
        SELECT g.game_date, g.opponent, p.name, g.is_pitching_record,
               g.at_bats, g.hits, g.runs, g.rbi, g.walks, g.strikeouts,
               g.doubles, g.triples, g.home_runs_batting, g.total_bases,
               g.hit_by_pitch, g.stolen_bases, g.caught_stealing,
               g.sacrifice_flys, g.sacrifice_hits,
               g.innings_pitched, g.hits_allowed, g.runs_allowed, g.earned_runs,
               g.walks_allowed, g.strikeouts_pitched, g.home_runs_allowed,
               g.pitches, g.strikes, g.hit_by_pitch_allowed, g.batters_faced,
               g.wild_pitches, g.errors_fielding, g.passed_balls,
               g.win, g.loss, g.save
        FROM game_records g JOIN players p ON p.id = g.player_id
        WHERE g.game_date < '2026-01-01'
        ORDER BY g.game_date, g.opponent, p.name, g.is_pitching_record""")


def _player_names(path):
    return {r[0] for r in _rows(path, 'SELECT name FROM players')}


def _integrity(path):
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        c = con.cursor()
        integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        fk = len(c.execute('PRAGMA foreign_key_check').fetchall())
        return integrity, fk
    finally:
        con.close()


def _run_import(db_path):
    """在指定库上做 2026 增量导入。

    必须用**子进程 + 环境变量**：Flask-SQLAlchemy 在 init_app() 里就
    eager 创建 engine，之后再改 URI 不生效（见 app.py 注释与 HANDOFF）。
    """
    env = dict(os.environ)
    env['DATABASE_FILE'] = db_path
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, 'import_pdfs.py', '--dir', '2026', '--allow-new-players'],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace')


def _run_rebuild(db_path):
    """全量重建档案（档案 = SUM(game_records)）。

    为什么必须做：导入只重建「本批次涉及的球员」的档案，
    其他人（比如没上场的吴鸿硕）的档案仍是旧值 ——
    而旧值里可能带着旧公式的结果。重建是唯一的归一手段。
    """
    env = dict(os.environ)
    env['DATABASE_FILE'] = db_path
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, 'scripts/rebuild_stats.py', '--apply', '--yes'],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace')


def _report(before, after):
    _log('')
    _log('=' * 72)
    _log('R6-2026 迁移报告（副本）')
    _log('=' * 72)

    _log('\n【行数对照】')
    cb, ca = _counts(before), _counts(after)
    for table in cb:
        flag = '' if cb[table] == ca[table] else '   ← 变化 %+d' % (ca[table] - cb[table])
        _log('  %-18s %6d → %6d%s' % (table, cb[table], ca[table], flag))

    _log('\n【按赛季】')
    yb, ya = _by_year(before), _by_year(after)
    for y in sorted(set(yb) | set(ya)):
        _log('  %s  %4d → %4d' % (y, yb.get(y, 0), ya.get(y, 0)))

    _log('\n【历史数据是否被动过】(2026-01-01 之前的全部记录，逐字段比对)')
    hb, ha = _historical_records(before), _historical_records(after)
    if hb == ha:
        _log('  ✓ %d 条历史记录**逐字段完全一致** —— 增量导入没有碰历史' % len(hb))
    else:
        _log('  ✗ 历史数据有差异！')
        diff = 0
        for a, b in zip(hb, ha, strict=False):
            if a != b:
                diff += 1
                if diff <= 5:
                    _log('    差异: %s' % (a,))
                    _log('       →  %s' % (b,))
        _log('    共 %d 处差异（长度 %d → %d）' % (diff, len(hb), len(ha)))

    _log('\n【球员名单】')
    pb, pa = _player_names(before), _player_names(after)
    new = sorted(pa - pb)
    gone = sorted(pb - pa)
    _log('  新增 %d 人: %s' % (len(new), new or '无'))
    _log('  移除 %d 人: %s' % (len(gone), gone or '无'))

    _log('\n【新导入的比赛】')
    for date, opp, n, p in _rows(after, """
            SELECT g.game_date, g.opponent,
                   SUM(CASE WHEN g.is_pitching_record=0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN g.is_pitching_record=1 THEN 1 ELSE 0 END)
            FROM game_records g WHERE g.game_date >= '2026-01-01'
            GROUP BY g.game_date, g.opponent ORDER BY g.game_date"""):
        _log('  %s vs %-16s 打击 %2d · 投球 %d' % (date, opp, n or 0, p or 0))

    _log('\n【面对打席数(BF)覆盖】')
    for label, path in (('迁移前', before), ('迁移后', after)):
        tot = _rows(path, """SELECT COUNT(*) FROM game_records
                             WHERE is_pitching_record=1""")[0][0]
        withbf = _rows(path, """SELECT COUNT(*) FROM game_records
                                WHERE is_pitching_record=1
                                  AND COALESCE(batters_faced,0) > 0""")[0][0]
        _log('  %s: %d/%d 条投球记录有 BF（缺 %d）' % (label, withbf, tot, tot - withbf))

    _log('\n【档案 WHIP：迁移前 → 迁移后】')
    wb = {r[0]: r[1] for r in _rows(before, """
            SELECT p.name, pp.whip FROM pitcher_profiles pp
            JOIN players p ON p.id = pp.player_id""")}
    for name, w, bf, ip in _rows(after, """
            SELECT p.name, pp.whip, pp.batters_faced, pp.innings_pitched_total
            FROM pitcher_profiles pp JOIN players p ON p.id = pp.player_id
            WHERE pp.innings_pitched_total > 0 OR pp.whip > 0
            ORDER BY p.name"""):
        old = wb.get(name)
        mark = ''
        if old is not None and abs((old or 0) - (w or 0)) > 0.005:
            mark = '   <- 变化'
        _log('  %-8s %5.2f -> %5.2f   BF %4d   IP %6.2f%s'
             % (name, old or 0.0, w or 0, bf or 0, ip or 0, mark))


def main():
    apply = '--apply' in sys.argv

    if not os.path.exists(PROD_DB):
        _log('!! 生产库不存在: %s' % PROD_DB)
        return 1

    _log('生产库: %s' % PROD_DB)
    _log('生产库 SHA256（迁移前）: %s' % _sha256(PROD_DB))

    if os.path.exists(COPY_DB):
        os.remove(COPY_DB)
    shutil.copy2(PROD_DB, COPY_DB)
    _log('副本已建: %s' % COPY_DB)

    _log('\n--- 在副本上增量导入 2026 ---')
    proc = _run_import(COPY_DB)
    out = proc.stdout or ''
    for ln in [x for x in out.splitlines() if x.strip()][-16:]:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 副本导入失败（returncode=%s）' % proc.returncode)
        _log((proc.stderr or '')[-2000:])
        _log('生产库未被改动 ✓')
        return 1

    _log('\n--- 在副本上全量重建档案 ---')
    proc = _run_rebuild(COPY_DB)
    for ln in [x for x in (proc.stdout or '').splitlines() if x.strip()][-6:]:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 副本重建失败（returncode=%s）' % proc.returncode)
        _log((proc.stderr or '')[-2000:])
        _log('生产库未被改动 ✓')
        return 1

    _report(PROD_DB, COPY_DB)

    integrity, fk = _integrity(COPY_DB)
    _log('\n【完整性】integrity_check=%s  foreign_key_check=%d 条' % (integrity, fk))
    _log('【指纹】迁移前 %s' % _sha256(PROD_DB))
    _log('        副本后 %s' % _sha256(COPY_DB))

    if not apply:
        _log('\n这是**副本验证**。生产库未被改动 ✓')
        _log('确认报告无误后加 --apply 执行正式迁移。')
        return 0

    if integrity != 'ok' or fk:
        _log('\n!! 副本完整性检查未通过，拒绝写生产库')
        return 1

    backup = os.path.join(
        INSTANCE, 'baseball_players.pre_r6_%s.db' % time.strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(PROD_DB, backup)
    _log('\n生产库已备份: %s' % backup)

    _log('\n--- 写生产库 ---')
    proc = _run_import(PROD_DB)
    for ln in [x for x in (proc.stdout or '').splitlines() if x.strip()][-16:]:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 生产库导入失败 —— 回滚：把备份复制回去')
        _log('  cp "%s" "%s"' % (backup, PROD_DB))
        _log((proc.stderr or '')[-2000:])
        return 1

    _log('\n--- 生产库全量重建档案 ---')
    proc = _run_rebuild(PROD_DB)
    for ln in [x for x in (proc.stdout or '').splitlines() if x.strip()][-6:]:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 生产库重建失败 —— 回滚：把备份复制回去')
        _log('  cp ' + chr(34) + backup + chr(34) + ' ' + chr(34) + PROD_DB + chr(34))
        return 1

    integrity2, fk2 = _integrity(PROD_DB)
    _log('\n迁移后 integrity_check=%s  foreign_key_check=%d' % (integrity2, fk2))
    _log('生产库 SHA256（迁移后）: %s' % _sha256(PROD_DB))
    _log('备份文件: %s' % backup)
    return 0


if __name__ == '__main__':
    sys.exit(main())
