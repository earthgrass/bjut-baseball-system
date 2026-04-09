"""
数据库清理脚本：修复名字、合并重复球员、重算统计
用法: python cleanup_db.py
"""

import io
import sys
import re
import unicodedata
from collections import defaultdict
from datetime import datetime

# 修复 Windows 控制台编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

from app import app
from database import db, Player, GameRecord, Position, init_positions

# CJK 部首字符 → 标准汉字映射
CJK_RADICAL_MAP = {
    '\u2f00': '一', '\u2f01': '丨', '\u2f02': '丶', '\u2f03': '丿',
    '\u2f04': '乙', '\u2f05': '亅', '\u2f06': '二', '\u2f07': '亠',
    '\u2f08': '人', '\u2f09': '儿', '\u2f0a': '入', '\u2f0b': '八',
    '\u2f0c': '门', '\u2f0d': '冂', '\u2f0e': '冖', '\u2f0f': '冫',
    '\u2f10': '几', '\u2f11': '凵', '\u2f12': '刀', '\u2f13': '力',
    '\u2f14': '勹', '\u2f15': '匕', '\u2f16': '匚', '\u2f17': '匸',
    '\u2f18': '十', '\u2f19': '卜', '\u2f1a': '卩', '\u2f1b': '厂',
    '\u2f1c': '厶', '\u2f1d': '又', '\u2f1e': '口', '\u2f1f': '囗',
    '\u2f20': '土', '\u2f21': '士', '\u2f22': '夂', '\u2f23': '夊',
    '\u2f24': '夕', '\u2f25': '大', '\u2f26': '女', '\u2f27': '子',
    '\u2f28': '宀', '\u2f29': '寸', '\u2f2a': '小', '\u2f2b': '尢',
    '\u2f2c': '尸', '\u2f2d': '屮', '\u2f2e': '山', '\u2f2f': '巛',
    '\u2f30': '工', '\u2f31': '己', '\u2f32': '巾', '\u2f33': '干',
    '\u2f34': '幺', '\u2f35': '广', '\u2f36': '廴', '\u2f37': '廾',
    '\u2f38': '弋', '\u2f39': '弓', '\u2f3a': '彐', '\u2f3b': '彡',
    '\u2f3c': '彳', '\u2f3d': '心', '\u2f3e': '戈', '\u2f3f': '户',
    '\u2f40': '手', '\u2f41': '支', '\u2f42': '攴', '\u2f43': '文',
    '\u2f44': '斗', '\u2f45': '斤', '\u2f46': '方', '\u2f47': '无',
    '\u2f48': '日', '\u2f49': '曰', '\u2f4a': '月', '\u2f4b': '木',
    '\u2f4c': '欠', '\u2f4d': '止', '\u2f4e': '歹', '\u2f4f': '殳',
    '\u2f50': '毋', '\u2f51': '比', '\u2f52': '毛', '\u2f53': '氏',
    '\u2f54': '气', '\u2f55': '水', '\u2f56': '火', '\u2f57': '爪',
    '\u2f58': '父', '\u2f59': '爻', '\u2f5a': '爿', '\u2f5b': '片',
    '\u2f5c': '牙', '\u2f5d': '牛', '\u2f5e': '犬', '\u2f5f': '玄',
    '\u2f60': '玉', '\u2f61': '瓜', '\u2f62': '瓦', '\u2f63': '甘',
    '\u2f64': '生', '\u2f65': '用', '\u2f66': '田', '\u2f67': '疋',
    '\u2f68': '疒', '\u2f69': '癶', '\u2f6a': '白', '\u2f6b': '皮',
    '\u2f6c': '皿', '\u2f6d': '目', '\u2f6e': '矛', '\u2f6f': '矢',
    '\u2f70': '石', '\u2f71': '示', '\u2f72': '禸', '\u2f73': '禾',
    '\u2f74': '穴', '\u2f75': '立', '\u2f76': '竹', '\u2f77': '米',
    '\u2f78': '糸', '\u2f79': '缶', '\u2f7a': '网', '\u2f7b': '羊',
    '\u2f7c': '羽', '\u2f7d': '老', '\u2f7e': '而', '\u2f7f': '耒',
    '\u2f80': '耳', '\u2f81': '聿', '\u2f82': '肉', '\u2f83': '臣',
    '\u2f84': '自', '\u2f85': '至', '\u2f86': '臼', '\u2f87': '舌',
    '\u2f88': '舛', '\u2f89': '舟', '\u2f8a': '艮', '\u2f8b': '色',
    '\u2f8c': '艸', '\u2f8d': '虍', '\u2f8e': '虫', '\u2f8f': '血',
    '\u2f90': '行', '\u2f91': '衣', '\u2f92': '襾', '\u2f93': '見',
    '\u2f94': '角', '\u2f95': '言', '\u2f96': '谷', '\u2f97': '豆',
    '\u2f98': '豕', '\u2f99': '豸', '\u2f9a': '貝', '\u2f9b': '赤',
    '\u2f9c': '走', '\u2f9d': '足', '\u2f9e': '身', '\u2f9f': '車',
    '\u2fa0': '辛', '\u2fa1': '辰', '\u2fa2': '辵', '\u2fa3': '邑',
    '\u2fa4': '酉', '\u2fa5': '釆', '\u2fa6': '里', '\u2fa7': '金',
    '\u2fa8': '長', '\u2fa9': '門', '\u2faa': '阜', '\u2fab': '隶',
    '\u2fac': '隹', '\u2fad': '雨', '\u2fae': '靑', '\u2faf': '非',
    '\u2fb0': '面', '\u2fb1': '革', '\u2fb2': '韋', '\u2fb3': '韭',
    '\u2fb4': '音', '\u2fb5': '頁', '\u2fb6': '風', '\u2fb7': '飛',
    '\u2fb8': '食', '\u2fb9': '首', '\u2fba': '香', '\u2fbb': '馬',
    '\u2fbc': '骨', '\u2fbd': '高', '\u2fbe': '髟', '\u2fbf': '鬥',
    '\u2fc0': '鬯', '\u2fc1': '鬲', '\u2fc2': '鬼', '\u2fc3': '魚',
    '\u2fc4': '鳥', '\u2fc5': '鹵', '\u2fc6': '鹿', '\u2fc7': '麥',
    '\u2fc8': '麻', '\u2fc9': '黃', '\u2fca': '黍', '\u2fcb': '黑',
    '\u2fcc': '黹', '\u2fcd': '黽', '\u2fce': '鼎', '\u2fcf': '鼓',
    '\u2fd0': '鼠', '\u2fd1': '鼻', '\u2fd2': '齊', '\u2fd3': '齒',
    '\u2fd4': '龍', '\u2fd5': '龜', '\u2fd6': '龠',
    # CJK Supplementary Radical range
    '\u2e80': '二', '\u2e81': '人', '\u2e82': '人', '\u2e83': '人',
    '\u2e84': '人', '\u2e85': '人', '\u2e86': '人', '\u2e87': '人',
    '\u2e88': '人', '\u2e89': '人', '\u2e8a': '人', '\u2e8b': '人',
    '\u2e8c': '人', '\u2e8d': '人', '\u2e8e': '人', '\u2e8f': '人',
    # Common mistaken radicals seen in data
    '\u2f6a': '白', '\u2fc9': '黄', '\u2fd2': '齐', '\u2f66': '田',
    '\u2fbb': '马', '\u2f56': '火', '\u2f44': '斗', '\u2f27': '子',
}

# Known bad merged-line name patterns → correct name
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
                print(f'  Merge: {name} (keep #{kept.id}, remove #{dup.id})')

        if merged_count:
            db.session.commit()
            print(f'Merged {merged_count} duplicate players')
        else:
            print('  No duplicates found')

        # ---- 3. Recalculate stats ----
        print('\n=== 重算统计 ===')
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
