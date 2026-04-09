"""
PDF 比赛记录批量导入脚本
用法:
  python import_pdfs.py --dry-run    # 预览模式，不写入数据库
  python import_pdfs.py              # 实际导入
"""

import sys
import os
import io
import json
import traceback

from datetime import datetime
from difflib import SequenceMatcher

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_parser import parse_pdf
from database import db, Player, GameRecord, Position, init_positions
from app import app  # 引入 Flask app 以使用其数据库


# 修复 Windows 控制台编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# ---------- 模糊匹配 ----------


def _fuzzy_match_name(parsed_name, threshold=0.6):
    """模糊匹配球员名: 基于 Sequence similarity 找到最相似的已有球员。"""
    all_players = Player.query.all()
    best_match = None
    best_score = 0.0
    for player in all_players:
        matcher = SequenceMatcher(None, parsed_name, player.name)
        score = matcher.ratio()
        if score > best_score:
            best_score = score
            best_match = player
    if best_score >= threshold:
        return best_match, best_score
    return None, 0.0


def find_or_create_player(name, jersey_number=None, position=None):
    """查找或创建球员，优先精确匹配，然后模糊匹配"""
    pos_map = {
        'P': '投手', 'C': '捕手', '1B': '一垒手', '2B': '二垒手',
        '3B': '三垒手', 'SS': '游击手', 'LF': '左外野手',
        'CF': '中外野手', 'RF': '右外野手',
    }
    pos_cn = pos_map.get(position, position)

    # 1. 精确匹配
    player = Player.query.filter_by(name=name).first()
    if player:
        return player, False  # 已存在

    # 2. 模糊匹配
    fuzzy, fuzzy_score = _fuzzy_match_name(name)
    if fuzzy:
        return fuzzy, False

    # 3. 创建新球员
    player = Player(
        name=name,
        jersey_number=jersey_number or '0',
        primary_position=pos_cn or '未指定',
        join_date=datetime.now().date()
    )

    if position == 'P' or position == '投手':
        player.apply_player_type('pitcher')
        player.set_positions_by_names(['投手'])
    else:
        player.apply_player_type('fielder')
        if pos_cn and pos_cn != '未指定':
            player.set_positions_by_names([pos_cn])
            player.primary_position = pos_cn
    player.normalize_positions()

    # 初始化统计字段
    for field in ['at_bats_total', 'hits_total', 'rbi_total', 'walks_total',
                  'strikeouts_batting_total', 'doubles', 'triples',
                  'home_runs_batting', 'total_bases', 'hit_by_pitch',
                  'stolen_bases', 'caught_stealing', 'sacrifice_flys',
                  'sacrifice_hits', 'innings_pitched_total',
                  'hits_allowed_total', 'runs_allowed_total',
                  'earned_runs_total', 'walks_allowed_total',
                  'strikeouts_total', 'home_runs_allowed_total',
                  'pitches', 'strikes', 'hit_by_pitch_allowed',
                  'batters_faced']:
        setattr(player, field, 0)
    for field in ['batting_average', 'on_base_percentage',
                  'slugging_percentage', 'ops', 'era', 'whip']:
        setattr(player, field, 0.0)
    db.session.add(player)
    return player, True  # 新创建


def import_game_record(result, dry_run=False):
    """导入单场比赛的所有数据"""
    game_date = result.get('game_date')
    opponent = result.get('opponent', '未知')
    filepath = result.get('filepath', '')
    if not game_date:
        return {'status': 'skip', 'reason': '无比赛日期'}
    game_date_obj = datetime.strptime(game_date, '%Y-%m-%d').date()
    imported_batting = 0
    imported_pitching = 0
    skipped = 0
    new_players = []
    details = []

    # 导入打击数据
    for batter in result.get('my_team_batting', []):
        name = batter['name']
        jersey = batter.get('jersey_number')
        if not dry_run:
            player, is_new = find_or_create_player(name, jersey, batter.get('position'))
            if is_new:
                new_players.append(name)
            # 去重检查: 同球员同日期同对手
            existing = GameRecord.query.filter_by(
                player_id=player.id,
                game_date=game_date_obj,
                opponent=opponent
            ).first()
            if existing:
                skipped += 1
                continue
            # 创建比赛记录
            record = GameRecord(
                player_id=player.id,
                game_date=game_date_obj,
                opponent=opponent,
                is_pitching_record=False,
                at_bats=batter['at_bats'],
                runs=batter['runs'],
                hits=batter['hits'],
                rbi=batter['rbi'],
                walks=batter['walks'],
                strikeouts=batter['strikeouts'],
                doubles=batter['doubles'],
                triples=batter['triples'],
                home_runs_batting=batter['home_runs'],
                total_bases=batter['total_bases'],
                stolen_bases=batter['stolen_bases'],
                caught_stealing=batter['caught_stealing'],
                hit_by_pitch=batter['hit_by_pitch'],
            )
            db.session.add(record)
            # 更新球员累计数据
            player.at_bats_total += batter['at_bats']
            player.runs_total += batter['runs']
            player.hits_total += batter['hits']
            player.rbi_total += batter['rbi']
            player.walks_total += batter['walks']
            player.strikeouts_batting_total += batter['strikeouts']
            player.doubles += batter['doubles']
            player.triples += batter['triples']
            player.home_runs_batting += batter['home_runs']
            player.total_bases += batter['total_bases']
            player.stolen_bases += batter['stolen_bases']
            player.caught_stealing += batter['caught_stealing']
            player.hit_by_pitch += batter['hit_by_pitch']
            player.update_calculated_fields()
        imported_batting += 1
        details.append(f"  打击: {name} AB={batter['at_bats']} H={batter['hits']} RBI={batter['rbi']}")

    # 导入投手数据
    for pitcher in result.get('my_team_pitching', []):
        name = pitcher['name']
        jersey = pitcher.get('jersey_number')
        if not dry_run:
            player, is_new = find_or_create_player(name, jersey, 'P')
            if is_new and name not in new_players:
                new_players.append(name)
            if not player._is_pitcher:
                player.apply_player_type('pitcher')
            # 去重检查
            existing = GameRecord.query.filter_by(
                player_id=player.id,
                game_date=game_date_obj,
                opponent=opponent,
                is_pitching_record=True
            ).first()
            if existing:
                skipped += 1
                continue
            record = GameRecord(
                player_id=player.id,
                game_date=game_date_obj,
                opponent=opponent,
                is_pitching_record=True,
                innings_pitched=pitcher['innings_pitched'],
                hits_allowed=pitcher['hits_allowed'],
                runs_allowed=pitcher['runs_allowed'],
                earned_runs=pitcher['earned_runs'],
                walks_allowed=pitcher['walks_allowed'],
                strikeouts_pitched=pitcher['strikeouts'],
                home_runs_allowed=pitcher['home_runs_allowed'],
                pitches=pitcher['pitches'],
                strikes=pitcher['strikes'],
                hit_by_pitch_allowed=pitcher['hit_by_pitch_allowed'],
                batters_faced=pitcher['batters_faced'],
                win=pitcher['win'],
                loss=pitcher['loss'],
                save=pitcher['save'],
            )
            db.session.add(record)
            # 更新球员累计数据
            player.innings_pitched_total += pitcher['innings_pitched']
            player.hits_allowed_total += pitcher['hits_allowed']
            player.runs_allowed_total += pitcher['runs_allowed']
            player.earned_runs_total += pitcher['earned_runs']
            player.walks_allowed_total += pitcher['walks_allowed']
            player.strikeouts_total += pitcher['strikeouts']
            player.home_runs_allowed_total += pitcher['home_runs_allowed']
            player.pitches += pitcher['pitches']
            player.strikes += pitcher['strikes']
            player.hit_by_pitch_allowed += pitcher['hit_by_pitch_allowed']
            player.batters_faced += pitcher['batters_faced']
            # 计算防御率和 WHIP
            if player.innings_pitched_total > 0:
                player.era = round(
                    (player.earned_runs_total * 9) / player.innings_pitched_total, 2)
                player.whip = round(
                    (player.walks_allowed_total + player.hits_allowed_total) /
                    player.innings_pitched_total, 2)
        imported_pitching += 1
        details.append(
            f"  投手: {name} IP={pitcher['innings_pitched']} ER={pitcher['earned_runs']}")

    if not dry_run:
        db.session.commit()

    return {
        'status': 'ok',
        'batting': imported_batting,
        'pitching': imported_pitching,
        'skipped': skipped,
        'new_players': new_players,
        'details': details,
        'date': game_date,
        'opponent': opponent
    }


def import_all_pdfs(dry_run=False):
    """导入 data/ 目录下所有 PDF 文件"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if not os.path.exists(data_dir):
        print(f"数据目录不存在: {data_dir}")
        return []

    results = []
    pdf_files = []
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, f))

    pdf_files.sort()
    print(f"找到 {len(pdf_files)} 个 PDF 文件")

    for filepath in pdf_files:
        filename = os.path.basename(filepath)
        print(f"\n{'='*60}")
        print(f"处理: {filename}")
        print(f"{'='*60}")

        try:
            parsed = parse_pdf(filepath)
            if 'error' in parsed:
                print(f"  错误: {parsed['error']}")
                results.append({'file': filename, 'status': 'error', 'error': parsed['error']})
                continue

            print(f"  日期: {parsed.get('game_date')}")
            print(f"  对手: {parsed.get('opponent')}")
            print(f"  打击数据: {len(parsed.get('my_team_batting', []))} 条")
            print(f"  投手数据: {len(parsed.get('my_team_pitching', []))} 条")

            if not parsed.get('my_team_batting') and not parsed.get('my_team_pitching'):
                print(f"  跳过: 无有效数据")
                results.append({'file': filename, 'status': 'skip', 'reason': '无有效数据'})
                continue

            import_result = import_game_record(parsed, dry_run=dry_run)

            for detail in import_result.get('details', []):
                print(detail)

            if import_result['status'] == 'ok':
                print(f"  导入成功: 打击 {import_result['batting']} 条, 投手 {import_result['pitching']} 条")
                if import_result['new_players']:
                    print(f"  新球员: {', '.join(import_result['new_players'])}")
                if import_result['skipped']:
                    print(f"  跳过(重复): {import_result['skipped']} 条")

            results.append({
                'file': filename,
                **import_result
            })

        except Exception as e:
            print(f"  异常: {e}")
            traceback.print_exc()
            results.append({'file': filename, 'status': 'error', 'error': str(e)})

    # 汇总
    total_batting = sum(r.get('batting', 0) for r in results)
    total_pitching = sum(r.get('pitching', 0) for r in results)
    total_skipped = sum(r.get('skipped', 0) for r in results)
    total_errors = sum(1 for r in results if r.get('status') == 'error')
    all_new = set()
    for r in results:
        all_new.update(r.get('new_players', []))

    print(f"\n{'='*60}")
    print(f"导入完成！")
    print(f"  PDF 文件: {len(pdf_files)}")
    print(f"  打击记录: {total_batting}")
    print(f"  投手记录: {total_pitching}")
    print(f"  跳过(重复): {total_skipped}")
    print(f"  错误: {total_errors}")
    print(f"  新球员: {len(all_new)}")
    if all_new:
        print(f"  新球员列表: {', '.join(sorted(all_new))}")
    print(f"{'='*60}")

    return results


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("=== 预览模式（不写入数据库）===")

    with app.app_context():
        init_positions()
        import_all_pdfs(dry_run=dry_run)
