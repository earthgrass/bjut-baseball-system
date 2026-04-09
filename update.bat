@echo off
echo ====================================
echo 数据库更新脚本
echo ====================================

echo 1. 生成新的迁移脚本...
flask db migrate -m "database update"

echo.
echo 2. 应用迁移...
flask db upgrade

echo.
echo ✓ 数据库更新完成
echo.
pause