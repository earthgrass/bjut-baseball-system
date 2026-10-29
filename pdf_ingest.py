"""
PDF 解析入口 —— 选版式、带回退标记
============================================================
两套解析器：
    `pdf_parser_columns`  列坐标版（Phase R3 新写）
        按 pdfplumber 的词坐标切分左右两栏，附加数据（2B/HR/TB/SB/CS/HBP/BF/WP…）
        不会把对方球员混进我方数据。
    `pdf_parser`           纯文本版（旧版）
        用 `extract_text()` 的拍平文本做正则切分，
        靠「第一段/最后段」猜哪段是我方的 —— 会把对方球员当成我方球员
        （实测造出过 '齐佳王佳帅'、'孙世铎'、'子非陈' 三个假球员）。

本模块对外只暴露一个 `parse_pdf()`：
    优先用列坐标版；
    只有当它**完全没解析出数据**时才退回文本版，并在结果里打
    `_fallback=True` 标记 —— 退回不是静默的，导入报告会把它列出来。
"""
from pdf_parser import parse_pdf as parse_pdf_text
from pdf_parser_columns import parse_pdf as parse_pdf_columns


def parse_pdf(filepath):
    """解析单个 PDF。返回结构与 `pdf_parser.parse_pdf()` 一致。"""
    result = parse_pdf_columns(filepath)
    if result.get('error'):
        return result

    has_data = bool(result.get('my_team_batting') or result.get('my_team_pitching'))
    if has_data:
        return result

    # 列坐标版没解析出东西 → 退回文本版，但要留下标记
    fallback = parse_pdf_text(filepath)
    if fallback.get('error'):
        return result  # 两版都失败，返回列坐标版的错误
    fallback['_fallback'] = True
    fallback['_fallback_reason'] = '列坐标版未解析出数据，已退回文本版'
    return fallback
