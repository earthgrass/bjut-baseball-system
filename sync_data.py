"""
同步球员档案：从 game_records 重算全部累计统计（兼容入口）
==========================================================
⚠️ 这个脚本以前**自带一套聚合实现** —— 24 处 `+=` 增量、局数按**字面值**
   累加、还硬编码了生产库路径（忽略 DATABASE_FILE）。也就是说：
     · 它算出来的数和 `database.rebuild_player_stats()` 可能不一样
       （局数记法 .1 = 1/3 局这一条就不一样）；
     · 在别的 DATABASE_FILE 下跑，它照样写生产库；
     · 它是「档案 = SUM(game_records)」这条不变量的**第二个实现**，
       两边各写各的，档案迟早漂移。

现在它只做一件事：调用权威实现（`database.rebuild_player_stats`）。
指标公式、局数换算、聚合口径全部以 `database.py` / `metrics.py` 为准。

用法：
    python sync_data.py                    # 用默认库（instance/baseball_players.db）
    DATABASE_FILE=_scratch.db python sync_data.py   # 打在副本上
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ⚠️ 只在**直接运行**时重定向 stdout —— 作为模块被 import 时劫持 sys.stdout
# 会破坏 pytest 的输出捕获。
if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app import app
from database import db, Player, GameRecord, rebuild_player_stats


def sync_from_game_records():
    """把所有**有比赛记录**的球员档案从 game_records 重算一遍。

    只处理有记录的球员 —— 没有记录的球员档案保持原样，
    与 `database.sync_stats_from_game_records()` 的口径一致。
    """
    with app.app_context():
        print('=== 开始同步数据 ===')

        all_records = GameRecord.query.all()
        print(f'总比赛记录数: {len(all_records)}')

        player_ids = sorted({r.player_id for r in all_records})
        print(f'从比赛记录中识别到 {len(player_ids)} 名球员\n')

        existing = {p.id: p for p in Player.query.all()}
        updated = 0
        for pid in player_ids:
            if pid not in existing:
                print(f'警告: 球员ID {pid} 在数据库中不存在，跳过')
                continue
            rebuild_player_stats(pid)
            updated += 1

        db.session.commit()

        print('\n=== 同步完成 ===')
        print(f'更新了 {updated} 名球员的累计数据')

        print('\n=== 验证结果 ===')
        for p in Player.query.order_by(Player.id).limit(5):
            print(f'{p.name}: AB={p.at_bats_total}, H={p.hits_total}, '
                  f'AVG={p.batting_average:.3f}')


if __name__ == '__main__':
    sync_from_game_records()
