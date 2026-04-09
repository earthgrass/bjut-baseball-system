@echo off
echo ====================================
echo 重置数据库脚本
echo ====================================

echo 警告：这将删除所有数据！
set /p confirm="确认重置数据库？(y/n): "

if "%confirm%"=="y" (
    echo 删除数据库文件...
    del baseball_players.db 2>nul
    
    echo 删除迁移历史...
    rmdir /s /q migrations 2>nul
    
    echo 重新初始化...
    flask db init
    flask db migrate -m "initial migration"
    flask db upgrade
    
    echo ✓ 数据库已重置
) else (
    echo 操作已取消
)
pause