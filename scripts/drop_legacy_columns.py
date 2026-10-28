#!/usr/bin/env python3
"""清理 players 表的 legacy 统计列。

背景
----
历史上所有累计统计都存在 `players` 表里。后来模型拆成
`players` + `fielder_profiles` + `pitcher_profiles`，统计搬到了 profile 表，
但 `players` 表的物理列还在（SQLAlchemy 不会自动删列）。

`database.py:migrate_legacy_player_stats()` 会在每次启动时把这些旧列清零，
所以它们**永远是 0** —— 但列还在（42 列里 34 列是死的）。

危害
----
1. 用 DB 工具打开 players 表，会看到"有表但统计全是空的"，极易误判为数据丢失
2. 是误导性的脚手架：改这些列没有任何效果
3. 占体积、干扰新人理解数据模型

本脚本
------
把 players 表裁剪到 ORM 真正映射的 8 列：
    id, name, jersey_number, primary_position, is_pitcher,
    birth_date, join_date, contact_phone

安全性
------
- 真实数据在 fielder_profiles / pitcher_profiles / game_records，**本脚本不碰它们**
- 先自动备份，再执行
- 支持 --dry-run
- 幂等：已经是 8 列时直接退出
- SQLite 需要 >= 3.35（Python 3.9+ 自带版本通常满足）

用法
----
    python scripts/drop_legacy_columns.py --dry-run    # 只看会删什么
    python scripts/drop_legacy_columns.py              # 实际执行（自动备份）
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ORM 里 Player 模型真正映射的列
KEEP_COLUMNS = [
    'id',
    'name',
    'jersey_number',
    'primary_position',
    'is_pitcher',
    'birth_date',
    'join_date',
    'contact_phone',
]


def resolve_db_path():
    """与 app.py 保持一致：DATABASE_FILE 环境变量 > instance/baseball_players.db"""
    override = os.environ.get('DATABASE_FILE', '').strip()
    if override:
        if os.path.isabs(override):
            return override
        return os.path.join(ROOT, 'instance', override)
    return os.path.join(ROOT, 'instance', 'baseball_players.db')


def table_columns(conn, table):
    return [r[1] for r in conn.execute('PRAGMA table_info(%s)' % table)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='只打印将要执行的变更')
    parser.add_argument('--db', help='指定数据库文件路径（默认与 app.py 一致）')
    args = parser.parse_args()

    db_path = args.db or resolve_db_path()
    if not os.path.exists(db_path):
        print('[x] 数据库不存在: %s' % db_path)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        cols = table_columns(conn, 'players')
        legacy = [c for c in cols if c not in KEEP_COLUMNS]

        print('数据库: %s' % db_path)
        print('players 当前列数: %d' % len(cols))

        if not legacy:
            print('[ok] players 表已是干净的 %d 列，无需处理' % len(KEEP_COLUMNS))
            return 0

        print('将要删除的 legacy 列 (%d 个):' % len(legacy))
        for c in legacy:
            print('    - %s' % c)

        if args.dry_run:
            print('\n[dry-run] 未做任何修改')
            return 0

        # 检查这些列上有没有索引（有索引则 SQLite 不允许 DROP COLUMN）
        idx_rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='players'"
        ).fetchall()
        blocked = []
        for idx_name, idx_sql in idx_rows:
            if not idx_sql:
                continue  # sqlite_autoindex_* 隐式索引
            for c in legacy:
                if c in idx_sql:
                    blocked.append((idx_name, c))
        if blocked:
            print('[x] 以下 legacy 列被索引引用，无法删除: %s' % blocked)
            return 1

        # 备份
        backup = '%s.pre_colundrop_%s.db' % (
            os.path.splitext(db_path)[0],
            datetime.now().strftime('%Y%m%d_%H%M%S'))
        conn.commit()
        shutil.copyfile(db_path, backup)
        print('\n已备份 -> %s' % backup)

        # 逐列删除（SQLite 不支持一条语句删多列）
        for c in legacy:
            try:
                conn.execute('ALTER TABLE players DROP COLUMN "%s"' % c)
            except sqlite3.OperationalError as e:
                print('[!] 无法删除列 %s: %s' % (c, e))
                conn.rollback()
                print('[x] 已回滚，数据库未变更')
                return 1
        conn.commit()

        after = table_columns(conn, 'players')
        print('\n[ok] 完成。players 列数: %d -> %d' % (len(cols), len(after)))
        print('     剩余列: %s' % ', '.join(after))

        # 校验真实数据未受影响
        for t in ('players', 'game_records', 'fielder_profiles', 'pitcher_profiles'):
            n = conn.execute('SELECT count(*) FROM %s' % t).fetchone()[0]
            print('     %-18s %d 行' % (t, n))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
