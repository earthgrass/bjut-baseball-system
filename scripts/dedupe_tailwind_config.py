"""
脚本：移除 10 个模板里重复的 tailwind.config 内联脚本块，改为引用 shared tailwind.config.js。

每个模板在 </style> 后面都有同样的：
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        arena: { bg, surface, surface2, red, redDark, redAccent }
                    }
                }
            }
        }
    </script>
</head>

这个块与 static/js/tailwind.config.js 内容一致。
外链后即可删除。
"""
import re
from pathlib import Path

TEMPLATES = [
    'index.html', 'players.html', 'add_player.html', 'add_game_record.html',
    'stats.html', 'game_stats.html', 'matchup_stats.html', 'pdf_viewer.html',
    'upload_pdf.html',
    # login.html 已经在 Phase A 阶段重构成 extends base.html，跳过
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / 'templates'

# 精确匹配整个 tailwind.config 内联块（含前后的 <script> 标签与 </head>）
# 9 个 Tailwind 模板的结构完全一致
PATTERN = re.compile(
    r'    <script>\s*'
    r'tailwind\.config = \{\s*'
    r'theme: \{\s*'
    r'extend: \{\s*'
    r'colors: \{\s*'
    r'arena: \{\s*'
    r"bg: '#050505',\s*"
    r"surface: '#0A0A0A',\s*"
    r"surface2: '#111111',\s*"
    r"red: '#E60000',\s*"
    r"redDark: '#990000',\s*"
    r"redAccent: '#FF1A1A'\s*"
    r'\}\s*\}\s*\}\s*\}\s*\}\s*'
    r'</script>\s*'
    r'</head>',
    re.MULTILINE,
)

total_removed = 0
for name in TEMPLATES:
    path = TEMPLATES_DIR / name
    content = path.read_text(encoding='utf-8')
    new_content, n = PATTERN.subn('</head>', content)
    if n > 0:
        path.write_text(new_content, encoding='utf-8')
        print(f'  {name}: removed {n} block(s) ({-len(content)+len(new_content):+d} bytes)')
        total_removed += n
    else:
        print(f'  {name}: no match (already clean?)')

print(f'\nDone. Removed {total_removed} tailwind.config block(s).')
print('Note: shared config now in static/js/tailwind.config.js; load via <script src="..."> in templates that still need it.')