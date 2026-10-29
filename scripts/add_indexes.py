"""
索引迁移 —— 给热点表补索引（Phase R4，审计 #17）
=================================================
为什么：
    迁移前 `game_records` / `players` / `player_positions` **一个索引都没有**，
    连外键列都没索引。`EXPLAIN QUERY PLAN` 实测全是 `SCAN`：

        select count(*) from game_records where player_id=1
        -> SCAN game_records
        select count(*) from players where name='欧阳翦'
        -> SCAN players

    现在 230 行无痛，但每个赛季增长后这是 scaling 风险 ——
    而「重建档案」「覆盖导入按日期+对手删旧记录」是每次写入都要跑的高频查询。

做什么：
    按 database.py 里模型声明的索引，给**已存在的库**补建索引。
    模型声明 → 新建库（`db.create_all()`）自动带上；
    本脚本 → 老库（生产库）补建。两者必须同时存在，缺一不可。

安全：
    · 只做 `CREATE INDEX IF NOT EXISTS` —— **不删数据、不改数据**，
      只是让 SQLite 多维护一份 B-tree。
    · 幂等：重复跑没有副作用。
    · 不在生产库上首次试验 —— 先在副本上跑（见报告）。

用法：
    python scripts/add_indexes.py --dry-run     # 只报告，不建
    python scripts/add_indexes.py                # 建索引
    DATABASE_FILE=_scratch.db python scripts/add_indexes.py   # 打在副本上
"""
import os
import sys
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows 控制台编码
# ⚠️ 只在**直接运行**时重定向 stdout —— 作为模块被 import 时劫持 sys.stdout
# 会破坏 pytest 的输出捕获（实测整个测试会话崩在 teardown）。
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')



# 索引定义 —— 与 database.py 的模型声明一一对应
INDEXES = [
    # (表, 索引名, 列)
    ('game_records', 'ix_game_records_player', ['player_id', 'is_pitching_record']),
    ('game_records', 'ix_game_records_game', ['game_date', 'opponent']),
    ('players', 'ix_players_name', ['name']),
    ('players', 'ix_players_jersey_number', ['jersey_number']),
    ('player_positions', 'ix_player_positions_position', ['position_id']),
]

# 用来看效果的关键查询
PROBES = [
    ("select count(*) from game_records where player_id = 1",
     '重建档案：按球员取记录'),
    ("select count(*) from game_records where game_date = '2024-11-16' "
     "and opponent = '北京交通大学'",
     '覆盖导入：按日期+对手删旧记录'),
    ("select count(*) from players where name = '欧阳翦'",
     '导入：按名字找球员'),
]


def _existing_indexes(conn):
    result = {}
    for table, in conn.execute(
            "select name from sqlite_master where type='table'").fetchall():
        names = [r[1] for r in conn.execute(f'PRAGMA index_list("{table}")')]
        result[table] = names
    return result


def _plan(conn, sql):
    rows = conn.execute('EXPLAIN QUERY PLAN ' + sql).fetchall()
    return ' | '.join(r[3] for r in rows)


def main(dry_run=False):
    from app import app
    from database import db

    with app.app_context():
        uri = str(db.engine.url)
        print(f'目标库: {uri}')
        engine = db.engine
        raw = engine.raw_connection()
        conn = raw.driver_connection if hasattr(raw, 'driver_connection') else raw.connection
        try:
            before = _existing_indexes(conn)
            print('\n=== 迁移前 ===')
            for table, names in sorted(before.items()):
                print(f'  {table:20} {names}')
            print('\n关键查询的执行计划（迁移前）:')
            for sql, label in PROBES:
                try:
                    print(f'  [{label}] {sql}\n      -> {_plan(conn, sql)}')
                except Exception as e:
                    print(f'  [{label}] 探针失败: {e}')

            created, skipped = [], []
            for table, name, columns in INDEXES:
                exists = name in before.get(table, [])
                if exists:
                    skipped.append(name)
                    continue
                if dry_run:
                    created.append(f'{name} (待建)')
                    continue
                cols = ', '.join(columns)
                conn.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ({cols})')
                created.append(f'{name} ({table}: {cols})')

            if not dry_run:
                conn.commit()

            after = _existing_indexes(conn)
            print('\n=== 迁移后 ===')
            for table, names in sorted(after.items()):
                print(f'  {table:20} {names}')
            print('\n关键查询的执行计划（迁移后）:')
            for sql, label in PROBES:
                try:
                    print(f'  [{label}] {sql}\n      -> {_plan(conn, sql)}')
                except Exception as e:
                    print(f'  [{label}] 探针失败: {e}')

            print(f'\n新建索引 {len(created)} 个:')
            for c in created:
                print(f'    + {c}')
            print(f'已存在跳过 {len(skipped)} 个:')
            for s in skipped:
                print(f'    = {s}')
            if dry_run:
                print('\n（dry-run：没有真正建索引）')
        finally:
            raw.close()


if __name__ == '__main__':
    dry = '--dry-run' in sys.argv
    main(dry_run=dry)
