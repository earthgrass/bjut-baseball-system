"""
PDF Parser characterization tests — Phase E0

约束：
- 不使用真实 PDF（包含其他球员/对手数据，可能敏感）
- 仅做：
  1. parser 模块可正常 import
  2. parser 文本解析层（_normalize_name / _normalize_text / _extract_named_counts_from）的 unit test
  3. parse_pdf() 对不存在文件返回 error dict（baseline behavior）
  4. parse_pdf() 对空文件返回 error dict
"""
from pdf_parser import (
    parse_pdf,
    _normalize_text,
    _normalize_name,
    _extract_named_counts_from,
    _split_tag_sections,
    _parse_opponent_from_filename,
    _parse_date_from_filename,
)


# ====== 模块可加载 ======

def test_parser_module_imports():
    """parser 模块导入不应失败"""
    assert callable(parse_pdf)


# ====== 文本规范化 ======

def test_normalize_text_康熙部首():
    """PDF 中的康熙部首字符应被映射为标准汉字"""
    # ⻬ → 齐
    assert _normalize_text('⻬') == '齐'
    # ⻜ → 飞
    assert _normalize_text('⻜') == '飞'
    # ⻰ → 龙
    assert _normalize_text('⻰') == '龙'
    # 多字符混合
    assert _normalize_text('⻬佳#37') == '齐佳#37'


def test_normalize_text_passthrough():
    """非部首字符应原样保留"""
    assert _normalize_text('张三') == '张三'
    assert _normalize_text('Pitcher 2025') == 'Pitcher 2025'


# ====== 球员名规范化 ======

def test_normalize_name_strip_junk():
    """CR: 前缀 / 背号 / 位置括号 应被去除"""
    assert _normalize_name('CR:张三') == '张三'
    assert _normalize_name('张三#7') == '张三'
    assert _normalize_name('张三(游击手)') == '张三'
    assert _normalize_name('张三123') == '张三'


def test_normalize_name_known_fixes():
    """已知的合并行特例"""
    assert _normalize_name('⻬佳#37000000王佳帅') == '齐佳'
    # NOTE: 这条规则当前 parser 里有，未来 PDF 格式变化时需调整
    # 是已知 baseline 行为


# ====== 文件名解析 ======

def test_parse_opponent_from_filename():
    assert _parse_opponent_from_filename('北京工业大学_vs_清华_Nov_16_2024.pdf') == '清华'
    assert _parse_opponent_from_filename('清华_vs_北京工业大学_Nov_16_2024.pdf') == '清华'
    assert _parse_opponent_from_filename('某队_vs_某队.pdf') is None  # 无'北京工业'关键词


def test_parse_date_from_filename():
    """Nov_16_2024 → 2024-11-16

    BASELINE 注意：当前实现只对纯 ASCII 月份名有效。
    真实文件 `北京工业大学_vs_清华_Nov_16_2024.pdf` 会失败（regex 匹配但 strptime 失败）。
    实际运行依赖 _parse_game_date(text) 从 PDF 内容提取日期。
    """
    # 纯 ASCII 月份名（英文文件名）
    assert _parse_date_from_filename('Nov_16_2024.pdf') == '2024-11-16'
    assert _parse_date_from_filename('Apr_1_2023.pdf') == '2023-04-01'
    # 真实文件名含中文 — 当前返回 None（BASELINE 限制）
    assert _parse_date_from_filename('北京工业大学_vs_清华_Nov_16_2024.pdf') is None


# ====== 附加信息提取 ======

def test_extract_named_counts_from_basic():
    """'球员A 2, 球员B 1' → {'球员A': 2, '球员B': 1}"""
    result = _extract_named_counts_from('张三 2, 李四 1')
    assert result.get('张三') == 2
    assert result.get('李四') == 1


def test_split_tag_sections():
    """同一 tag 在文本中出现多次（我方 + 对方）应都被切分"""
    text = "2B: 张三 1, 李四 2 HR: 王五 1 2B: 对方甲 1"
    sections = _split_tag_sections(text)
    assert len(sections.get('2B', [])) == 2
    assert len(sections.get('HR', [])) == 1


# ====== parse_pdf() 错误路径 ======

def test_parse_pdf_nonexistent_file():
    """文件不存在应返回 error 字段"""
    result = parse_pdf('/nonexistent/path.pdf')
    assert 'error' in result
    # baseline: error 信息是中文
    assert 'PDF' in result['error'] or '读取' in result['error']


def test_parse_pdf_empty_file(tmp_path):
    """空文件应返回 error"""
    empty = tmp_path / 'empty.pdf'
    empty.write_bytes(b'')
    result = parse_pdf(str(empty))
    assert 'error' in result


# ====== 已知 BASELINE 限制 ======

def test_normalize_name_no_jersey_uuid_handling():
    """文档：当前 parser 处理 'CR:⻬佳#37000000王佳帅' 是依赖硬编码规则
    这是 baseline 锁定；未来 PDF 格式变化需重新评估"""
    # 真实 PDF 中可能遇到
    text = 'CR:⻬佳#37000000王佳帅'
    name = _normalize_name(text)
    assert name == '齐佳'  # baseline: 硬编码特例