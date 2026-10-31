"""
指标引擎 —— 全项目**唯一**的公式来源
============================================================
为什么要有这个模块：
    修复前，ERA / WHIP / AVG / OBP / SLG / OPS 这些公式散落在 6 处：
        database.py（权威）、app.py ×2、import_pdfs.py、
        migrate_profiles_sqlite.py、static/js/script.js（前端预览）
    改一个指标要同步改 6 处（含前端那份），漏改就出现「网页上算一个数、
    导出的 CSV 是另一个数」。

局数（IP）口径 —— 本项目最重要的一条约定
--------------------------------------------------------------
    这些 box score 用**中文记法**：小数位表示几分之一局，
        0.1 = 1/3 局    0.2 = 2/3 局    1.1 = 1⅓ 局
    库里 `game_records.innings_pitched` 存的就是**记法字面值**（与 PDF 一致），
    不做换算、也不迁移历史数据。

    但 ERA = ER*9/IP 要求 IP 是**真实局数**，所以所有**聚合**必须逐条换算：
        true_ip(record) = int(ip) + 小数位/3

    ⚠️ 不能对「合计」换算 —— 逐场的小数位加起来可能 ≥10 而进位：
        0.5 + 0.5 → 字面合计 1.0 → 换算 1.0，但真实是 5/3+5/3 = 3.333
    所以换算必须在**逐条记录**上做（见 database._accumulate_record）。

    本项目的库里小数位只出现过 1 和 2（对应 1/3、2/3 局），
    规则由 PDF 自身的 Totals 行在 16/17 份文件上独立验证过
    （见 scripts/validate_ip_notation.py）。

WHIP 口径（Phase R5 修正）
--------------------------------------------------------------
    修复前 WHIP = (被安打 + 保送) / 投球局数 —— **分母用错了**。
    标准口径是**面对打席数（BF）**：

        WHIP = (H + BB) / BF

    用局数当分母会离谱地偏高：库里实测刘孝宇旧值 5.60，标准口径 0.56。

    ⚠️ 分子分母必须来自**同一批场次**：有的场次 PDF 没给 BF（见下方
    「限定场次」），若分子用全部场次、分母只用有 BF 的场次，
    分子会被多算，WHIP 反而虚高（实测 5 名投手会算错）。

    所以 WHIP 只统计**有 BF 的场次**（见 database._accumulate_record 的
    whip_hits/whip_walks 累加），分母即这些场次的 BF 合计。
"""


def innings_to_true(innings):
    """记法局数 → 真实局数。

    >>> round(innings_to_true(3.0), 4)
    3.0
    >>> round(innings_to_true(1.1), 4)      # 1⅓ 局
    1.3333
    >>> round(innings_to_true(0.2), 4)      # ⅔ 局
    0.6667
    """
    try:
        value = float(innings or 0)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0:
        return 0.0
    whole = int(value)
    digit = round((value - whole) * 10)
    if digit in (1, 2):
        return whole + digit / 3.0
    # 不属于中文记法（理论上不该出现）→ 按字面小数处理
    return value


def format_innings(innings):
    """真实局数 → 记法显示（如 1.3333 → '1.1'）。"""
    value = float(innings or 0)
    whole = int(value)
    remainder = value - whole
    digit = 0
    if remainder > 0:
        digit = int(round(remainder * 3))
        if digit == 3:
            whole += 1
            digit = 0
    return '%d.%d' % (whole, digit) if digit else '%d' % whole


# ── 打击 ───────────────────────────────────────────────────────────

def batting_average(hits, at_bats):
    """打击率 = 安打 / 打数。"""
    if not at_bats or at_bats <= 0:
        return 0.0
    return round(hits / at_bats, 3)


def total_bases(hits, doubles, triples, home_runs):
    """总垒数 = 一垒安打 + 2*二垒 + 3*三垒 + 4*本垒打。"""
    singles = hits - doubles - triples - home_runs
    if singles < 0:
        singles = 0
    return singles + doubles * 2 + triples * 3 + home_runs * 4


def slugging_percentage(total_bases_value, at_bats):
    """长打率 = 总垒数 / 打数。"""
    if not at_bats or at_bats <= 0:
        return 0.0
    return round(total_bases_value / at_bats, 3)


def on_base_percentage(hits, walks, hit_by_pitch, sacrifice_flies, sacrifice_hits, at_bats):
    """上垒率 = (安打+保送+触身球) / (打数+保送+触身球+高飞牺牲打+牺牲触击)

    ⚠️ 修复前分母漏了牺牲触击(SH) —— 见 HANDOFF「OBP 漏 SH」。
    当前库里 SH 全为 0，所以这条修正对现有数据无数值影响，
    但从现在起录入的牺牲触击会被正确计入。
    """
    plate_appearances = (at_bats + walks + hit_by_pitch
                         + sacrifice_flies + sacrifice_hits)
    if plate_appearances <= 0:
        return 0.0
    numerator = hits + walks + hit_by_pitch
    return round(numerator / plate_appearances, 3)


def ops(on_base_pct, slugging_pct):
    """OPS = 上垒率 + 长打率。

    ⚠️ 传入的应当是**未舍入**的上垒率与长打率 —— 先各自舍入再相加，
    会产生「二次舍入」误差（Phase R3 审计 B4）。
    batting_metrics() 内部就是这么做的。
    """
    return round(on_base_pct + slugging_pct, 3)


def isolated_power(slugging_pct, batting_avg):
    """ISO = 长打率 - 打击率（纯长打能力，扣掉四垒安打的影响）。"""
    return round(slugging_pct - batting_avg, 3)


def plate_appearances(at_bats, walks, hit_by_pitch, sacrifice_flies, sacrifice_hits):
    """打席数 = 打数 + 保送 + 触身球 + 牺牲飞球 + 牺牲触击。

    K% / BB% 的分母用它（不是打数 —— 三振也占一个打席）。
    """
    return (at_bats + walks + hit_by_pitch
            + sacrifice_flies + sacrifice_hits)


def strikeout_rate(strikeouts, plate_appearances_value):
    """打者三振率 K% = 三振 / 打席数 * 100。"""
    if not plate_appearances_value or plate_appearances_value <= 0:
        return 0.0
    return round((strikeouts / plate_appearances_value) * 100, 1)


def walk_rate(walks, plate_appearances_value):
    """打者保送率 BB% = 保送 / 打席数 * 100。"""
    if not plate_appearances_value or plate_appearances_value <= 0:
        return 0.0
    return round((walks / plate_appearances_value) * 100, 1)


def strikeout_walk_rate(strikeout_pct, walk_pct):
    """打者 K-B% = K% - BB%（正数 = 好球优于保送）。"""
    return round(strikeout_pct - walk_pct, 1)


def babip(hits, home_runs, at_bats, strikeouts, sacrifice_flies, sacrifice_hits):
    """BABIP = (安打 - 本垒打) / (打数 - 三振 - 牺牲飞球 - 牺牲触击)。

    「打出去没被直接接杀」的比率。分母为 0 时返回 0。
    """
    denominator = at_bats - strikeouts - sacrifice_flies - sacrifice_hits
    if denominator <= 0:
        return 0.0
    return round((hits - home_runs) / denominator, 3)


def stolen_base_rate(stolen_bases, caught_stealing):
    """盗垒成功率 SB% = 盗垒成功 / (盗垒成功 + 盗垒失败)。"""
    attempts = stolen_bases + caught_stealing
    if attempts <= 0:
        return 0.0
    return round((stolen_bases / attempts) * 100, 1)


def caught_stealing_rate(stolen_bases, caught_stealing):
    """盗垒失败率 CS% = 盗垒失败 / (盗垒成功 + 盗垒失败)。"""
    attempts = stolen_bases + caught_stealing
    if attempts <= 0:
        return 0.0
    return round((caught_stealing / attempts) * 100, 1)


# ── 投球 ───────────────────────────────────────────────────────────

def era(earned_runs, innings):
    """防御率 = 自责分 * 9 / 真实局数。

    ⚠️ `innings` 必须是**真实局数**（见 innings_to_true）。
    """
    if not innings or innings <= 0:
        return 0.0
    return round((earned_runs * 9) / innings, 2)


def whip(hits_allowed, walks_allowed, batters_faced):
    """WHIP = (被安打 + 保送) / **面对打席数**。

    ⚠️ Phase R5 修正：分母从「投球局数」改成「面对打席数（BF）」——
    这是标准口径。修复前用局数当分母，实测偏高数倍
    （例：库里刘孝宇旧值 5.60 → 标准口径 0.56）。

    ⚠️ 分子分母必须来自**同一批场次**：调用方只应传入「有 BF 的场次」的
    累计值（见 database._accumulate_record）。BF 为 0 时返回 0.0，
    表示「无打者数数据，无法计算 WHIP」——宁可空着，也不给一个假的数。
    """
    if not batters_faced or batters_faced <= 0:
        return 0.0
    return round((walks_allowed + hits_allowed) / batters_faced, 2)


def strikeouts_per_9(strikeouts, innings):
    """三振率 K/9 = 三振 / 真实局数 * 9。

    ⚠️ `innings` 必须是**真实局数**。
    """
    if not innings or innings <= 0:
        return 0.0
    return round((strikeouts / innings) * 9, 2)


def walks_per_9(walks_allowed, innings):
    """保送率 BB/9 = 保送 / 真实局数 * 9。

    ⚠️ `innings` 必须是**真实局数**。
    """
    if not innings or innings <= 0:
        return 0.0
    return round((walks_allowed / innings) * 9, 2)


def pitcher_strikeout_walk_rate(strikeouts_per_9_value, walks_per_9_value):
    """投手 K-B% = K/9 - BB/9。

    ⚠️ 投手的 K-B% 惯例是**按 9 局**相减（不是打者那种按打席相减）。
    """
    return round(strikeouts_per_9_value - walks_per_9_value, 2)


def strike_percentage(strikes, pitches):
    """好球率 = 好球数 / 投球数 * 100。"""
    if not pitches or pitches <= 0:
        return 0.0
    return round((strikes / pitches) * 100, 1)


# ── 汇总：一次算完某一方（打者/投手）的全部派生率 ──────────────────
#
# 档案表只存**原始累计数**与少数几个派生列；其余派生率在序列化时算，
# 但**公式一律来自本模块**（全项目唯一公式源，Phase R3 确立）。
# 这两个函数是给「把一堆累计数丢进来、拿回全部率」的便捷入口。

def batting_metrics(totals):
    """由打击累计数算出全部打击派生率。

    totals 需要的键（与 FielderProfile 的列同名）：
        at_bats, hits, walks, hit_by_pitch, sacrifice_flies, sacrifice_hits,
        doubles, triples, home_runs, strikeouts, stolen_bases, caught_stealing

    返回：
        batting_average, on_base_percentage, slugging_percentage, ops,
        isolated_power, babip, plate_appearances, total_bases,
        strikeout_rate, walk_rate, strikeout_walk_rate,
        stolen_base_rate, caught_stealing_rate

    ⚠️ OPS 在这里**只舍入一次**：先用未舍入的 OBP/SLG 相加，
    再舍入 —— 避免「二次舍入」（审计 B4）。
    """
    at_bats = totals.get('at_bats') or 0
    hits = totals.get('hits') or 0
    walks = totals.get('walks') or 0
    hit_by_pitch = totals.get('hit_by_pitch') or 0
    sacrifice_flies = totals.get('sacrifice_flies') or 0
    sacrifice_hits = totals.get('sacrifice_hits') or 0
    doubles = totals.get('doubles') or 0
    triples = totals.get('triples') or 0
    home_runs = totals.get('home_runs') or 0
    strikeouts = totals.get('strikeouts') or 0
    stolen_bases = totals.get('stolen_bases') or 0
    caught_stealing = totals.get('caught_stealing') or 0

    tb = total_bases(hits, doubles, triples, home_runs)
    pa = plate_appearances(at_bats, walks, hit_by_pitch,
                           sacrifice_flies, sacrifice_hits)

    avg = batting_average(hits, at_bats)
    slg = slugging_percentage(tb, at_bats)

    # 未舍入的上垒率，用于算 OPS（避免二次舍入）
    if pa > 0:
        obp_raw = (hits + walks + hit_by_pitch) / pa
    else:
        obp_raw = 0.0
    slg_raw = (tb / at_bats) if at_bats > 0 else 0.0

    k_pct = strikeout_rate(strikeouts, pa)
    bb_pct = walk_rate(walks, pa)

    return {
        'batting_average': avg,
        'on_base_percentage': round(obp_raw, 3),
        'slugging_percentage': slg,
        'ops': ops(obp_raw, slg_raw),
        'isolated_power': isolated_power(slg, avg),
        'babip': babip(hits, home_runs, at_bats, strikeouts,
                       sacrifice_flies, sacrifice_hits),
        'plate_appearances': pa,
        'total_bases': tb,
        'strikeout_rate': k_pct,
        'walk_rate': bb_pct,
        'strikeout_walk_rate': strikeout_walk_rate(k_pct, bb_pct),
        'stolen_base_rate': stolen_base_rate(stolen_bases, caught_stealing),
        'caught_stealing_rate': caught_stealing_rate(stolen_bases, caught_stealing),
    }


def pitching_metrics(totals):
    """由投球累计数算出全部投球派生率。

    totals 需要的键：
        innings（**真实局数**，不是记法字面值！）、earned_runs,
        hits_allowed, walks_allowed, strikeouts, pitches, strikes
    可选键：
        whip_hits / whip_walks —— WHIP 的计算基数（只统计有 BF 的场次），
        batters_faced —— 同一批场次的 BF 合计。两者都缺时 whip = 0.0。

    返回：
        era, whip, strikeouts_per_9, walks_per_9, pitcher_strikeout_walk_rate,
        strike_percentage
    """
    innings = totals.get('innings') or 0
    earned_runs = totals.get('earned_runs') or 0
    walks_allowed = totals.get('walks_allowed') or 0
    strikeouts = totals.get('strikeouts') or 0
    pitches = totals.get('pitches') or 0
    strikes = totals.get('strikes') or 0

    k9 = strikeouts_per_9(strikeouts, innings)
    bb9 = walks_per_9(walks_allowed, innings)

    return {
        'era': era(earned_runs, innings),
        'whip': whip(totals.get('whip_hits') or 0,
                     totals.get('whip_walks') or 0,
                     totals.get('batters_faced') or 0),
        'strikeouts_per_9': k9,
        'walks_per_9': bb9,
        'pitcher_strikeout_walk_rate': pitcher_strikeout_walk_rate(k9, bb9),
        'strike_percentage': strike_percentage(strikes, pitches),
    }

