@echo off
echo.
echo ==========================================
echo   BiciSi - PM2 Setup & Startup
echo ==========================================
echo.

echo [Step 1] Checking/Installing PM2...
call npm install -g pm2

echo [Step 2] Checking/Installing Windows Startup Service...
call npm install -g pm2-windows-startup
call pm2-startup install

echo [Step 3] Starting applications...
call pm2 start ecosystem.config.js

echo [Step 4] Saving list to restart on reboot...
call pm2 save

echo.
echo ==========================================
echo   Setup Complete!
echo   Use "pm2 status" to see your apps.
echo   Use "pm2 logs" to see activity.
echo ==========================================
pause
