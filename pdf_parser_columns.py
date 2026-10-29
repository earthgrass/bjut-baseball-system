"""
PDF 解析器 —— 列坐标版
============================================================
为什么重写：
    旧版（`pdf_parser.py`）用 `page.extract_text()` 抽出的**纯文本**做正则切分。
    但这些 box score 是**左右两栏并排**的表格（左=我方，右=对方），
    `extract_text()` 会把两栏拍平成交错的一行：

        "2B: 张家昊, 韩登越 2, ..., HR: 张家昊, 2B: 马学赓, ..., HR: 赫旭, TB: ..."

    旧版只好用「2B/HR 我方在第一段、SB/CS 我方在最后段」这种**顺序猜测**来区分两队 ——
    必然出错，且错得静默（解析不报错，数据直接串到对面队）。

本版改用 `pdfplumber` 的**词坐标**：
    1. 把页面按视觉行聚类；
    2. 按 x 坐标切成左栏（我方）/ 右栏（对方），栏界取自表头里对方队名的 x；
    3. 表头给出每个数据列的 x 位置，数据行按「离哪个表头列最近」归属，
       不再依赖文本顺序。

产出格式与 `pdf_parser.parse_pdf()` **完全一致**，可无缝替换。

局数（IP）口径：
    这些 box score 用中文记法 —— 小数位表示「几分之一局」：.1 = 1/3 局，.2 = 2/3 局。
    规则由 PDF 自身的 Totals 行独立验证过（16/17 份逐份吻合，见
    `scripts/validate_ip_notation.py`）。
    本模块**输出原始字面值**（与 PDF 一致），换算在写入边界统一做。
"""
import os
import re

import pdfplumber

from pdf_parser import _normalize_text, _normalize_name, _CHAR_MAP  # noqa: F401


# 栏界：左右两栏的分界。优先从表头推导，推导不出来时退回页面中线。
def _derive_boundary(header_words):
    """从表头行推导对方栏的起始 x。

    表头形如：`北京工业大学 AB R H RBI BB SO  北京交通大学 AB R H RBI BB SO`
    对方队名的 x0 即右栏起点。
    """
    if not header_words:
        return None
    # 表头里除第一项（我方队名）以外的"中文词"即对方队名
    candidates = [w for w in header_words if re.search(r'[一-鿿]', w['text'])]
    if len(candidates) >= 2:
        return candidates[1]['x0']
    return None


def _extract_rows(page):
    """把页面按视觉行聚类，每行的词按 x0 排序。

    不用 `extract_text()` —— 它会把并排的两栏拍平。这里保留真实坐标。

    行聚类容差必须**小于行距**：这些 box score 有两种版式 ——
      2024/2025：行距 18pt、字高 10pt
      2023    ：行距 12pt、字高 10pt
    容差给到 2pt 就会把 2023 版式的相邻两行粘成一行（实测会）。
    这里用「字高的 40%」作为容差 —— 同行词 top 相同，不同行 top 差 ≥12pt。
    """
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    words.sort(key=lambda w: (w['top'], w['x0']))

    rows = []
    for w in words:
        height = w['bottom'] - w['top']
        tol = max(1.0, height * 0.4)
        placed = False
        for row in rows:
            if abs(w['top'] - row['top']) <= tol:
                row['words'].append(w)
                row['bottom'] = max(row['bottom'], w['bottom'])
                placed = True
                break
        if not placed:
            rows.append({'top': w['top'], 'bottom': w['bottom'], 'words': [w]})

    for row in rows:
        row['words'].sort(key=lambda w: w['x0'])
    rows.sort(key=lambda r: r['top'])
    return rows


def _row_text(row):
    return ' '.join(w['text'] for w in row['words'])


def _split_by_boundary(words, boundary):
    """按栏界把一行切成 (左栏词, 右栏词)。"""
    left, right = [], []
    for w in words:
        (left if w['x0'] < boundary else right).append(w)
    return left, right


def _numbers_in(words):
    """取出一个词序列里的纯数字词（保留 x 坐标）。"""
    return [w for w in words if re.match(r'^-?\d+(?:\.\d+)?$', w['text'])]


def _assign_by_x(numbers, columns):
    """把数据行里的数字按 x 归到表头列。

    columns: [(label, x_center), ...] 按 x 升序
    返回 {label: value}
    """
    result = {}
    if not columns:
        return result
    # 数字可能多于列数（PDF 把两行压成一行）—— 按顺序贪心分配
    for num in sorted(numbers, key=lambda w: w['x0']):
        best = None
        best_dist = None
        for label, cx in columns:
            dist = abs(num['x0'] + len(num['text']) / 2 - cx)
            if best_dist is None or dist < best_dist:
                best, best_dist = label, dist
        if best is None:
            continue
        if best in result:
            # 该列已经有值了 —— 说明有多余数字，跳过（不覆盖）
            continue
        result[best] = num['text']
    return result


def _header_columns(words, labels):
    """从表头词里取出每个标签的 x 中心。

    labels 是这个表应有的列名（顺序无关，按 x 定位）。
    """
    found = []
    for w in words:
        if w['text'] in labels:
            found.append((w['text'], w['x0'] + len(w['text']) / 2))
    return sorted(found, key=lambda t: t[1])


def _parse_player_block(words, columns, labels, name_stop_x=None):
    """解析一栏里的一个（或多个）球员数据块。

    columns: [(label, x_center)] 该表的列定义
    labels:  该栏应有的列名集合
    """
    if not words:
        return []

    # 姓名 / 背号 / 位置：在第一个数据列左边
    first_data_x = columns[0][1] if columns else 1e9
    head_words = [w for w in words if w['x0'] < first_data_x - 12]
    data_words = [w for w in words if w['x0'] >= first_data_x - 12]

    if not head_words:
        return []

    # 拆出背号与位置。
    # 位置字段可能被拆成多个词："(2B," + "P," + "2B)" → "(2B, P, 2B)"
    jersey = None
    position_parts = []
    in_position = False
    name_words = []
    for w in head_words:
        t = w['text']
        if in_position:
            position_parts.append(t)
            if t.endswith(')'):
                in_position = False
            continue
        if t.startswith('('):
            in_position = not t.endswith(')')
            position_parts.append(t)
        elif t.startswith('#'):
            jersey = t[1:]
        else:
            name_words.append(t)
    position = None
    if position_parts:
        raw = ' '.join(position_parts)
        if raw.startswith('(') and raw.endswith(')'):
            position = raw[1:-1]
        else:
            position = raw.strip('()')
    name = _normalize_name(' '.join(name_words))
    if not name:
        return []

    assigned = _assign_by_x(_numbers_in(data_words), columns)

    record = {'name': name, 'jersey_number': jersey, 'position': position}
    for label, key in labels.items():
        raw = assigned.get(label)
        if raw is None:
            record[key] = 0.0 if label == 'IP' else 0
        elif label == 'IP':
            record[key] = float(raw)
        else:
            record[key] = int(raw)
    return [record]


def _make_batting_record(name, jersey_number, position, values):
    """组装打击记录，并按规则算总垒数。"""
    doubles = values.get('doubles', 0)
    triples = values.get('triples', 0)
    home_runs = values.get('home_runs', 0)
    hits = values.get('hits', 0)
    singles = hits - doubles - triples - home_runs
    if singles < 0:
        singles = 0
    total_bases = singles + doubles * 2 + triples * 3 + home_runs * 4
    return {
        'name': name,
        'jersey_number': jersey_number,
        'position': position,
        'at_bats': values.get('at_bats', 0),
        'runs': values.get('runs', 0),
        'hits': hits,
        'rbi': values.get('rbi', 0),
        'walks': values.get('walks', 0),
        'strikeouts': values.get('strikeouts', 0),
        'doubles': doubles,
        'triples': triples,
        'home_runs': home_runs,
        'total_bases': total_bases,
        'stolen_bases': values.get('stolen_bases', 0),
        'caught_stealing': values.get('caught_stealing', 0),
        'hit_by_pitch': values.get('hit_by_pitch', 0),
        'sacrifice_flys': values.get('sacrifice_flys', 0),
        'sacrifice_hits': values.get('sacrifice_hits', 0),
        # 守备失误（Phase R4）—— 4 份 2025 年的 box score 里有 "E:" 标签，
        # 以前没人读它，所以 errors_fielding 永远是 0（审计 #11）。
        'errors_fielding': values.get('errors_fielding', 0),
    }


def _make_pitching_record(name, jersey_number, position, values):
    return {
        'name': name,
        'jersey_number': jersey_number,
        'position': position,
        'innings_pitched': float(values.get('innings_pitched', 0) or 0),
        'hits_allowed': values.get('hits_allowed', 0),
        'runs_allowed': values.get('runs_allowed', 0),
        'earned_runs': values.get('earned_runs', 0),
        'walks_allowed': values.get('walks_allowed', 0),
        'strikeouts': values.get('strikeouts', 0),
        'home_runs_allowed': values.get('home_runs_allowed', 0),
        'pitches': values.get('pitches', 0),
        'strikes': values.get('strikes', 0),
        'batters_faced': values.get('batters_faced', 0),
        'hit_by_pitch_allowed': values.get('hit_by_pitch_allowed', 0),
        'wild_pitches': values.get('wild_pitches', 0),
        'win': False,
        'loss': False,
        'save': False,
    }


# ── 表头解析 ───────────────────────────────────────────────────────

BATTING_LABELS = {'AB': 'at_bats', 'R': 'runs', 'H': 'hits',
                  'RBI': 'rbi', 'BB': 'walks', 'SO': 'strikeouts'}
PITCHING_LABELS = {'IP': 'innings_pitched', 'H': 'hits_allowed', 'R': 'runs_allowed',
                   'ER': 'earned_runs', 'BB': 'walks_allowed', 'SO': 'strikeouts',
                   'HR': 'home_runs_allowed'}


def _team_names(words):
    """取表头里的两个队名（中文词）。"""
    return [w for w in words if re.search(r'[一-鿿]', w['text'])]


def _parse_batting_header(words):
    """打击表头 → (boundary, 我方在左?, 左栏列定义, 右栏列定义, 我方队名)"""
    teams = _team_names(words)
    if len(teams) < 2:
        return None
    left_team, right_team = teams[0], teams[1]
    boundary = right_team['x0']
    left, right = _split_by_boundary(words, boundary)
    left_cols = _header_columns(left, set(BATTING_LABELS))
    right_cols = _header_columns(right, set(BATTING_LABELS))
    ours_left = _is_our_team(left_team['text'])
    return {
        'boundary': boundary,
        'ours_left': ours_left,
        'left_cols': left_cols,
        'right_cols': right_cols,
        'our_team': left_team['text'] if ours_left else right_team['text'],
    }


def _parse_pitching_header(words):
    """投手表头 → 同上"""
    teams = _team_names(words)
    if len(teams) < 2:
        return None
    left_team, right_team = teams[0], teams[1]
    boundary = right_team['x0']
    left, right = _split_by_boundary(words, boundary)
    left_cols = _header_columns(left, set(PITCHING_LABELS))
    right_cols = _header_columns(right, set(PITCHING_LABELS))
    ours_left = _is_our_team(left_team['text'])
    return {
        'boundary': boundary,
        'ours_left': ours_left,
        'left_cols': left_cols,
        'right_cols': right_cols,
        'our_team': left_team['text'] if ours_left else right_team['text'],
    }


def _is_our_team(name):
    from pdf_parser import MY_TEAM_KEYWORDS
    return any(kw in name for kw in MY_TEAM_KEYWORDS)


# ── 主流程 ─────────────────────────────────────────────────────────

def parse_pdf(filepath):
    """解析单个 PDF（列坐标版）。返回结构与 `pdf_parser.parse_pdf()` 一致。"""
    result = {
        'filepath': filepath,
        'game_date': None,
        'opponent': None,
        'my_team_batting': [],
        'my_team_pitching': [],
    }

    try:
        pdf = pdfplumber.open(filepath)
        # 必须在 pdf 关闭前提取词坐标（pdfminer 依赖可 seek 的文件句柄）
        rows = []
        for page in pdf.pages:
            for row in _extract_rows(page):
                for w in row['words']:
                    w['text'] = _normalize_text(w['text'])
                row['text'] = ' '.join(w['text'] for w in row['words'])
                rows.append(row)
        pdf.close()
    except Exception:
        # 不回显异常原文（含服务器绝对路径）—— 见 P1 #6
        result['error'] = 'PDF 读取失败'
        return result

    if not rows:
        result['error'] = 'PDF内容为空'
        return result

    filename = os.path.basename(filepath)
    from pdf_parser import (_parse_opponent_from_filename, _parse_date_from_filename,
                             _parse_game_date)
    result['opponent'] = _parse_opponent_from_filename(filename)
    result['game_date'] = _parse_game_date('\n'.join(r['text'] for r in rows)) \
        or _parse_date_from_filename(filename)

    bat_hdr = None
    pit_hdr = None
    section = 'none'
    bat_rows, pit_rows = [], []
    extras_rows, post_rows = [], []

    def sides(words, hdr):
        """按栏界把一行拆成 (我方词, 对方词)。"""
        if hdr is None:
            return words, []
        left, right = _split_by_boundary(words, hdr['boundary'])
        return (left, right) if hdr['ours_left'] else (right, left)

    for row in rows:
        words = row['words']
        wordset = {w['text'] for w in words}

        if 'BATTING' in wordset and len(wordset) <= 3:
            section = 'none'
            continue
        if 'PITCHING' in wordset and len(wordset) <= 3:
            section = 'none'
            continue

        if {'AB', 'RBI', 'SO'} <= wordset:
            bat_hdr = _parse_batting_header(words)
            section = 'batting'
            continue
        if {'IP', 'ER', 'SO'} <= wordset:
            pit_hdr = _parse_pitching_header(words)
            section = 'pitching'
            continue

        # ⚠️ 「Totals」必须**按栏**判断，不能按整行文本判断。
        # 两队的 Totals 行往往不在同一高度：对方的 Totals 行可能与我方某名
        # 球员的数据行同高（这一行同时含双方的 Totals 与我方球员数据）。
        # 用 startswith('Totals') 会把整行丢掉 —— 我方那名球员连同他后面的
        # 所有人都被跳过（实测漏掉 3 人）。
        if section == 'batting':
            ours, _theirs = sides(words, bat_hdr)
            if 'Totals' in {w['text'] for w in ours}:
                section = 'extras'
                continue
            bat_rows.append(row)
        elif section == 'extras':
            ours, _theirs = sides(words, bat_hdr)
            if 'Totals' in {w['text'] for w in ours}:
                continue
            extras_rows.append(row)
        elif section == 'pitching':
            ours, _theirs = sides(words, pit_hdr)
            if 'Totals' in {w['text'] for w in ours}:
                section = 'post'
                continue
            pit_rows.append(row)
        elif section == 'post':
            ours, _theirs = sides(words, pit_hdr)
            if 'Totals' in {w['text'] for w in ours}:
                continue
            post_rows.append(row)

    # ── 打击表 ──
    if bat_hdr:
        boundary = bat_hdr['boundary']
        ours_left = bat_hdr['ours_left']
        for row in bat_rows:
            left, right = _split_by_boundary(row['words'], boundary)
            side = left if ours_left else right
            cols = bat_hdr['left_cols'] if ours_left else bat_hdr['right_cols']
            for rec in _parse_player_block(side, cols, BATTING_LABELS):
                result['my_team_batting'].append(_make_batting_record(
                    rec['name'], rec['jersey_number'], rec['position'], rec))

    # ── 投手表 ──
    if pit_hdr:
        boundary = pit_hdr['boundary']
        ours_left = pit_hdr['ours_left']
        for row in pit_rows:
            left, right = _split_by_boundary(row['words'], boundary)
            side = left if ours_left else right
            cols = pit_hdr['left_cols'] if ours_left else pit_hdr['right_cols']
            for rec in _parse_player_block(side, cols, PITCHING_LABELS):
                result['my_team_pitching'].append(_make_pitching_record(
                    rec['name'], rec['jersey_number'], rec['position'], rec))

    # ── 附加数据（extras）──
    if bat_hdr:
        boundary = bat_hdr['boundary']
        ours_left = bat_hdr['ours_left']
        our_words = []
        for row in extras_rows:
            left, right = _split_by_boundary(row['words'], boundary)
            our_words.extend(left if ours_left else right)
        _apply_extras(result['my_team_batting'], our_words)

    # ── 投手附加数据（胜负 / 投球数 / 暴投 / 面对打席）──
    if pit_hdr:
        boundary = pit_hdr['boundary']
        ours_left = pit_hdr['ours_left']
        our_words = []
        for row in post_rows:
            left, right = _split_by_boundary(row['words'], boundary)
            our_words.extend(left if ours_left else right)
        _apply_pitching_extras(result['my_team_pitching'], our_words)
        # 守备失误（E）/ 高飞牺牲打（SF）有时印在**投球附加行**里
        # （实测 4 份 2025 年的 box score 如此）—— 那是打者的数据，
        # 不能因为它出现在投球区就丢掉。
        _apply_fielding_extras(result['my_team_batting'], our_words)

    return result


# ── 附加数据合并 ───────────────────────────────────────────────────

from pdf_parser import _split_tag_sections, _extract_named_counts_from  # noqa: E402


def _apply_extras(batting, words):
    """把我方栏的 extras 合并到打击记录里。

    旧版在这里用「第一段/最后段」猜哪段是我方的；这里 words 已经按栏切好，
    每段就必然是我方的。
    """
    if not words:
        return
    text = ' '.join(w['text'] for w in words)
    sections = _split_tag_sections(text)

    def merged(tag):
        return ', '.join(sections.get(tag, []))

    mapping = {
        'doubles': ('2B', merged('2B')),
        'triples': ('3B', merged('3B')),
        'home_runs': ('HR', merged('HR')),
        'stolen_bases': ('SB', merged('SB')),
        'caught_stealing': ('CS', merged('CS')),
        'hit_by_pitch': ('HBP', merged('HBP')),
        # 守备失误（E）与高飞牺牲打（SF）—— Phase R4 补上，
        # 这两项以前有列没数据源，永远是 0（审计 #11）。
        'errors_fielding': ('E', merged('E')),
        'sacrifice_flys': ('SF', merged('SF')),
    }
    for key, (_tag, content) in mapping.items():
        if not content:
            continue
        counts = _extract_named_counts_from(content)
        for player in batting:
            value = counts.get(player['name'])
            if value is not None:
                player[key] = value

    # 合并完 2B/3B/HR 后必须重算总垒数
    # （_make_batting_record 算的时候 extras 还没进来，那时的 total_bases 只是一垒安打数）
    for player in batting:
        player['total_bases'] = _total_bases(player)

    # 自校验：PDF 自己给了每个球员的总垒数（TB 标签）。
    # 用它反查我们推出的 TB 是否一致 —— 不一致说明 2B/3B/HR 的归属串了
    # （这正是旧版静默出错的地方）。TB = H + 2B + 2*3B + 3*HR
    tb_counts = _extract_named_counts_from(merged('TB'))
    for player in batting:
        expected = tb_counts.get(player['name'])
        if expected is None:
            continue
        computed = _total_bases(player)
        player['tb_from_pdf'] = expected
        player['tb_matches'] = (computed == expected)


def _apply_fielding_extras(batting, words):
    """守备失误（E）与高飞牺牲打（SF）—— 从**投球附加行**里取。

    为什么单独一个函数：这两项是**打者**的数据，但 box score 常常把它们
    印在投球区的附加行上（实测 4/17 份 PDF 的 "E:" 在投球行里）。
    不能把整个投球附加行丢给打击统计 —— 那一行里的 "HBP:" 是**被触身球**
    （投手的），混进来会把 HBP 安到错误的人身上。

    只取 E / SF 两个标签，其余标签一概不碰。
    """
    if not words:
        return
    text = ' '.join(w['text'] for w in words)
    sections = _split_tag_sections(text)

    for key, tag in (('errors_fielding', 'E'), ('sacrifice_flys', 'SF')):
        content = ', '.join(sections.get(tag, []))
        if not content:
            continue
        counts = _extract_named_counts_from(content)
        for player in batting:
            value = counts.get(player['name'])
            if value is not None:
                player[key] = value


def _total_bases(player):
    """总垒数 = 一垒安打 + 2*二垒 + 3*三垒 + 4*本垒打
    等价于 H + 2B + 2*3B + 3*HR（把 singles 展开后）。"""
    singles = (player['hits'] - player['doubles']
               - player['triples'] - player['home_runs'])
    if singles < 0:
        singles = 0
    return (singles + player['doubles'] * 2
            + player['triples'] * 3 + player['home_runs'] * 4)


def _apply_pitching_extras(pitching, words):
    """合并投手附加数据：W / L / P-S（投球-好球）/ WP / BF。"""
    if not words:
        return
    text = ' '.join(w['text'] for w in words)
    sections = _split_tag_sections(text)

    for player in pitching:
        name = player['name']

        for tag, key in (('W', 'win'), ('L', 'loss')):
            content = ', '.join(sections.get(tag, []))
            if not content:
                continue
            counts = _extract_named_counts_from(content)
            if name in counts:
                player[key] = True

        # P-S: 姓名 45-24 → 投球数 45、好球 24
        content = ', '.join(sections.get('P-S', []))
        if content:
            for item in content.split(','):
                item = item.strip()
                m = re.match(r'(.+?)\s+(\d+)-(\d+)$', item)
                if not m:
                    continue
                if _normalize_name(m.group(1)) == name:
                    player['pitches'] = int(m.group(2))
                    player['strikes'] = int(m.group(3))
                    break

        # WP: 姓名（无数字 → 1 次）
        content = ', '.join(sections.get('WP', []))
        if content:
            counts = _extract_named_counts_from(content)
            if name in counts:
                player['wild_pitches'] = counts[name]

        # BF: 面对打席数
        content = ', '.join(sections.get('BF', []))
        if content:
            counts = _extract_named_counts_from(content)
            if name in counts:
                player['batters_faced'] = counts[name]

        # HBP: 被触身球（投手的「触身球」列）
        content = ', '.join(sections.get('HBP', []))
        if content:
            counts = _extract_named_counts_from(content)
            if name in counts:
                player['hit_by_pitch_allowed'] = counts[name]

