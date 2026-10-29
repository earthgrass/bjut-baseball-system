"""
数据库清理脚本：修复名字、合并重复球员、重算统计
用法: python cleanup_db.py
"""

import io
import sys
import re
import unicodedata
from collections import defaultdict

# 修复 Windows 控制台编码
# ⚠️ 只在**直接运行**时做 —— 作为模块被 import 时劫持 sys.stdout 会破坏
# pytest 的输出捕获（与 import_pdfs.py 同一个坑，实测整个测试会话崩在 teardown）。
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

from app import app
from database import (db, Player, GameRecord, init_positions,
                      rebuild_player_stats)

# CJK 部首字符 → 标准汉字映射
#
# ⚠️ 这一段以前是**手写**的 239 条映射表，其中 U+2F0C 写成了 '门'
#    （部首表里根本没有「门」这个字，U+2F0C 是「冂」）。
#    多出来的这一条把**后面 200 多个映射全部顶错一位** ——
#    例如 U+2FB9「⾹」本该是「首」，却被换成「香」；
#    U+2FBA「⾺」本该是「馬」，却被换成「香」……
#    （ruff 的 F601 重复键检查把它翻了出来）
#
# 现在直接用 Unicode 的 NFKC 规范化 —— 那就是权威映射表，不会错位。
# 只有「部首写法 → 队里实际用的简体字」这四条需要人工覆盖。


def _build_cjk_radical_map():
    """Kangxi 部首(U+2F00–U+2FDF) + CJK 部首补充(U+2E80–U+2EF3) → 标准汉字。"""
    mapping = {}
    for cp in list(range(0x2E80, 0x2EF4)) + list(range(0x2F00, 0x2FE0)):
        ch = chr(cp)
        nfkc = unicodedata.normalize('NFKC', ch)
        if nfkc != ch:
            mapping[ch] = nfkc
    # 队里用的是简体字，这几个部首的规范写法是繁体，单独覆盖成简体
    mapping.update({
        '⾺': '马',   # 馬 → 马
        '⿈': '黄',   # 黃 → 黄
        '⿑': '齐',   # 齊 → 齐
        '⾨': '门',   # 門 → 门
    })
    return mapping


CJK_RADICAL_MAP = _build_cjk_radical_map()


NAME_FIXES = {
    'CR:⻬佳#37000000王佳帅': '齐佳',
    '⻬佳#37000000王佳帅': '齐佳',
    '聂千盛(C)121110博⽂杨': '聂千盛',
    '齐佳#37100001子⾮陈': '齐佳',
}


def normalize_cjk_name(name):
    """将 CJK 部首字符替换为标准汉字"""
    result = []
    for ch in name:
        if ch in CJK_RADICAL_MAP:
            result.append(CJK_RADICAL_MAP[ch])
        else:
            result.append(ch)
    return ''.join(result)


def cleanup():
    with app.app_context():
        init_positions()

        # ---- 1. Fix known bad names ----
        print('=== 修复已知错误名字 ===')
        players = Player.query.all()
        fixed_count = 0

        for player in players:
            new_name = player.name

            # Apply known name fixes
            for bad, good in NAME_FIXES.items():
                if bad in new_name:
                    new_name = good
                    break

            # Normalize CJK radicals
            new_name = normalize_cjk_name(new_name)

            # Remove residual junk
            new_name = re.sub(r'^CR:\s*', '', new_name)
            new_name = re.sub(r'#\d+', '', new_name)
            new_name = re.sub(r'\(.*?\)', '', new_name)
            new_name = re.sub(r'\d+$', '', new_name)
            new_name = new_name.strip()

            if new_name != player.name:
                print(f'  Fix: {player.name!r} -> {new_name!r}')
                player.name = new_name
                fixed_count += 1

        if fixed_count:
            db.session.commit()
            print(f'Fixed {fixed_count} names')
        else:
            print('  No name fixes needed')

        # ---- 2. Merge duplicate players ----
        print('\n=== 合并重复球员 ===')
        players = Player.query.all()
        name_to_players = defaultdict(list)
        for p in players:
            name_to_players[p.name].append(p)

        duplicates = {n: ps for n, ps in name_to_players.items() if len(ps) > 1}
        merged_count = 0
        touched_player_ids = set()

        for name, dup_players in duplicates.items():
            kept = dup_players[0]
            for dup in dup_players[1:]:
                # Move game records
                GameRecord.query.filter_by(player_id=dup.id).update({'player_id': kept.id})
                # Merge positions
                for pos in dup.positions:
                    if pos not in kept.positions:
                        kept.positions.append(pos)
                # Merge pitcher status
                if dup.is_pitcher:
                    kept._is_pitcher = True
                # Keep better jersey number
                if kept.jersey_number == '0' and dup.jersey_number != '0':
                    kept.jersey_number = dup.jersey_number
                if kept.primary_position in ('未指定', '', None):
                    kept.primary_position = dup.primary_position
                db.session.delete(dup)
                merged_count += 1
                touched_player_ids.add(kept.id)
                print(f'  Merge: {name} (keep #{kept.id}, remove #{dup.id})')

        if merged_count:
            db.session.commit()
            print(f'Merged {merged_count} duplicate players')
        else:
            print('  No duplicates found')

        # ---- 3. Recalculate stats ----
        # ⚠️ 合并球员后，累计档案（at_bats_total 等）不会自愈：
        #   被合并掉的球员的比赛记录改挂到了保留球员身上，但保留球员的档案
        #   仍然是合并前的旧值 —— 与 game_records 严重不符。
        #   `update_calculated_fields()` 只重算 AVG/SLG/OBP 这类**派生比值**，
        #   不动累计值，所以光调它是不够的（审计 #5）。
        #   正确做法：对受影响的球员从 game_records **重建**档案。
        print('\n=== 重算统计 ===')
        for pid in sorted(touched_player_ids):
            player = rebuild_player_stats(pid)
            if player is not None:
                print(f'  Rebuilt stats for #{pid} {player.name} '
                      f'(AB={player.at_bats_total} H={player.hits_total})')
        for p in Player.query.all():
            p.update_calculated_fields()
        db.session.commit()

        # ---- 4. Final report ----
        players = Player.query.all()
        records = GameRecord.query.count()
        print(f'\nAfter: {len(players)} players, {records} records')
        for p in sorted(players, key=lambda x: x.name):
            print(f'  {p.name} #{p.jersey_number} {p.primary_position} '
                  f'AVG={p.batting_average:.3f} H={p.hits_total} RBI={p.rbi_total}')


if __name__ == '__main__':
    cleanup()
