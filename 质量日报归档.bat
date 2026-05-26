@echo off
chcp 65001 >nul
title 质量日报归档工具

echo ========================================
echo    质量日报归档工具 v1.0
echo    每天3张报表, 自动识别归档
echo ========================================
echo.

REM 检查图片参数
if "%1"=="" (
    echo 使用方法:
    echo   直接拖拽图片到本文件上
    echo   或: 质量日报归档.bat 图片1.png 图片2.png 图片3.png
    echo.
    echo 示例: 将微信保存的3张日报图片拖拽到这里
    pause
    exit /b
)

REM 切换到脚本目录
cd /d "%~dp0"

echo 正在处理 %* 张图片...
echo.

REM 调用WSL中的Python脚本
wsl python3 /mnt/d/质量日报归档工具/quality_report_archiver.py %*

if %errorlevel% neq 0 (
    echo.
    echo ⚠️ 处理过程中出现错误
    echo 请确认:
    echo   1. WSL已安装Python3和PIL库
    echo   2. 在WSL中运行: pip install Pillow
    echo   3. API Key已配置
)

echo.
echo 按任意键退出...
pause >nul
