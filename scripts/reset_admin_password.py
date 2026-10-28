#!/usr/bin/env python3
"""重设管理员账号密码。

用途：数据库恢复后 users 表里的 password_hash 可能是占位符
（`REQUIRES_PASSWORD_RESET`），无法登录，需要在此重设。

用法（推荐，密码不落盘、不进命令行历史）：
    python scripts/reset_admin_password.py
    → 交互式输入用户名与密码（密码不回显）

用法（自动化，传环境变量）：
    ADMIN_PASSWORD='xxx' ADMIN_USERNAME=admin python scripts/reset_admin_password.py

注意：本脚本不会把明文密码写入 .env 或任何配置文件。
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from database import db, User


def reset(username: str, password: str) -> int:
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user is None:
            print(f"[x] 用户 '{username}' 不存在")
            return 1

        user.set_password(password)
        db.session.commit()

        # 立刻回读校验
        ok = User.query.filter_by(username=username).first().check_password(password)
        print(f"[ok] 用户 '{username}' 密码已重设，校验结果: {'通过' if ok else '失败'}")
        return 0 if ok else 1


def main() -> int:
    username = os.environ.get('ADMIN_USERNAME', '').strip() or (input('用户名 [admin]: ').strip() or 'admin')

    password = os.environ.get('ADMIN_PASSWORD')
    if not password:
        password = getpass.getpass('新密码: ')
        if not password:
            print('[x] 密码不能为空')
            return 1
        confirm = getpass.getpass('确认密码: ')
        if password != confirm:
            print('[x] 两次密码不一致')
            return 1

    if len(password) < 6:
        print('[!] 警告：密码少于 6 位')

    return reset(username, password)


if __name__ == '__main__':
    sys.exit(main())
