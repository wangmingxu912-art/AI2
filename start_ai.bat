@echo off
:: 切换 CMD 编码为 UTF-8，解决中文乱码
chcp 65001 >nul

echo ==================================================
echo   AI 阅卷系统自动启动脚本
echo ==================================================

:: 1. 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python！
    pause
    exit
)

:: 2. 安装依赖
echo [1/3] 正在检查并安装 Python 依赖库...
pip install flask flask-cors requests pymupdf pillow -i https://pypi.tuna.tsinghua.edu.cn/simple

:: 3. 启动后端 (使用 start 打开新窗口，避免阻塞)
echo [2/3] 正在启动后端服务...
start "AI-BackEnd-Server" cmd /k "python app.py"

:: 4. 启动前端
echo [3/3] 正在打开前端页面...
:: 等待 2 秒确保后端先启动
timeout /t 2 >nul
start index.html

echo ==================================================
echo   系统已启动！
echo   1. 请在弹出的浏览器窗口中操作。
echo   2. 注意：请勿关闭那个运行 python app.py 的黑色窗口。
echo ==================================================
pause