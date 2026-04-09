"""
同步球员数据：从比赛记录重新计算所有球员的累计统计
更新 FielderProfile 和 PitcherProfile 作为唯一数据源
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from database import db, Player, GameRecord, Position, FielderProfile, PitcherProfile
from datetime import datetime, timezone
from collections import defaultdict

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "baseball_players.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def sync_from_game_records():
    with app.app_context():
        print("=== 开始同步数据 ===\n")

        # 1. 获取所有比赛记录
        all_records = GameRecord.query.all()
        print(f"总比赛记录数: {len(all_records)}")

        # 2. 按球员聚合数据
        player_stats = defaultdict(lambda: {
            'batting': {
                'at_bats': 0, 'runs': 0, 'hits': 0, 'rbi': 0, 'walks': 0,
                'strikeouts': 0, 'doubles': 0, 'triples': 0, 'home_runs': 0,
                'stolen_bases': 0, 'hit_by_pitch': 0, 'caught_stealing': 0,
                'sacrifice_flys': 0, 'sacrifice_hits': 0, 'total_bases': 0
            },
            'pitching': {
                'innings_pitched': 0.0, 'hits_allowed': 0, 'runs_allowed': 0,
                'earned_runs': 0, 'walks_allowed': 0, 'strikeouts': 0,
                'home_runs_allowed': 0, 'pitches': 0, 'strikes': 0,
                'hit_by_pitch_allowed': 0, 'batters_faced': 0, 'wild_pitches': 0
            },
            'is_pitcher': False,
            'game_dates': [],
            'opponents': set()
        })

        for record in all_records:
            pid = record.player_id
            stats = player_stats[pid]

            stats['game_dates'].append(record.game_date)
            if record.opponent:
                stats['opponents'].add(record.opponent)

            if record.is_pitching_record:
                stats['is_pitcher'] = True
                p = stats['pitching']
                p['innings_pitched'] += record.innings_pitched or 0
                p['hits_allowed'] += record.hits_allowed or 0
                p['runs_allowed'] += record.runs_allowed or 0
                p['earned_runs'] += record.earned_runs or 0
                p['walks_allowed'] += record.walks_allowed or 0
                p['strikeouts'] += record.strikeouts_pitched or 0
                p['home_runs_allowed'] += record.home_runs_allowed or 0
                p['pitches'] += record.pitches or 0
                p['strikes'] += record.strikes or 0
                p['hit_by_pitch_allowed'] += record.hit_by_pitch_allowed or 0
                p['batters_faced'] += record.batters_faced or 0
                p['wild_pitches'] += record.wild_pitches or 0
            else:
                b = stats['batting']
                b['at_bats'] += record.at_bats or 0
                b['runs'] += record.runs or 0
                b['hits'] += record.hits or 0
                b['rbi'] += record.rbi or 0
                b['walks'] += record.walks or 0
                b['strikeouts'] += record.strikeouts or 0
                b['doubles'] += record.doubles or 0
                b['triples'] += record.triples or 0
                b['home_runs'] += record.home_runs_batting or 0
                b['stolen_bases'] += record.stolen_bases or 0
                b['hit_by_pitch'] += record.hit_by_pitch or 0
                b['caught_stealing'] += record.caught_stealing or 0
                b['sacrifice_flys'] += record.sacrifice_flys or 0
                b['sacrifice_hits'] += record.sacrifice_hits or 0

        print(f"从比赛记录中识别到 {len(player_stats)} 名球员\n")

        # 3. 获取所有现有球员
        existing_players = {p.id: p for p in Player.query.all()}
        print(f"数据库中现有球员: {len(existing_players)} 名\n")

        # 4. 更新每个球员的累计数据
        updated_count = 0
        for player_id, stats in player_stats.items():
            if player_id not in existing_players:
                print(f"警告: 球员ID {player_id} 在数据库中不存在，跳过")
                continue

            player = existing_players[player_id]

            # 确保 FielderProfile 存在
            if not player.fielder_profile:
                player.fielder_profile = FielderProfile()

            # 更新打击数据到 FielderProfile（唯一数据源）
            fp = player.fielder_profile
            b = stats['batting']
            fp.at_bats_total = b['at_bats']
            fp.runs_total = b['runs']
            fp.hits_total = b['hits']
            fp.rbi_total = b['rbi']
            fp.walks_total = b['walks']
            fp.strikeouts_batting_total = b['strikeouts']
            fp.doubles = b['doubles']
            fp.triples = b['triples']
            fp.home_runs_batting = b['home_runs']
            fp.stolen_bases = b['stolen_bases']
            fp.hit_by_pitch = b['hit_by_pitch']
            fp.caught_stealing = b['caught_stealing']
            fp.sacrifice_flys = b['sacrifice_flys']
            fp.sacrifice_hits = b['sacrifice_hits']

            # 计算打击率、上垒率等
            fp.update_calculated_fields()

            # 更新投手数据到 PitcherProfile（唯一数据源）
            if stats['is_pitcher']:
                if not player.pitcher_profile:
                    player.pitcher_profile = PitcherProfile()

                pp = player.pitcher_profile
                p = stats['pitching']
                pp.innings_pitched_total = p['innings_pitched']
                pp.hits_allowed_total = p['hits_allowed']
                pp.runs_allowed_total = p['runs_allowed']
                pp.earned_runs_total = p['earned_runs']
                pp.walks_allowed_total = p['walks_allowed']
                pp.strikeouts_total = p['strikeouts']
                pp.home_runs_allowed_total = p['home_runs_allowed']
                pp.pitches = p['pitches']
                pp.strikes = p['strikes']
                pp.hit_by_pitch_allowed = p['hit_by_pitch_allowed']
                pp.batters_faced = p['batters_faced']
                pp.wild_pitches = p['wild_pitches']

                pp.update_calculated_fields()

            updated_count += 1
            print(f"更新: {player.name} (ID:{player_id}) - AB:{b['at_bats']}, H:{b['hits']}, AVG:{player.batting_average:.3f}")

        # 5. 提交更改
        db.session.commit()
        print(f"\n=== 同步完成 ===")
        print(f"更新了 {updated_count} 名球员的累计数据")

        # 6. 验证结果
        print("\n=== 验证结果 ===")
        players = Player.query.all()
        for p in players[:5]:
            print(f"{p.name}: AB={p.at_bats_total}, H={p.hits_total}, AVG={p.batting_average:.3f}")

if __name__ == '__main__':
    sync_from_game_records()