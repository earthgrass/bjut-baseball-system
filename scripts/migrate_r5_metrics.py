"""
R5 数据迁移 —— WHIP 标准口径 + PDF 页脚修复带来的 BF 补全
============================================================
为什么要迁移：
    1. WHIP 的分母从「投球局数」改成「面对打席数」（标准口径）→
       档案表 pitcher_profiles.whip 的值全部要重算
       （实测旧值离谱：库里有 5.60 / 3.56 / 3.53 这种数）
    2. PDF 页脚修复后，5 场原本漏掉「面对打席数」的记录能补回真值 →
       game_records 要重导（页面脚粘在最后一条后面把整条吞了）

流程（规范 §25：任何迁移先在生产库副本上跑，出报告，最后才考虑生产）：
    1. 复制生产库 → instance/_r5_migration.db
    2. 在**副本**上重导 17 份 PDF（--replace），档案随之重建
    3. 用 scripts/compare_db.py 的口径逐条比对（生产库 vs 迁移后副本）
    4. 打印迁移报告
    5. 只有加 --apply 且副本验证通过，才写生产库（写之前自动备份）

用法：
    python scripts/migrate_r5_metrics.py          # 只在副本上跑 + 出报告
    python scripts/migrate_r5_metrics.py --apply  # 验证通过后写生产库（自动备份）

⚠️ 本脚本**不做 schema 变更**（不新增列、不删列）—— 只是重算与重导。
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
COPY_DB = os.path.join(INSTANCE, '_r5_migration.db')

sys.path.insert(0, ROOT)


def _log(msg):
    print(msg, flush=True)


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _counts(path):
    """取关键表的行数与指纹（迁移前后必须逐项对照）。"""
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        c = con.cursor()
        out = {}
        for table in ('players', 'game_records', 'fielder_profiles',
                      'pitcher_profiles', 'positions'):
            try:
                out[table] = c.execute(
                    'SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            except sqlite3.Error:
                out[table] = None
        return out
    finally:
        con.close()


def _whip_table(path):
    """每位投手的 WHIP（迁移前后对照用）。"""
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        c = con.cursor()
        rows = c.execute("""
            SELECT p.name, pp.whip, pp.batters_faced, pp.innings_pitched_total
            FROM pitcher_profiles pp JOIN players p ON p.id = pp.player_id
            ORDER BY p.name
        """).fetchall()
        return {r[0]: {'whip': r[1], 'bf': r[2], 'ip': r[3]} for r in rows}
    finally:
        con.close()


def _bf_gaps(path):
    """有多少条投球记录缺「面对打席数」（WHIP 的分母来源）。"""
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        c = con.cursor()
        total = c.execute(
            'SELECT COUNT(*) FROM game_records WHERE is_pitching_record=1'
        ).fetchone()[0]
        with_bf = c.execute(
            'SELECT COUNT(*) FROM game_records WHERE is_pitching_record=1 '
            'AND COALESCE(batters_faced,0) > 0').fetchone()[0]
        return {'total': total, 'with_bf': with_bf}
    finally:
        con.close()


def _run_import(db_path):
    """在指定库上重导 17 份 PDF（--replace），档案随之重建。

    必须用**子进程 + 环境变量**：Flask-SQLAlchemy 在 init_app() 里就
    eager 创建 engine，之后再改 URI 不生效（见 app.py 注释与 HANDOFF）。
    """
    env = dict(os.environ)
    env['DATABASE_FILE'] = db_path
    env['PYTHONIOENCODING'] = 'utf-8'
    proc = subprocess.run(
        [sys.executable, 'import_pdfs.py', '--replace'],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace')
    return proc


def _print_report(before_path, after_path):
    _log('')
    _log('=' * 72)
    _log('R5 迁移报告')
    _log('=' * 72)

    _log('\n【行数对照】')
    before, after = _counts(before_path), _counts(after_path)
    for table in before:
        b, a = before[table], after.get(table)
        flag = '' if b == a else '   ← 变化！'
        _log('  %-18s %6s → %6s%s' % (table, b, a, flag))

    _log('\n【投球记录的「面对打席数」覆盖】')
    gb, ga = _bf_gaps(before_path), _bf_gaps(after_path)
    _log('  迁移前: %d/%d 条有 BF（缺 %d）'
         % (gb['with_bf'], gb['total'], gb['total'] - gb['with_bf']))
    _log('  迁移后: %d/%d 条有 BF（缺 %d）'
         % (ga['with_bf'], ga['total'], ga['total'] - ga['with_bf']))

    _log('\n【WHIP 对照】（分母从「投球局数」改成「面对打席数」）')
    wb, wa = _whip_table(before_path), _whip_table(after_path)
    _log('  %-10s %8s %8s   %s' % ('投手', '迁移前', '迁移后', '说明'))
    for name in sorted(set(wb) | set(wa)):
        old = wb.get(name, {}).get('whip', 0) or 0
        new = wa.get(name, {}).get('whip', 0) or 0
        note = ''
        if abs((old or 0) - (new or 0)) > 0.001:
            note = '口径修正'
        _log('  %-10s %8.2f %8.2f   %s' % (name, old, new, note))

    _log('\n【指纹】')
    _log('  迁移前 SHA256: %s' % _sha256(before_path))
    _log('  迁移后 SHA256: %s' % _sha256(after_path))


def _integrity(path):
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        c = con.cursor()
        integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        fk = c.execute('PRAGMA foreign_key_check').fetchall()
        return integrity, len(fk)
    finally:
        con.close()


def main():
    apply = '--apply' in sys.argv

    if not os.path.exists(PROD_DB):
        _log('!! 生产库不存在: %s' % PROD_DB)
        return 1

    _log('生产库: %s' % PROD_DB)
    _log('生产库 SHA256（迁移前）: %s' % _sha256(PROD_DB))

    # ── 1. 复制到副本 ──
    if os.path.exists(COPY_DB):
        os.remove(COPY_DB)
    shutil.copy2(PROD_DB, COPY_DB)
    _log('副本已建: %s' % COPY_DB)

    # ── 2. 在副本上重导 ──
    _log('\n--- 在副本上重导 17 份 PDF（--replace）---')
    proc = _run_import(COPY_DB)
    tail = [ln for ln in (proc.stdout or '').splitlines() if ln.strip()][-14:]
    for ln in tail:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 副本迁移失败（returncode=%s）' % proc.returncode)
        _log((proc.stderr or '')[-2000:])
        _log('生产库未被改动 ✓')
        return 1

    # ── 3. 验证 + 报告 ──
    integrity, fk = _integrity(COPY_DB)
    _print_report(PROD_DB, COPY_DB)
    _log('\n【完整性】integrity_check=%s  foreign_key_check=%d 条' % (integrity, fk))

    if not apply:
        _log('\n这是**预览**。生产库未被改动 ✓')
        _log('确认报告无误后加 --apply 执行正式迁移。')
        return 0

    # ── 4. 写生产库 ──
    if integrity != 'ok' or fk:
        _log('\n!! 副本完整性检查未通过，拒绝写生产库')
        return 1

    backup = os.path.join(
        INSTANCE, 'baseball_players.pre_r5_%s.db' % time.strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(PROD_DB, backup)
    _log('\n生产库已备份: %s' % backup)
    _log('生产库 SHA256（备份）: %s' % _sha256(backup))

    _log('\n--- 写生产库 ---')
    proc = _run_import(PROD_DB)
    for ln in [ln for ln in (proc.stdout or '').splitlines() if ln.strip()][-14:]:
        _log('  ' + ln)
    if proc.returncode != 0:
        _log('\n!! 生产库迁移失败 —— 回滚：把备份复制回去')
        _log('  cp "%s" "%s"' % (backup, PROD_DB))
        _log((proc.stderr or '')[-2000:])
        return 1

    integrity2, fk2 = _integrity(PROD_DB)
    _log('\n迁移后 integrity_check=%s  foreign_key_check=%d' % (integrity2, fk2))
    _log('生产库 SHA256（迁移后）: %s' % _sha256(PROD_DB))
    _log('备份文件: %s' % backup)
    return 0


if __name__ == '__main__':
    sys.exit(main())
