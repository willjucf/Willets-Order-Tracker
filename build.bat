@echo off
echo ========================================
echo   Willet's Order Tracker - Build Script
echo ========================================
echo.

echo [1/4] Installing Node dependencies...
call npm install
if %errorlevel% neq 0 (
    echo FAILED: npm install. Make sure Node.js is installed.
    pause
    exit /b 1
)

echo.
echo [2/4] Installing Python dependencies...
pip install -r backend\requirements.txt pyinstaller
if %errorlevel% neq 0 (
    echo FAILED: pip install. Make sure Python is installed and in PATH.
    pause
    exit /b 1
)

echo.
echo [3/4] Bundling Python backend...
echo   Clearing PyInstaller cache to force a clean rebuild...
if exist backend\build rd /s /q backend\build
if exist backend\dist rd /s /q backend\dist
if exist backend-dist rd /s /q backend-dist
cd backend
pyinstaller --onefile --name main main.py --hidden-import uvicorn.logging --hidden-import uvicorn.protocols.http --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.protocols.websockets.wsproto_impl --hidden-import uvicorn.protocols.websockets.websockets_impl
cd ..
if not exist backend\dist\main.exe (
    echo FAILED: PyInstaller did not produce main.exe
    pause
    exit /b 1
)
if not exist backend-dist mkdir backend-dist
copy /Y backend\dist\main.exe backend-dist\main.exe

echo.
echo [4/4] Building installer...
call npm run package
if %errorlevel% neq 0 (
    echo.
    echo BUILD FAILED. Common fix: Enable Developer Mode in Windows Settings.
    echo Go to Settings ^> System ^> For Developers ^> Developer Mode ON
    echo Then run this script again.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD COMPLETE!
echo   Installer: release\Willets Order Tracker Setup 1.5.0.exe
echo ========================================
pause
