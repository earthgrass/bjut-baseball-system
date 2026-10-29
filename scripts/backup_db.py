"""
数据库备份工具（Phase R4，审计 #18）
====================================
为什么：
    仓库里所有备份都是**手工产物**（instance/*.backup_*.db、recovery/ 快照），
    没有任何自动备份机制。2026-04 那次数据事故就是前车之鉴 ——
    一次误操作就可能不可逆。

做什么：
    把生产库复制成带时间戳的备份文件，放进 `instance/backups/`，
    记录 SHA256 与行数指纹，并按保留份数清理旧备份。

安全：
    · **只读**：用 SQLite 的 backup API 出一致性快照（不是裸 copy 文件），
      即使源库正在被写也不会拿到半截快照。
    · 不碰源库的任何一行。
    · 备份目录在 instance/ 下（已 gitignore）。

用法：
    python scripts/backup_db.py                 # 备份一次
    python scripts/backup_db.py --list          # 列出已有备份
    python scripts/backup_db.py --keep 10       # 保留最近 10 份（默认 10）
    DATABASE_FILE=_scratch.db python scripts/backup_db.py   # 备份副本（测试用）
"""
import os
import sys
import io
import glob
import sqlite3
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ⚠️ 只在**直接运行**时重定向 stdout —— 作为模块被 import 时劫持 sys.stdout
# 会破坏 pytest 的输出捕获（实测整个测试会话崩在 teardown）。
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


BACKUP_DIR_NAME = 'backups'


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(path):
    """记录用指纹：行数 + 日期范围 + 完整性。

    表可能不存在（比如备份的是别人的库）—— 缺失的表记 None，不抛异常。
    """
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        tables = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}

        def count(table):
            if table not in tables:
                return None
            return con.execute(f'select count(*) from "{table}"').fetchone()[0]

        fp = {
            'players': count('players'),
            'game_records': count('game_records'),
            'fielder_profiles': count('fielder_profiles'),
            'pitcher_profiles': count('pitcher_profiles'),
            'users': count('users'),
        }
        try:
            fp['date_range'] = con.execute(
                'select min(game_date), max(game_date) from game_records').fetchone()
        except Exception:
            fp['date_range'] = None
        fp['integrity'] = con.execute('PRAGMA integrity_check').fetchone()[0]
        fp['fk_violations'] = len(con.execute('PRAGMA foreign_key_check').fetchall())
        return fp
    finally:
        con.close()


def backup(db_path=None, keep=10, backup_dir=None):
    if db_path is None:
        db_path = os.environ.get('DATABASE_FILE')
        if db_path:
            if not os.path.isabs(db_path):
                # 与 app.py 一致：相对路径按 instance/ 解析
                db_path = os.path.join('instance', db_path)
        else:
            db_path = os.path.join('instance', 'baseball_players.db')
    db_path = os.path.abspath(db_path)

    if not os.path.exists(db_path):
        print(f'✗ 库不存在: {db_path}')
        return None

    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(db_path), BACKUP_DIR_NAME)
    os.makedirs(backup_dir, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = os.path.splitext(os.path.basename(db_path))[0]
    dest = os.path.join(backup_dir, f'{base}.backup_{stamp}.db')

    # SQLite backup API —— 一致性快照，不是裸 copy
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    digest = _sha256(dest)
    fp = _fingerprint(dest)
    print(f'✓ 备份完成: {dest}')
    print(f'   大小: {os.path.getsize(dest)} bytes')
    print(f'   SHA256: {digest}')
    print(f'   指纹: players={fp["players"]} game_records={fp["game_records"]} '
          f'日期范围={fp["date_range"]} integrity={fp["integrity"]} '
          f'fk={fp["fk_violations"]}')

    _prune(backup_dir, keep)
    return dest


def _prune(backup_dir, keep):
    if keep <= 0:
        return
    files = sorted(glob.glob(os.path.join(backup_dir, '*.db')),
                   key=os.path.getmtime, reverse=True)
    for old in files[keep:]:
        os.remove(old)
        print(f'   清理旧备份: {os.path.basename(old)}')


def list_backups(backup_dir=None):
    if backup_dir is None:
        backup_dir = os.path.join(os.path.abspath('instance'), BACKUP_DIR_NAME)
    files = sorted(glob.glob(os.path.join(backup_dir, '*.db')))
    if not files:
        print(f'（{backup_dir} 里没有备份）')
        return
    print(f'备份目录: {backup_dir}')
    for f in files:
        print(f'  {os.path.basename(f):50} {os.path.getsize(f):>10} bytes  '
              f'{datetime.fromtimestamp(os.path.getmtime(f)):%Y-%m-%d %H:%M:%S}')


if __name__ == '__main__':
    if '--list' in sys.argv:
        list_backups()
    else:
        keep = 10
        if '--keep' in sys.argv:
            keep = int(sys.argv[sys.argv.index('--keep') + 1])
        backup(keep=keep)
