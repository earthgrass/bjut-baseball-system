@echo off
echo ====================================
echo 棒球队管理系统 - 自动化安装脚本
echo ====================================

echo 1. 安装依赖包...
pip install -r requirements.txt

echo.
echo 2. 初始化Flask-Migrate...
if not exist migrations (
    flask db init
    echo ✓ 迁移仓库初始化完成
) else (
    echo ✓ 迁移仓库已存在
)

echo.
echo 3. 生成迁移脚本...
flask db migrate -m "initial migration"

echo.
echo 4. 应用数据库迁移...
flask db upgrade

echo.
echo 5. 运行应用...
echo 请访问 http://localhost:5000
python app.py