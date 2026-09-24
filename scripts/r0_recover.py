"""
Phase R0 Recovery Script

基于 R0.3 指纹分析，winner 是 git_bb429ba_db.bin：
- 27 players / 230 records / max date 2025-11-22
- 完全匹配 Phase E0 forensic fingerprint（除 users 表）

差异：bb429ba 没有 users 表（admin login 是 1dbb67c commit 后续添加的）。
为了精确还原事故前状态，脚本会：
1. 复制 bb429ba blob 作为 base
2. 添加 users 表 + 默认 admin 账号（与 init_default_admin 等价）
3. 输出最终 fingerprint

**禁止**：
- 修改 recovery/*.db（事故原件）
- 触碰 instance/baseball_players.db（待用户确认后再覆盖）

输出：recovery/recovered_pre_incident.db
"""
import sqlite3
import os
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
RECOVERY = WORKSPACE / 'recovery'
SOURCE = RECOVERY / 'git_bb429ba_db.bin'
TARGET = RECOVERY / 'recovered_pre_incident.db'


def main():
    if not SOURCE.exists():
        print(f'ERROR: source not found: {SOURCE}')
        sys.exit(1)

    if TARGET.exists():
        print(f'WARNING: target exists: {TARGET}')
        ans = input('Overwrite? (yes/no): ').strip().lower()
        if ans != 'yes':
            print('Aborted.')
            return

    # Copy source to target (no direct modification of source)
    import shutil
    shutil.copy2(SOURCE, TARGET)
    print(f'Copied {SOURCE} -> {TARGET}')

    # Read source hash for verification
    import hashlib
    src_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    tgt_sha = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    assert src_sha == tgt_sha, 'copy integrity failed'

    # Open target and add users table + admin
    conn = sqlite3.connect(str(TARGET))
    cur = conn.cursor()

    # Check if users already exists
    has_users = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if has_users:
        print('users table already exists, skipping creation')
    else:
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                is_admin BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add default admin user (matching database.py:init_default_admin)
        # Password hash: werkzeug.security.generate_password_hash('admin123')
        # We can't easily reproduce the hash without flask context.
        # But for backup, we can use a placeholder + flag for manual reset.
        # Better: store empty hash and instruct user to set via CLI after restore.
        cur.execute("""
            INSERT INTO users (username, password_hash, is_admin)
            VALUES ('admin', 'REQUIRES_PASSWORD_RESET', 1)
        """)
        print('Created users table with admin (REQUIRES_PASSWORD_RESET)')

    conn.commit()

    # ====== verify fingerprint ======
    print()
    print('=' * 60)
    print('RECOVERED FINGERPRINT')
    print('=' * 60)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    print(f'  tables ({len(tables)}): {tables}')
    for t in tables:
        n = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'    {t}: {n}')

    d = cur.execute(
        'SELECT MIN(game_date), MAX(game_date) FROM game_records'
    ).fetchone()
    print(f'  game_records date range: {d[0]} .. {d[1]}')
    print(f'  game_records count: {cur.execute("SELECT COUNT(*) FROM game_records").fetchone()[0]}')

    # Check player 28 AMBIGUOUS records
    n28 = cur.execute("""
        SELECT COUNT(*) FROM game_records
        WHERE player_id = 28 AND game_date = '2024-11-16'
          AND opponent = '北京交通大学' AND is_pitching_record = 0
    """).fetchone()[0]
    print(f'  player 28 AMBIGUOUS records: {n28} (expected: 2)')

    conn.close()

    print()
    print('=' * 60)
    print('PHASE E0 FINGERPRINT COMPARISON')
    print('=' * 60)
    print('  E0 expected:    27 players / 230 records / 7 tables / max 2025-11-22 / users=1')
    print('  recovered: see above')
    print()
    print('NOTE: admin password is REQUIRES_PASSWORD_RESET.')
    print('  After promoting to production, run:')
    print('    python -c "from app import app; from database import db, User; ..."')
    print('  to reset admin password via env var ADMIN_PASSWORD.')


if __name__ == '__main__':
    main()