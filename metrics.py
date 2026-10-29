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
    """OPS = 上垒率 + 长打率。"""
    return round(on_base_pct + slugging_pct, 3)


# ── 投球 ───────────────────────────────────────────────────────────

def era(earned_runs, innings):
    """防御率 = 自责分 * 9 / 真实局数。

    ⚠️ `innings` 必须是**真实局数**（见 innings_to_true）。
    """
    if not innings or innings <= 0:
        return 0.0
    return round((earned_runs * 9) / innings, 2)


def whip(hits_allowed, walks_allowed, innings):
    """WHIP = (被安打 + 保送) / 真实局数。

    ⚠️ `innings` 必须是**真实局数**。修复前用字面合计做分母，
    局数带小数的投手 WHIP 会偏高。
    """
    if not innings or innings <= 0:
        return 0.0
    return round((walks_allowed + hits_allowed) / innings, 2)


def strike_percentage(strikes, pitches):
    """好球率 = 好球数 / 投球数 * 100。"""
    if not pitches or pitches <= 0:
        return 0.0
    return round((strikes / pitches) * 100, 1)
