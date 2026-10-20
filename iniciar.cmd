@echo off
cd /d "%~dp0"
where docker >nul 2>nul || (echo Instale o Docker Desktop e rode de novo: https://docs.docker.com/desktop/ & pause & exit /b 1)
if not exist .env powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\criar-env.ps1"
docker compose up -d --build || (pause & exit /b 1)
echo.
echo Aguardando o Lume subir...
powershell -NoProfile -Command "$p=(Select-String -Path .env -Pattern '^APP_PORT=(.*)').Matches.Groups[1].Value; if(-not $p){$p=8080}; for($i=0;$i -lt 120;$i++){ try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 ('http://localhost:'+$p+'/api/health') | Out-Null; Start-Process ('http://localhost:'+$p); exit 0 } catch { Start-Sleep 2 } }; exit 1"
if errorlevel 1 (echo O Lume ainda esta subindo. Acompanhe com: docker compose logs -f) else (echo Pronto! Entre com admin@lume.dev ou leitor@lume.dev - senha Lume@2026)
pause
