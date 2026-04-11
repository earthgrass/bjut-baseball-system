#!/usr/bin/env python
"""启动脚本 - 使用 werkzeug.serving 运行 Flask 应用"""

import os
import sys

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 控制台编码修复
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

from werkzeug.serving import run_simple
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f" * Running on http://127.0.0.1:{port}")
    run_simple('0.0.0.0', port, app, use_debugger=True, use_reloader=False, threaded=True)