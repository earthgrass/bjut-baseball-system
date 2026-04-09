"""
PDF 比赛记录解析模块
自动从 PDF 文件中提取球员打击和投手数据
"""

import re
import os
import pdfplumber
from datetime import datetime


MY_TEAM_KEYWORDS = ['北京工业大学', '北京工业', '北京⼯业']

# PDF 中常见的不规范字符映射 → 规范字符
# 康熙部首 (U+2F00-2FDF) 和 CJK 部件补充 (U+2E80-2EFF) → 标准汉字
_CHAR_MAP = {
    # CJK 部件补充 (U+2E80-2EFF)
    '\u2EA0': '民',  # ⺠ → 民
    '\u2ED9': '韦',  # ⻙ → 韦
    '\u2EDC': '飞',  # ⻜ → 飞
    '\u2EE2': '马',  # ⻢ → 马
    '\u2EE9': '黄',  # ⻩ → 黄
    '\u2EEC': '齐',  # ⻬ → 齐
    '\u2EF0': '龙',  # ⻰ → 龙
    # 康熙部首 (U+2F00-2FDF)
    '\u2F00': '一',  # ⼀ → 一
    '\u2F08': '人',  # ⼈ → 人
    '\u2F12': '力',  # ⼒ → 力
    '\u2F20': '士',  # ⼠ → 士
    '\u2F24': '大',  # ⼤ → 大
    '\u2F26': '子',  # ⼦ → 子
    '\u2F2F': '工',  # ⼯ → 工
    '\u2F3C': '心',  # ⼼ → 心
    '\u2F42': '文',  # ⽂ → 文
    '\u2F51': '毛',  # ⽑ → 毛
    '\u2F54': '水',  # ⽔ → 水
    '\u2F5C': '牛',  # ⽜ → 牛
    '\u2F62': '甘',  # ⽢ → 甘
    '\u2F65': '田',  # ⽥ → 田
    '\u2F69': '白',  # ⽩ → 白
    '\u2F6F': '石',  # ⽯ → 石
    '\u2F7B': '羽',  # ⽻ → 羽
    '\u2FA0': '辰',  # ⾠ → 辰
    '\u2FA2': '邑',  # ⾢ → 邑
    '\u2FA6': '金',  # ⾦ → 金
    '\u2FAC': '雨',  # ⾬ → 雨
    '\u2FAE': '非',  # ⾮ → 非
    '\u2FB8': '首',  # ⾸ → 首
    '\u2FBC': '高',  # ⾼ → 高
}


def _normalize_text(text):
    """将 PDF 中的特殊 Unicode 字符替换为常用汉字"""
    result = []
    for ch in text:
        if ch in _CHAR_MAP:
            result.append(_CHAR_MAP[ch])
        else:
            result.append(ch)
    return ''.join(result)


def parse_pdf(filepath):
    """
    解析单个 PDF 文件，返回结构化的比赛数据。

    返回格式:
    {
        'filepath': str,
        'game_date': str (YYYY-MM-DD),
        'opponent': str,
        'my_team_batting': [
            {
                'name': str,
                'jersey_number': str or None,
                'position': str,
                'at_bats': int, 'runs': int, 'hits': int,
                'rbi': int, 'walks': int, 'strikeouts': int,
                'doubles': int, 'triples': int, 'home_runs': int,
                'total_bases': int, 'stolen_bases': int, 'caught_stealing': int,
                'hit_by_pitch': int
            },
            ...
        ],
        'my_team_pitching': [
            {
                'name': str,
                'jersey_number': str or None,
                'innings_pitched': float,
                'hits_allowed': int, 'runs_allowed': int, 'earned_runs': int,
                'walks_allowed': int, 'strikeouts': int, 'home_runs_allowed': int,
                'pitches': int, 'strikes': int, 'batters_faced': int,
                'hit_by_pitch_allowed': int,
                'win': bool, 'loss': bool, 'save': bool
            },
            ...
        ]
    }
    """
    result = {
        'filepath': filepath,
        'game_date': None,
        'opponent': None,
        'my_team_batting': [],
        'my_team_pitching': []
    }

    try:
        pdf = pdfplumber.open(filepath)
        full_text = ''
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + '\n'
        pdf.close()
    except Exception as e:
        result['error'] = f'读取PDF失败: {e}'
        return result

    if not full_text.strip():
        result['error'] = 'PDF内容为空'
        return result

    # 规范化 PDF 中的特殊 Unicode 字符
    full_text = _normalize_text(full_text)

    # 从文件名提取对手名和日期作为备用
    filename = os.path.basename(filepath)
    result['opponent'] = _parse_opponent_from_filename(filename)
    result['game_date'] = _parse_game_date(full_text) or _parse_date_from_filename(filename)

    # 确定我方队伍在 BATTING/PITCHING 表中的显示名
    my_team_display = _get_my_team_display_name(full_text)

    # 解析打击数据
    result['my_team_batting'] = _parse_batting(full_text, my_team_display)

    # 解析投手数据
    result['my_team_pitching'] = _parse_pitching(full_text, my_team_display)

    # 解析附加信息
    extras = _parse_extras(full_text, my_team_display)
    _merge_extras(result['my_team_batting'], extras)

    # 解析投手附加信息
    pitching_extras = _parse_pitching_extras(full_text, my_team_display)
    _merge_pitching_extras(result['my_team_pitching'], pitching_extras)

    return result


def _parse_game_date(text):
    """从 PDF 文本中提取比赛日期"""
    match = re.search(r'(?:Home|Away)\s+\w+\s+(\w+\s+\d{1,2},\s*\d{4})', text)
    if match:
        date_str = match.group(1).strip()
        try:
            dt = datetime.strptime(date_str, '%B %d, %Y')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def _parse_opponent_from_filename(filename):
    """从文件名提取对手名
    格式: 北京工业大学_vs_北京交通大学_Nov_16_2024(2).pdf
    或: 对外经济贸易大学_vs_北京工业大学_Apr_1_2023.pdf
    """
    name = filename.replace('.pdf', '')
    parts = name.split('_vs_')
    if len(parts) >= 2:
        team1 = parts[0]
        # 第二部分可能包含日期: 北京交通大学_Nov_16_2024(2)
        team2 = parts[1].split('_')[0] if '_' in parts[1] else parts[1]
        if '北京工业' in team1:
            return team2
        elif '北京工业' in team2:
            return team1
    return None


def _parse_date_from_filename(filename):
    """从文件名提取日期作为备用"""
    # Nov_16_2024 or Apr_1_2023
    match = re.search(r'(\w+)_(\d{1,2})_(\d{4})', filename)
    if match:
        month_str, day_str, year_str = match.groups()
        try:
            dt = datetime.strptime(f'{month_str} {day_str}, {year_str}', '%b %d, %Y')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def _get_my_team_display_name(full_text):
    """获取我方队伍在 BATTING 表头中的显示名"""
    # BATTING 表头格式: "北京工业大学 AB R H RBI BB SO" 或 "北京工业⼤学 AB R H RBI BB SO"
    # 注意 PDF 中的"业"可能是特殊字符 ⼯业 vs ⼯业
    for line in full_text.split('\n'):
        line_stripped = line.strip()
        # 找包含我方关键词的 BATTING 表头行
        if 'AB' in line and any(kw in line_stripped for kw in MY_TEAM_KEYWORDS):
            # 提取表头前的队伍名
            match = re.match(r'(.+?)\s+AB\s+R\s+H', line_stripped)
            if match:
                return match.group(1).strip()

    # 降级：直接用简称
    return '北京工业'


def _normalize_name(name):
    """规范化球员姓名：去除多余空格和特殊字符"""
    # 去掉 CR: 前缀（代跑/代打标记）
    name = re.sub(r'^CR:\s*', '', name)
    # 移除零宽空格等特殊字符
    name = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', name)
    # 将多个空格合并为一个，然后去掉首尾空格
    name = re.sub(r'\s+', '', name)

    # Fix known merged-line edge cases (PDF有时将两个球员行合并为一行)
    if '⻬佳' in name:
        # CR:⻬佳#37000000王佳帅 → 齐佳
        # ⻬佳#37100001子⾮陈 → 齐佳 (second player on same line)
        name = '齐佳'
    elif '聂千盛(C)121110博⽂杨' in name or '聂千盛(C)' in name:
        # 聂千盛(C)121110博⽂杨 → 聂千盛 (second: 博⽂杨)
        name = '聂千盛'
    elif '博⽂杨' in name or '博文杨' in name:
        name = '博文杨'
    elif '子⾮陈' in name or '子非陈' in name:
        name = '子非陈'

    # Remove trailing numbers and special chars
    name = re.sub(r'#\d+', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\d+$', '', name)

    return name.strip()


def _parse_batting(text, my_team_display):
    """解析 BATTING 段落中我方球员的打击数据"""
    batting_data = []
    lines = text.split('\n')

    in_batting = False
    my_team_section = False

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # 检测 BATTING 标记
        if line_stripped == 'BATTING':
            in_batting = True
            continue

        # 检测 PITCHING 标记 → 结束 BATTING
        if line_stripped == 'PITCHING':
            in_batting = False
            continue

        if not in_batting:
            continue

        # 表头行: "北京工业大学 AB R H RBI BB SO  北京交通大学 AB R H RBI BB SO"
        if 'AB' in line and 'RBI' in line:
            # 判断我方在哪一侧
            left_header = line.split('AB')[0].strip()
            if my_team_display and any(kw in left_header for kw in MY_TEAM_KEYWORDS):
                my_team_section = 'left'
            else:
                my_team_section = 'right'
            continue

        # Totals 行 → 跳过
        if line_stripped.startswith('Totals'):
            continue

        # 尝试解析球员行
        if my_team_section == 'left':
            player = _parse_left_player(line_stripped)
            # 正常解析失败时，尝试拆分合并行
            if not player:
                for sub in _split_merged_batting_line(line_stripped):
                    player = _parse_left_player(sub)
                    if player:
                        batting_data.append(player)
                        player = None  # 继续尝试解析后半段
                continue
        elif my_team_section == 'right':
            player = _parse_right_player(line_stripped)
            if not player:
                for sub in _split_merged_batting_line(line_stripped):
                    player = _parse_right_player(sub)
                    if player:
                        batting_data.append(player)
                        player = None
                continue
        else:
            continue

        if player:
            batting_data.append(player)

    return batting_data


def _split_merged_batting_line(line):
    """检测并拆分合并到同一行的两个球员数据。

    PDF 有时将两行压缩为一行，例如：
      聂千盛 (C) 1 2 1 1 1 0 博⽂杨 #26 (3B) 1 1 1 0 0 0
      CR: ⻬佳 #37 0 0 0 0 0 0 王佳帅 #35 (C) 1 0 0 0 1 1
    """
    # 匹配 "6个数字" 后面紧跟 非数字非空格 的内容（即第二个球员名字开头）
    boundary = re.compile(
        r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+'
    )
    matches = list(boundary.finditer(line))
    if len(matches) >= 2:
        # 在第一组6个数字结束后切分
        split_pos = matches[0].end()
        return [line[:split_pos].strip(), line[split_pos:].strip()]
    if len(matches) == 1:
        # 只有一组6个数字——检查切分点后面是否像球员名
        split_pos = matches[0].end()
        remainder = line[split_pos:].strip()
        # 如果后面包含 #数字 或 (位置) 模式，说明有第二个球员
        if remainder and (re.search(r'#\d+', remainder) or re.search(r'\([A-Z0-9]+\)', remainder)):
            return [line[:split_pos].strip(), remainder]
    return [line]


def _parse_left_player(line):
    """解析左侧队伍的球员行
    格式1 (有背号): 张家昊 #73 (CF) 5 3 3 3 0 1
    格式2 (无背号): 仇志豪 (2B, P, C) 2 1 1 0 0 0
    格式3 (CR无位置): CR: ⻬佳 #37 0 0 0 0 0 0
    """
    # 去掉 CR: 前缀（代跑/代打标记）
    line_clean = re.sub(r'^CR:\s*', '', line.strip())

    # 有背号格式: 姓名 #数字 (位置) 数据
    match = re.match(
        r'(.+?)\s*#(\d+)\s*\(([^)]*)\)\s+'
        r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
        line_clean
    )
    if match:
        return _make_batting_record(
            name=match.group(1), jersey_number=match.group(2),
            position=match.group(3),
            ab=match.group(4), r=match.group(5), h=match.group(6),
            rbi=match.group(7), bb=match.group(8), so=match.group(9)
        )

    # 有背号但无位置: 姓名 #数字 数据
    match = re.match(
        r'(.+?)\s*#(\d+)\s+'
        r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
        line_clean
    )
    if match:
        name = _normalize_name(match.group(1))
        if name.lower() in ('totals', 'total', ''):
            return None
        return _make_batting_record(
            name=match.group(1), jersey_number=match.group(2),
            position='',
            ab=match.group(3), r=match.group(4), h=match.group(5),
            rbi=match.group(6), bb=match.group(7), so=match.group(8)
        )

    # 无背号格式: 姓名 (位置) 数据
    match = re.match(
        r'(.+?)\s*\(([^)]*)\)\s+'
        r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
        line_clean
    )
    if match:
        return _make_batting_record(
            name=match.group(1), jersey_number=None,
            position=match.group(2),
            ab=match.group(3), r=match.group(4), h=match.group(5),
            rbi=match.group(6), bb=match.group(7), so=match.group(8)
        )

    return None


def _make_batting_record(name, jersey_number, position, ab, r, h, rbi, bb, so):
    """创建标准化的打击数据字典"""
    return {
        'name': _normalize_name(name),
        'jersey_number': jersey_number,
        'position': position.split(',')[0].strip(),
        'at_bats': int(ab),
        'runs': int(r),
        'hits': int(h),
        'rbi': int(rbi),
        'walks': int(bb),
        'strikeouts': int(so),
        'doubles': 0, 'triples': 0, 'home_runs': 0,
        'total_bases': 0, 'stolen_bases': 0,
        'caught_stealing': 0, 'hit_by_pitch': 0
    }


def _parse_right_player(line):
    """解析右侧队伍的球员行（两列数据在同一行）
    需要先跳过左侧队伍的数据，再解析右侧
    """
    # 尝试匹配左侧数据并跳过：name #num (pos) 6个数字
    left_pattern = re.compile(
        r'(.+?)\s*#\d+\s*\([^)]*\)\s+'
        r'\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s*'
    )
    match = left_pattern.match(line)
    if match:
        remaining = line[match.end():]
        return _parse_left_player(remaining)

    # 无背号格式：name (pos) 6个数字
    left_pattern2 = re.compile(
        r'(.+?)\s*\([^)]*\)\s+'
        r'\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s*'
    )
    match = left_pattern2.match(line)
    if match:
        remaining = line[match.end():]
        return _parse_left_player(remaining)

    # 没有左侧数据，整行就是右侧
    return _parse_left_player(line)


def _parse_pitching(text, my_team_display):
    """解析 PITCHING 段落中我方投手数据"""
    pitching_data = []
    lines = text.split('\n')

    in_pitching = False
    my_team_section = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if line_stripped == 'PITCHING':
            in_pitching = True
            continue

        # Scorekeeping 行 → 结束 PITCHING
        if 'Scorekeeping' in line_stripped:
            in_pitching = False
            continue

        if not in_pitching:
            continue

        # 表头行: "北京工业大学 IP H R ER BB SO HR  北京交通大学 IP H R ER BB SO HR"
        if 'IP' in line and 'ER' in line:
            left_header = line.split('IP')[0].strip()
            if my_team_display and any(kw in left_header for kw in MY_TEAM_KEYWORDS):
                my_team_section = 'left'
            else:
                my_team_section = 'right'
            continue

        # Totals 行 → 跳过
        if line_stripped.startswith('Totals'):
            continue

        # 尝试解析投手行
        if my_team_section == 'left':
            pitcher = _parse_left_pitcher(line_stripped)
        elif my_team_section == 'right':
            pitcher = _parse_right_pitcher(line_stripped)
        else:
            continue

        if pitcher:
            pitching_data.append(pitcher)

    return pitching_data


def _parse_left_pitcher(line):
    """解析左侧投手行
    格式1 (有背号): 韩登越 #30 2.0 2 3 0 2 1 0
    格式2 (无背号): 韩登越 3.0 1 0 0 1 5 0
    """
    # 有背号
    match = re.match(
        r'(.+?)\s*#(\d+)\s+'
        r'(\d+\.?\d*)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
        line
    )
    if match:
        return {
            'name': _normalize_name(match.group(1)),
            'jersey_number': match.group(2),
            'innings_pitched': float(match.group(3)),
            'hits_allowed': int(match.group(4)),
            'runs_allowed': int(match.group(5)),
            'earned_runs': int(match.group(6)),
            'walks_allowed': int(match.group(7)),
            'strikeouts': int(match.group(8)),
            'home_runs_allowed': int(match.group(9)),
            'pitches': 0, 'strikes': 0, 'batters_faced': 0,
            'hit_by_pitch_allowed': 0,
            'win': False, 'loss': False, 'save': False
        }

    # 无背号
    match = re.match(
        r'(.+?)\s+'
        r'(\d+\.?\d*)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
        line
    )
    if match:
        name = _normalize_name(match.group(1))
        # 排除 "Totals" 等非球员名
        if name.lower() in ('totals', 'total', ''):
            return None
        return {
            'name': name,
            'jersey_number': None,
            'innings_pitched': float(match.group(2)),
            'hits_allowed': int(match.group(3)),
            'runs_allowed': int(match.group(4)),
            'earned_runs': int(match.group(5)),
            'walks_allowed': int(match.group(6)),
            'strikeouts': int(match.group(7)),
            'home_runs_allowed': int(match.group(8)),
            'pitches': 0, 'strikes': 0, 'batters_faced': 0,
            'hit_by_pitch_allowed': 0,
            'win': False, 'loss': False, 'save': False
        }

    return None


def _parse_right_pitcher(line):
    """解析右侧投手行：先跳过左侧数据"""
    # 有背号
    left_pattern = re.compile(
        r'(.+?)\s*#\d+\s+'
        r'\d+\.?\d*\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s*'
    )
    match = left_pattern.match(line)
    if match:
        remaining = line[match.end():]
        return _parse_left_pitcher(remaining)

    # 无背号
    left_pattern2 = re.compile(
        r'(.+?)\s+'
        r'\d+\.?\d*\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s*'
    )
    match = left_pattern2.match(line)
    if match:
        remaining = line[match.end():]
        return _parse_left_pitcher(remaining)

    return _parse_left_pitcher(line)


def _parse_extras(text, my_team_display):
    """解析附加信息行（我方队伍的 2B、HR、TB、SB、CS、HBP 等）

    策略：用我方球员名在 extras 文本中精确匹配，
    而不是依赖标签出现的顺序（因为两队数据会交错排列）
    """
    extras = {}

    lines = text.split('\n')
    # 收集 BATTING 的 Totals 行之后到 PITCHING 之前的所有文本
    in_extras_batting = False
    extras_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped == 'BATTING':
            in_extras_batting = False
            continue
        if stripped.startswith('Totals'):
            in_extras_batting = True
            continue
        if stripped == 'PITCHING':
            break
        if in_extras_batting and stripped:
            extras_lines.append(stripped)

    extras_text = ' '.join(extras_lines)

    # 收集所有标签段落（2B: ..., HR: ..., TB: ..., SB: ..., CS: ..., HBP: ...）
    # 同一个标签可能出现两次（我方和对方）
    tag_sections = _split_tag_sections(extras_text)

    # 对每种标签，选择正确的段落（我方数据）
    # 规律：2B、HR 我方在第一段；SB、CS 我方在最后一段
    # TB 因为交错严重，直接从基础数据计算
    for tag in ['2B', 'HR', 'TB', 'SB', 'CS', 'HBP']:
        sections = tag_sections.get(tag, [])
        if tag in ('2B', 'HR'):
            # 我方数据在第一段
            content = sections[0] if sections else ''
        elif tag in ('SB', 'CS'):
            # 我方数据在最后一段
            content = sections[-1] if sections else ''
        else:
            # TB 和 HBP：合并所有段落
            content = ', '.join(sections)

        if tag == 'TB':
            # TB 从基础数据计算更准确，跳过
            pass
        elif tag == '2B':
            extras['doubles'] = _extract_named_counts_from(content)
        elif tag == 'HR':
            extras['home_runs'] = _extract_named_counts_from(content)
        elif tag == 'SB':
            extras['stolen_bases'] = _extract_named_counts_from(content)
        elif tag == 'CS':
            extras['caught_stealing'] = _extract_named_counts_from(content)
        elif tag == 'HBP':
            extras['hit_by_pitch'] = _extract_named_counts_from(content)

    return extras


def _split_tag_sections(text):
    """将 extras 文本按标签分段。
    返回 {tag: [content1, content2, ...]}
    同一标签可能多次出现（我方和对方各一次）
    """
    result = {}
    # 匹配所有 "TAG: content" 模式
    pattern = r'(2B|HR|TB|SB|CS|HBP|LOB|E|BF|WP|P-S|W|L|S):\s*'
    positions = [(m.start(), m.group(1)) for m in re.finditer(pattern, text)]

    for i, (pos, tag) in enumerate(positions):
        # 内容从标签后开始，到下一个标签前结束
        content_start = text.index(':', pos) + 1
        if i + 1 < len(positions):
            content_end = positions[i + 1][0]
        else:
            content_end = len(text)
        content = text[content_start:content_end].strip().rstrip(',').strip()
        if tag not in result:
            result[tag] = []
        result[tag].append(content)

    return result


def _get_tag_content(text, tag):
    """获取指定标签的所有内容（合并多次出现），返回逗号分隔的字符串"""
    sections = _split_tag_sections(text)
    contents = sections.get(tag, [])
    return ', '.join(contents)


def _extract_named_counts_from(content):
    """从标签内容中提取所有 {名字: 计数} 对"""
    result = {}
    if not content:
        return result
    items = re.split(r',\s*', content)
    for item in items:
        item = item.strip()
        if not item:
            continue
        m = re.match(r'(.+?)\s+(\d+)$', item)
        if m:
            name = _normalize_name(m.group(1))
            count = int(m.group(2))
        else:
            name = _normalize_name(item)
            count = 1
        if name:
            result[name] = result.get(name, 0) + count
    return result


def _extract_named_values_from(content):
    """从标签内容中提取 {名字: 数值} 对（只取带明确数字的）"""
    result = {}
    if not content:
        return result
    items = re.split(r',\s*', content)
    for item in items:
        item = item.strip()
        if not item:
            continue
        m = re.match(r'(.+?)\s+(\d+)$', item)
        if m:
            name = _normalize_name(m.group(1))
            value = int(m.group(2))
            if name:
                result[name] = value
    return result


def _merge_extras(batting_data, extras):
    """将附加数据合并到打击数据中"""
    for player in batting_data:
        name = player['name']

        # 模糊匹配：在 extras 中查找匹配的名字
        matched = _find_matching_names(name, extras)

        for matched_name in matched:
            if matched_name in extras.get('doubles', {}):
                player['doubles'] = extras['doubles'][matched_name]
            if matched_name in extras.get('home_runs', {}):
                player['home_runs'] = extras['home_runs'][matched_name]
            if matched_name in extras.get('stolen_bases', {}):
                player['stolen_bases'] = extras['stolen_bases'][matched_name]
            if matched_name in extras.get('caught_stealing', {}):
                player['caught_stealing'] = extras['caught_stealing'][matched_name]
            if matched_name in extras.get('hit_by_pitch', {}):
                player['hit_by_pitch'] = extras['hit_by_pitch'][matched_name]

    # 对所有球员，从基础数据计算 total_bases（更可靠）
    for player in batting_data:
        singles = player['hits'] - player['doubles'] - player['triples'] - player['home_runs']
        singles = max(0, singles)  # 防止负数
        player['total_bases'] = singles + player['doubles'] * 2 + player['triples'] * 3 + player['home_runs'] * 4


def _find_matching_names(name, extras_dict):
    """在 extras 字典的所有子字典中查找匹配的名字"""
    matched = set()
    for extra_type in extras_dict.values():
        if isinstance(extra_type, dict):
            for extra_name in extra_type:
                if extra_name == name or name in extra_name or extra_name in name:
                    matched.add(extra_name)
    return matched


def _parse_pitching_extras(text, my_team_display):
    """解析投手附加信息：P-S（投球-好球）、BF（面对打者）、HBP、W/L/S"""
    extras = {}

    # 找到 PITCHING 之后，Scorekeeping 之前的所有文本
    lines = text.split('\n')
    pitching_extras_lines = []
    found_pitching_totals = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'PITCHING':
            found_pitching_totals = False
            continue
        # 在 PITCHING 段内，遇到第二个 Totals（我方或对方的）后开始收集
        if not found_pitching_totals and stripped.startswith('Totals'):
            # 检查此 Totals 是否在 PITCHING 段内
            prev_text = '\n'.join(lines[max(0, i-10):i])
            if 'PITCHING' in prev_text:
                found_pitching_totals = True
                continue
        if found_pitching_totals:
            if 'Scorekeeping' in stripped:
                break
            if stripped:
                pitching_extras_lines.append(stripped)

    extras_text = ' '.join(pitching_extras_lines)

    # P-S: 球员名 数字-数字, ...
    extras['pitches_strikes'] = _parse_ps(extras_text)
    # BF: 球员名 数字, ...
    extras['batters_faced'] = _extract_named_counts_from(_get_tag_content(extras_text, 'BF'))
    # HBP (投手): 球员名 数字, ...
    extras['hbp_allowed'] = _extract_named_counts_from(_get_tag_content(extras_text, 'HBP'))
    # W: 球员名
    extras['wins'] = _extract_wls(extras_text, 'W')
    # L: 球员名
    extras['losses'] = _extract_wls(extras_text, 'L')
    # S: 球员名 (save)
    extras['saves'] = _extract_wls(extras_text, 'S')

    return extras


def _parse_ps(text):
    """解析 P-S: 球员名 数字-数字, ..."""
    result = {}
    pattern = r'P-S:\s*(.+?)(?=\s*(?:W|L|S|WP|BF|HBP|E):|$)'
    match = re.search(pattern, text)
    if not match:
        return result

    content = match.group(1).strip()
    items = re.split(r',\s*', content)

    for item in items:
        item = item.strip()
        if not item:
            continue
        m = re.match(r'(.+?)\s+(\d+)-(\d+)$', item)
        if m:
            name = _normalize_name(m.group(1))
            pitches = int(m.group(2))
            strikes = int(m.group(3))
            if name:
                result[name] = {'pitches': pitches, 'strikes': strikes}

    return result


def _extract_wls(text, tag):
    """提取 W/L/S 标记的球员名"""
    result = set()
    # W: 球员名, L: 球员名
    pattern = rf'{tag}:\s*(.+?)(?=\s*(?:W|L|S|WP|BF|HBP|P-S|E):|$)'
    match = re.search(pattern, text)
    if not match:
        return result

    content = match.group(1).strip()
    # 按逗号分割，取第一个名字（可能有多个但通常只有一个）
    items = re.split(r',\s*', content)
    for item in items:
        name = _normalize_name(item.strip())
        if name:
            result.add(name)

    return result


def _merge_pitching_extras(pitching_data, extras):
    """将投手附加数据合并到投手数据中"""
    for pitcher in pitching_data:
        name = pitcher['name']

        # P-S
        if name in extras.get('pitches_strikes', {}):
            ps = extras['pitches_strikes'][name]
            pitcher['pitches'] = ps['pitches']
            pitcher['strikes'] = ps['strikes']

        # BF
        if name in extras.get('batters_faced', {}):
            pitcher['batters_faced'] = extras['batters_faced'][name]

        # HBP allowed
        if name in extras.get('hbp_allowed', {}):
            pitcher['hit_by_pitch_allowed'] = extras['hbp_allowed'][name]

        # W/L/S
        if name in extras.get('wins', set()):
            pitcher['win'] = True
        if name in extras.get('losses', set()):
            pitcher['loss'] = True
        if name in extras.get('saves', set()):
            pitcher['save'] = True
