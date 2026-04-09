#!/usr/bin/env python3
"""
数据库初始化脚本
运行: python init_db.py
"""

import os
import sys
from app import app
from database import db, init_positions, add_sample_data

def main():
    """主函数"""
    print("=" * 50)
    print("棒球队管理系统 - 数据库初始化")
    print("=" * 50)
    
    with app.app_context():
        # 1. 创建数据库表
        print("1. 创建数据库表...")
        db.create_all()
        print("   ✓ 数据库表创建完成")
        
        # 2. 初始化位置数据
        print("2. 初始化位置数据...")
        init_positions()
        print("   ✓ 位置数据初始化完成")
        
        # 3. 添加示例数据
        print("3. 添加示例数据...")
        add_sample_data()
        print("   ✓ 示例数据添加完成")
        
        print("\n" + "=" * 50)
        print("数据库初始化完成！")
        print("现在可以运行: python app.py")
        print("=" * 50)

if __name__ == '__main__':
    main()