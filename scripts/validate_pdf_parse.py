#!/usr/bin/env python3
"""PDF 解析校验工具（Phase R3）

用 PDF **自己**的数据当独立真值，校验解析器 —— 因为「解析成功」不等于
「数据正确」（历史上 17/17 份都"解析成功"，但数据静默错误）。

三重校验：
    1. **打击 Totals**：我方球员的 AB/R/H/RBI/BB/SO 之和
       必须等于 PDF 打击表的 Totals 行
    2. **投手局数**：我方投手的局数之和（按中文记法换算）
       必须等于 PDF 投球表的 Totals 行
    3. **TB 自校验**：用 H + 2B + 3B + HR 推出的总垒数
       必须等于 PDF 的 TB 标签给的值

用法：
    python scripts/validate_pdf_parse.py              # 校验 data/ 下全部 PDF
    python scripts/validate_pdf_parse.py data/2024/x.pdf
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_parser_columns import _extract_rows, _team_names, _is_our_team
from pdf_parser import _normalize_text
from metrics import innings_to_true


def our_totals(filepath):
    """取我方（左侧或右侧，取决于 PDF 排版）的打击/投球 Totals 行。

    ⚠️ 必须按**栏**判断「这个 Totals 属于谁」——
    两队的 Totals 行往往不在同一高度，对方的 Totals 行可能与我方某名
    球员的数据行同高。
    """
    import pdfplumber
    pdf = pdfplumber.open(filepath)
    rows = []
    for page in pdf.pages:
        for row in _extract_rows(page):
            for word in row['words']:
                word['text'] = _normalize_text(word['text'])
            rows.append(row)
    pdf.close()

    bat_totals = None
    pit_totals = None
    ours_left = None
    boundary = None
    section = None

    for row in rows:
        text = ' '.join(w['text'] for w in row['words']).strip()
        words = row['words']
        if 'AB' in text and 'RBI' in text:
            teams = _team_names(words)
            if len(teams) >= 2:
                ours_left = _is_our_team(teams[0]['text'])
                boundary = teams[1]['x0']
                section = 'batting'
            continue
        if 'IP' in text and 'ER' in text:
            teams = _team_names(words)
            if len(teams) >= 2:
                boundary = teams[1]['x0']
            section = 'pitching'
            continue
        if boundary is None:
            continue
        side = [w for w in words if (w['x0'] < boundary) == ours_left]
        if 'Totals' not in {w['text'] for w in side}:
            continue
        numbers = [w['text'] for w in side
                   if re.match(r'^-?\d+(\.\d+)?$', w['text'])]
        if section == 'batting' and bat_totals is None and len(numbers) >= 6:
            bat_totals = numbers[:6]
        if section == 'pitching' and pit_totals is None and len(numbers) >= 7:
            pit_totals = numbers[:7]
    return bat_totals, pit_totals


def validate(filepath):
    """校验一份 PDF，返回 (是否通过, 说明列表)。"""
    from pdf_ingest import parse_pdf
    problems = []
    bat_totals, pit_totals = our_totals(filepath)
    parsed = parse_pdf(filepath)

    if 'error' in parsed:
        return False, ['解析失败: %s' % parsed['error']]

    batting = parsed['my_team_batting']
    pitching = parsed['my_team_pitching']

    if bat_totals:
        mine = [sum(x[k] for x in batting) for k in
                ('at_bats', 'runs', 'hits', 'rbi', 'walks', 'strikeouts')]
        expected = [int(v) for v in bat_totals]
        if expected != mine:
            problems.append('打击合计 解析=%s PDF=%s' % (mine, expected))
    else:
        problems.append('找不到打击 Totals 行')

    if pit_totals:
        mine_ip = sum(innings_to_true(x['innings_pitched']) for x in pitching)
        expected_ip = innings_to_true(pit_totals[0])
        if abs(mine_ip - expected_ip) > 1e-6:
            problems.append('投手局数 解析=%.4f PDF=%.4f（PDF 自身可能前后矛盾）'
                            % (mine_ip, expected_ip))
    else:
        problems.append('找不到投球 Totals 行')

    checked = 0
    for player in batting:
        if 'tb_from_pdf' not in player:
            continue
        checked += 1
        if not player['tb_matches']:
            problems.append('TB 不符 %s 自算=%s PDF=%s (H=%s 2B=%s 3B=%s HR=%s)'
                            % (player['name'], player['total_bases'],
                               player['tb_from_pdf'], player['hits'],
                               player['doubles'], player['triples'],
                               player['home_runs']))

    return (not problems), problems, checked


def main():
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        files = sorted(glob.glob(os.path.join(root, '*', '*.pdf')))

    passed = 0
    failed = 0
    total_checked = 0
    for filepath in files:
        ok, problems, checked = validate(filepath)
        total_checked += checked
        name = os.path.basename(filepath)
        if ok:
            passed += 1
            print('  OK   %-52s (TB 核对 %d 人)' % (name[:50], checked))
        else:
            failed += 1
            print('  FAIL %-52s' % name[:50])
            for problem in problems:
                print('         - %s' % problem)

    print('\n通过 %d / %d 份，TB 核对 %d 人次' % (passed, passed + failed, total_checked))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
