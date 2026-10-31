"""
PDF 比赛记录批量导入脚本
用法:
  python import_pdfs.py --dry-run    # 预览模式，不写入数据库
  python import_pdfs.py              # 实际导入
"""

import sys
import os
import io
import traceback

from datetime import datetime
from difflib import SequenceMatcher

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_ingest import parse_pdf
from database import (db, Player, GameRecord, init_positions,
                       rebuild_player_stats)
from app import app  # 引入 Flask app 以使用其数据库


# 修复 Windows 控制台编码
# ⚠️ 只在**直接运行**时做 —— 作为模块被 import 时劫持 sys.stdout 会破坏
# pytest 的输出捕获（实测整个测试会话崩在 teardown）。
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# ---------- 模糊匹配 ----------

# PDF 里同一个人的两种写法（业务方已确认，2026-10-29）：
#   '欧阳' 与 '欧阳翦' 是**同一个人**（2024-11-16 vs 北京交通大学的 box score
#   里，同一件 23 号在打击表出现两次，一次写 '欧阳'（RF）、一次写 '欧阳翦'（P））。
# 显式别名优先于模糊匹配 —— 0.8 的相似度是启发式，不该承担「同一人」的判断；
# 走模糊匹配也照样会出现在导入报告里，不静默。
PLAYER_NAME_ALIASES = {
    '欧阳': '欧阳翦',
}


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


def find_or_create_player(name, jersey_number=None, position=None, allow_create=True):
    """查找或创建球员，优先精确匹配，然后模糊匹配。

    `allow_create=False` 时**不创建**新球员 —— 找不到就返回 (None, False)，
    由调用方记录成「未知姓名」并跳过。
    这条保护是 Phase R3 加的：旧版会为解析出的乱码名字凭空建球员
    （实测造出过 '齐佳王佳帅'、'孙世铎'、'子非陈' 三个人）。

    返回 (player, is_new)
    """
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

    # 2. 显式别名 —— 业务方确认过的「同一个人」
    alias_target = PLAYER_NAME_ALIASES.get(name)
    if alias_target:
        player = Player.query.filter_by(name=alias_target).first()
        if player:
            _FUZZY_MATCHES.append({
                'parsed': name, 'matched': player.name,
                'score': 1.0, 'kind': 'alias'
            })
            return player, False

    # 3. 模糊匹配
    fuzzy, fuzzy_score = _fuzzy_match_name(name)
    if fuzzy:
        _FUZZY_MATCHES.append({
            'parsed': name, 'matched': fuzzy.name,
            'score': round(fuzzy_score, 3), 'kind': 'fuzzy'
        })
        return fuzzy, False

    # 4. 创建新球员
    if not allow_create:
        return None, False

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

    # ⚠️ 不要再逐个 setattr 统计字段 —— 那些字段是 property proxy，
    # 对投手字段赋值会给**野手**凭空造出空的 pitcher_profiles 行
    # （旧版留下 21 个空壳行）。apply_player_type 已经建好了该建的档案。

    db.session.add(player)
    return player, True  # 新创建


# 模糊匹配记录（导入报告里会列出来，便于人工复核）
_FUZZY_MATCHES = []
_UNKNOWN_NAMES = []


def import_game_record(result, dry_run=False, replace=False,
                       allow_new_players=False, commit=True):
    """导入单场比赛的所有数据。

    写入语义（Phase R3）：
        只写 `game_records`，统计档案一律由 `rebuild_player_stats()` 从
        game_records 重算 —— 不做增量 +/-。
        增量写法（`player.at_bats_total += ...`）会与「档案 = SUM(game_records)」
        这条核心不变量冲突，且一旦历史上有漂移就会越积越错。

    `replace=True`（覆盖模式）：
        先删掉这场（game_date + opponent）已有的记录，再写入新解析的数据。
        没有这个模式的话，去重逻辑会命中旧记录直接跳过 —— 新解析出的
        更正后的值**永远写不进去**（实测：重导 17 份 PDF，imported 0 / skipped 212）。
        覆盖模式把「重导」从「加了几条」变成「修正了数据」。

    `allow_new_players=False`（默认）：
        解析出的姓名在队里找不到时**不建新球员**，记入 unknown_names 并跳过。
        旧版会为乱码名字凭空建球员（实测造出 '齐佳王佳帅'/'孙世铎'/'子非陈'）。

    `commit=False`：
        不在本场结束时提交，交给调用方统一提交（见 `import_all_pdfs` 的
        `atomic=True`）。规范 §28 要求一次批量导入是**一个事务**：
        BEGIN → 写全部场次 → COMMIT，任何一步失败整体 ROLLBACK，
        而不是「场 1 提交、场 2 提交、场 3 失败」这种半截状态。
    """
    game_date = result.get('game_date')
    opponent = result.get('opponent', '未知')
    filepath = result.get('filepath', '')
    if not game_date:
        return {'status': 'skip', 'reason': '无比赛日期'}
    game_date_obj = datetime.strptime(game_date, '%Y-%m-%d').date()
    fuzzy_start = len(_FUZZY_MATCHES)
    imported_batting = 0
    imported_pitching = 0
    skipped = 0
    replaced = 0
    new_players = []
    unknown_names = []
    details = []

    # ── 覆盖模式：先删掉这场已有的记录 ──
    if replace and not dry_run:
        old_records = GameRecord.query.filter_by(
            game_date=game_date_obj, opponent=opponent).all()
        replaced = len(old_records)
        for record in old_records:
            db.session.delete(record)
        db.session.flush()

    # ── 打击数据 ──
    for batter in result.get('my_team_batting', []):
        name = batter['name']
        jersey = batter.get('jersey_number')
        player = None
        if not dry_run:
            player, is_new = find_or_create_player(
                name, jersey, batter.get('position'), allow_create=allow_new_players)
            if player is None:
                unknown_names.append({'name': name, 'kind': 'batting',
                                      'file': os.path.basename(filepath)})
                skipped += 1
                continue
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
                # 守备失误 / 牺牲打 —— Phase R4 才有数据源（审计 #11）
                sacrifice_flys=batter.get('sacrifice_flys', 0) or 0,
                sacrifice_hits=batter.get('sacrifice_hits', 0) or 0,
                errors_fielding=batter.get('errors_fielding', 0) or 0,
            )
            db.session.add(record)
        imported_batting += 1
        details.append(f"  打击: {name} AB={batter['at_bats']} H={batter['hits']} RBI={batter['rbi']}")

    # ── 投球数据 ──
    for pitcher in result.get('my_team_pitching', []):
        name = pitcher['name']
        jersey = pitcher.get('jersey_number')
        if not dry_run:
            player, is_new = find_or_create_player(
                name, jersey, 'P', allow_create=allow_new_players)
            if player is None:
                unknown_names.append({'name': name, 'kind': 'pitching',
                                      'file': os.path.basename(filepath)})
                skipped += 1
                continue
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
                wild_pitches=pitcher.get('wild_pitches', 0),
                win=pitcher['win'],
                loss=pitcher['loss'],
                save=pitcher['save'],
            )
            db.session.add(record)
        imported_pitching += 1
        details.append(
            f"  投手: {name} IP={pitcher['innings_pitched']} ER={pitcher['earned_runs']}")

    if not dry_run:
        db.session.flush()
        # ── 档案统一从 game_records 重算 ──
        # 涉及这场比赛的全部球员（覆盖模式下被删掉记录的球员也算在内）
        touched_ids = set()
        for row in db.session.query(GameRecord.player_id).filter(
                GameRecord.game_date == game_date_obj,
                GameRecord.opponent == opponent).all():
            touched_ids.add(row[0])
        for pid in touched_ids:
            rebuild_player_stats(pid)
        if commit:
            db.session.commit()
        else:
            # 交给调用方统一提交（规范 §28：一个批次一个事务）
            db.session.flush()

    # 本次导入产生的模糊匹配（打上来源文件，便于报告里定位）
    fuzzy = []
    for match in _FUZZY_MATCHES[fuzzy_start:]:
        entry = dict(match)
        entry['file'] = os.path.basename(filepath)
        fuzzy.append(entry)

    return {
        'status': 'ok',
        'batting': imported_batting,
        'pitching': imported_pitching,
        'skipped': skipped,
        'replaced': replaced,
        'new_players': new_players,
        'unknown_names': unknown_names,
        'fuzzy_matches': fuzzy,
        'details': details,
        'date': game_date,
        'opponent': opponent
    }


def import_all_pdfs(dry_run=False, replace=False, allow_new_players=False,
                    atomic=True, subdir=None):
    """导入 data/ 目录下所有 PDF 文件。

    replace=True → 覆盖模式：每场先删旧记录再写新解析的数据。
    allow_new_players=True → 允许为未知姓名建新球员（默认关）。
    atomic=True（默认）→ 整个批次是**一个事务**：
        规范 §28「PDF Import 事务模型」要求 BEGIN → 写全部场次 → COMMIT，
        任何一步失败就整体 ROLLBACK，不留「前 5 场已提交、第 6 场失败」的半截状态。
        atomic=False 保留旧的「每场各提交一次」行为（仅供调试对照）。
    subdir='2026' → 只导入 data/2026/ 下的 PDF。
        新增赛季只想增量导入时用 —— 避免把历史赛季全部删了重写一遍
        （覆盖模式是按「日期+对手」删的，全量重导会让所有 record id 变）。
    """
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if subdir:
        data_dir = os.path.join(data_dir, subdir)
    if not os.path.exists(data_dir):
        print(f"数据目录不存在: {data_dir}")
        return []

    results = []
    pdf_files = []
    for root, _dirs, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, f))

    pdf_files.sort()
    print(f"找到 {len(pdf_files)} 个 PDF 文件")
    if atomic and not dry_run:
        print("事务模式: 整个批次一次提交（失败整体回滚）")

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
                if atomic and not dry_run:
                    raise RuntimeError(f'{filename} 解析失败: {parsed["error"]}')
                continue

            print(f"  日期: {parsed.get('game_date')}")
            print(f"  对手: {parsed.get('opponent')}")
            print(f"  打击数据: {len(parsed.get('my_team_batting', []))} 条")
            print(f"  投手数据: {len(parsed.get('my_team_pitching', []))} 条")

            if not parsed.get('my_team_batting') and not parsed.get('my_team_pitching'):
                print("  跳过: 无有效数据")
                results.append({'file': filename, 'status': 'skip', 'reason': '无有效数据'})
                continue

            import_result = import_game_record(
                parsed, dry_run=dry_run, replace=replace,
                allow_new_players=allow_new_players,
                commit=not (atomic and not dry_run))

            for detail in import_result.get('details', []):
                print(detail)

            if import_result['status'] == 'ok':
                print(f"  导入成功: 打击 {import_result['batting']} 条, 投手 {import_result['pitching']} 条")
                if import_result.get('replaced'):
                    print(f"  覆盖(先删旧记录): {import_result['replaced']} 条")
                if import_result['new_players']:
                    print(f"  新球员: {', '.join(import_result['new_players'])}")
                if import_result.get('unknown_names'):
                    names = ', '.join(u['name'] for u in import_result['unknown_names'])
                    print(f"  ⚠ 未知姓名(已跳过, 未建球员): {names}")
                if import_result.get('fuzzy_matches'):
                    for m in import_result['fuzzy_matches']:
                        kind = '别名(业务方已确认同一人)' if m.get('kind') == 'alias' else '模糊匹配'
                        print(f"  ⚠ {kind}: PDF 里的「{m['parsed']}」并入了"
                              f"「{m['matched']}」(相似度 {m['score']})")
                if import_result['skipped']:
                    print(f"  跳过(重复/未知): {import_result['skipped']} 条")

            results.append({
                'file': filename,
                **import_result
            })

        except Exception as e:
            print(f"  异常: {e}")
            traceback.print_exc()
            results.append({'file': filename, 'status': 'error', 'error': str(e)})
            if atomic and not dry_run:
                # 规范 §28：整体回滚，不留半截状态
                db.session.rollback()
                print(f"\n✗ 批次失败，已回滚全部改动（{len(pdf_files)} 份 PDF 一次提交）")
                raise

    # ── 一次提交（原子模式）──
    if atomic and not dry_run:
        db.session.commit()
        print(f"\n✓ 整个批次已提交（{len(pdf_files)} 份 PDF 一个事务）")

    # 汇总
    total_batting = sum(r.get('batting', 0) for r in results)
    total_pitching = sum(r.get('pitching', 0) for r in results)
    total_skipped = sum(r.get('skipped', 0) for r in results)
    total_replaced = sum(r.get('replaced', 0) for r in results)
    total_errors = sum(1 for r in results if r.get('status') == 'error')
    all_new = set()
    all_unknown = {}
    all_fuzzy = {}
    for r in results:
        all_new.update(r.get('new_players', []))
        for item in r.get('unknown_names', []):
            all_unknown.setdefault(item['name'], set()).add(item['file'])
        for item in r.get('fuzzy_matches', []):
            all_fuzzy.setdefault((item['parsed'], item['matched']), set()).add(item['file'])

    print(f"\n{'='*60}")
    print("导入完成！")
    print(f"  PDF 文件: {len(pdf_files)}")
    print(f"  打击记录: {total_batting}")
    print(f"  投手记录: {total_pitching}")
    if total_replaced:
        print(f"  覆盖(先删旧记录): {total_replaced} 条")
    print(f"  跳过(重复/未知): {total_skipped}")
    print(f"  错误: {total_errors}")
    print(f"  新球员: {len(all_new)}")
    if all_new:
        print(f"  新球员列表: {', '.join(sorted(all_new))}")
    if all_unknown:
        print(f"  ⚠ 未知姓名 {len(all_unknown)} 个（已跳过，未建球员）：")
        for name in sorted(all_unknown):
            print(f"      {name}  <- {', '.join(sorted(all_unknown[name]))}")
    if all_fuzzy:
        alias_items = {k: v for k, v in all_fuzzy.items()
                       if k[0] in PLAYER_NAME_ALIASES}
        fuzzy_items = {k: v for k, v in all_fuzzy.items()
                       if k[0] not in PLAYER_NAME_ALIASES}
        if alias_items:
            print(f"  ⚠ 别名合并 {len(alias_items)} 处（业务方已确认是同一个人）：")
            for (parsed, matched), files in sorted(alias_items.items()):
                print(f"      「{parsed}」 -> 「{matched}」  <- {', '.join(sorted(files))}")
        if fuzzy_items:
            print(f"  ⚠ 模糊匹配 {len(fuzzy_items)} 处（PDF 里的名字并入了队里的人）：")
            for (parsed, matched), files in sorted(fuzzy_items.items()):
                print(f"      「{parsed}」 -> 「{matched}」  <- {', '.join(sorted(files))}")
    print(f"{'='*60}")

    return results


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    replace = '--replace' in sys.argv
    allow_new = '--allow-new-players' in sys.argv
    atomic = '--no-atomic' not in sys.argv
    # --dir 2026 → 只导入 data/2026/（新增赛季做增量导入时用）
    subdir = None
    if '--dir' in sys.argv:
        _i = sys.argv.index('--dir')
        if _i + 1 < len(sys.argv):
            subdir = sys.argv[_i + 1]
    if dry_run:
        print("=== 预览模式（不写入数据库）===")
    if replace:
        print("=== 覆盖模式（每场先删旧记录再写入）===")
    if not atomic:
        print("=== 非原子模式（每场各提交一次，仅调试用）===")
    if subdir:
        print(f"=== 只导入 data/{subdir}/ 下的 PDF ===")

    with app.app_context():
        init_positions()
        import_all_pdfs(dry_run=dry_run, replace=replace,
                        allow_new_players=allow_new, atomic=atomic,
                        subdir=subdir)
