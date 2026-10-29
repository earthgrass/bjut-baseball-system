#!/usr/bin/env python
"""本地开发启动脚本 —— 仅绑定 127.0.0.1，不对外暴露。

与 run.py / app.py 的区别：
- run.py、app.py 绑定 0.0.0.0，供服务器部署时接受外网访问；
- 本脚本绑定 127.0.0.1，只允许本机访问，适合日常开发和本地试用。

用法：
    python run_local.py
    PORT=8080 python run_local.py
"""
import os
import sys

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 控制台编码修复
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_error=True)
    except Exception:
        pass

from werkzeug.serving import run_simple
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f" * 本地开发模式：http://{host}:{port}  (仅本机可访问)")
    print(" * 管理员账号：admin / 见 .env 或 scripts/reset_admin_password.py")
    run_simple(host, port, app, use_debugger=False, use_reloader=False, threaded=True)
