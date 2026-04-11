#!/usr/bin/env python3
"""管理员账号创建脚本"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db, User


def create_admin():
    """交互式创建管理员账号"""
    print("=" * 40)
    print("  POWER ARENA - 创建管理员账号")
    print("=" * 40)
    print()

    username = input("请输入用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return

    password = input("请输入密码: ").strip()
    if not password:
        print("密码不能为空")
        return

    confirm_password = input("请确认密码: ").strip()
    if password != confirm_password:
        print("两次密码不一致")
        return

    with app.app_context():
        # 检查用户名是否已存在
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"用户名 '{username}' 已存在")
            return

        # 创建管理员
        admin = User(username=username, is_admin=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        print()
        print(f"管理员账号 '{username}' 创建成功!")


if __name__ == '__main__':
    create_admin()
