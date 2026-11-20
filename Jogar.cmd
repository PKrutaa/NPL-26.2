@echo off
rem Windows launcher. Extra arguments go to "zelda_env play", for example: Jogar.cmd --mute
setlocal
set "HERE=%~dp0"
if not exist "%HERE%.venv\Scripts\python.exe" (
  echo Ambiente ausente em "%HERE%.venv". Siga a instalacao no README.md.
  pause
  exit /b 1
)
pushd "%HERE%"
"%HERE%.venv\Scripts\python.exe" -m zelda_env play %*
set "CODE=%ERRORLEVEL%"
popd
if not "%CODE%"=="0" pause
exit /b %CODE%
