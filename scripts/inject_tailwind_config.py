"""
在 9 个还没 extends base.html 的 Tailwind 模板的 <head> 里，
在 cdn.tailwindcss.com 之前注入 <script src="...tailwind.config.js"></script>。

（base.html 已经包含这个引用，无需改动；login.html 已重构，跳过。）
"""
from pathlib import Path

TEMPLATES = [
    'index.html', 'players.html', 'add_player.html', 'add_game_record.html',
    'stats.html', 'game_stats.html', 'matchup_stats.html', 'pdf_viewer.html',
    'upload_pdf.html',
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / 'templates'

CDN_LINE = '<script src="https://cdn.tailwindcss.com"></script>'
CONFIG_LINK = (
    '    <script src="{{ url_for(\'static\', filename=\'js/tailwind.config.js\') }}"></script>\n    '
    + CDN_LINE
)

for name in TEMPLATES:
    path = TEMPLATES_DIR / name
    content = path.read_text(encoding='utf-8')
    if 'tailwind.config.js' in content:
        print(f'  {name}: already has config link, skip')
        continue
    if CDN_LINE not in content:
        print(f'  {name}: CDN line not found, skip')
        continue
    new_content = content.replace(CDN_LINE, CONFIG_LINK, 1)
    path.write_text(new_content, encoding='utf-8')
    print(f'  {name}: config link injected')

print('\nDone.')