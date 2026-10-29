#!/usr/bin/env python3
"""统计档案显式重建工具（Phase R3）

为什么有这个脚本
------------------------------------------------------------
Phase R3 之前，应用**每次启动**都会调 `sync_stats_from_game_records()`
把全队档案重算一遍。这有两个问题：

  1. 违反规范 §16「禁止启动自动修 Stats」/ §61「检测可以自动，修复必须显式」——
     它把 `game_records` 的真实漂移**静默抹平**，bug 被掩盖而不是被暴露；
  2. 每次启动都改库。实测：改一次指标公式，下一次跑测试就把新公式
     写进了生产库，而没人察觉。

所以启动现在只做审计（`database.audit_stats_drift()`），
**要修就用这个脚本，显式地修**。

用法
------------------------------------------------------------
    python scripts/rebuild_stats.py --report        # 只看漂移报告，不改库
    python scripts/rebuild_stats.py --apply         # 确认后重建
    python scripts/rebuild_stats.py --apply --yes   # 不交互确认（CI 用）

重建语义：档案 = SUM(game_records)，逐个球员重算，
不修改 `game_records` 本身 —— 规范数据永远优先。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from database import db, Player, GameRecord, rebuild_player_stats
from sqlalchemy import func


def drift_report():
    """列出每个球员「档案 vs game_records 之和」的差异。"""
    rows = []
    for player in Player.query.all():
        fp, pp = player.fielder_profile, player.pitcher_profile
        if fp:
            for column, agg in (('at_bats_total', 'at_bats'),
                                ('hits_total', 'hits'),
                                ('rbi_total', 'rbi'),
                                ('walks_total', 'walks'),
                                ('strikeouts_batting_total', 'strikeouts'),
                                ('doubles', 'doubles'),
                                ('triples', 'triples'),
                                ('home_runs_batting', 'home_runs_batting'),
                                ('stolen_bases', 'stolen_bases'),
                                ('caught_stealing', 'caught_stealing'),
                                ('hit_by_pitch', 'hit_by_pitch')):
                expected = db.session.query(
                    func.coalesce(func.sum(getattr(GameRecord, agg)), 0)).filter(
                    GameRecord.player_id == player.id,
                    GameRecord.is_pitching_record.is_(False)).scalar()
                actual = getattr(fp, column) or 0
                if actual != expected:
                    rows.append((player.name, 'fielder.' + column, actual, expected))
        if pp:
            for column, agg in (('hits_allowed_total', 'hits_allowed'),
                                ('runs_allowed_total', 'runs_allowed'),
                                ('earned_runs_total', 'earned_runs'),
                                ('walks_allowed_total', 'walks_allowed'),
                                ('strikeouts_total', 'strikeouts_pitched'),
                                ('pitches', 'pitches'),
                                ('strikes', 'strikes'),
                                ('batters_faced', 'batters_faced'),
                                ('wild_pitches', 'wild_pitches')):
                expected = db.session.query(
                    func.coalesce(func.sum(getattr(GameRecord, agg)), 0)).filter(
                    GameRecord.player_id == player.id,
                    GameRecord.is_pitching_record.is_(True)).scalar()
                actual = getattr(pp, column) or 0
                if actual != expected:
                    rows.append((player.name, 'pitcher.' + column, actual, expected))
    return rows


def main():
    apply = '--apply' in sys.argv
    assume_yes = '--yes' in sys.argv

    with app.app_context():
        rows = drift_report()
        print('=' * 70)
        print('统计档案漂移报告')
        print('=' * 70)
        if not rows:
            print('  档案与 game_records 完全一致，无需重建。')
            return 0

        print('  发现 %d 处不一致：\n' % len(rows))
        for name, field, actual, expected in rows:
            print('    %-10s %-32s 档案=%-8s 记录合计=%-8s' % (name, field, actual, expected))

        if not apply:
            print('\n（只报告，未改库。确认无误后加 --apply 执行重建）')
            return 1

        if not assume_yes:
            answer = input('\n确认按 game_records 重建这些档案？[y/N] ').strip().lower()
            if answer not in ('y', 'yes'):
                print('已取消。')
                return 1

        players = {p.id: p.name for p in Player.query.all()}
        for pid in sorted(players):
            rebuild_player_stats(pid)
        db.session.commit()

        after = drift_report()
        print('\n重建完成。重建后仍有 %d 处不一致。' % len(after))
        for name, field, actual, expected in after:
            print('    %-10s %-32s 档案=%-8s 记录合计=%-8s' % (name, field, actual, expected))
        return 0 if not after else 2


if __name__ == '__main__':
    sys.exit(main())
