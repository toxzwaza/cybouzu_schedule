@echo off
echo ========================================
echo スケジュール検索Webアプリを起動します
echo ========================================
echo.

REM Flaskがインストールされているか確認
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Flaskがインストールされていません。
    echo インストールを開始します...
    pip install -r requirements.txt
    echo.
)

echo Webアプリケーションを起動中...
echo.
echo ブラウザで以下のURLにアクセスしてください:
echo http://localhost:5000
echo.
echo 終了するには Ctrl+C を押してください
echo.

python app.py

pause

