@echo off
setlocal EnableExtensions
rem Nota: nao usar chcp 65001 aqui — com ficheiro .bat em UTF-8 o cmd pode
rem corromper o parsing das linhas seguintes.

rem ---------------------------------------------------------------------------
rem  Pasta do projeto:
rem  - Se este ficheiro estiver na raiz do repositorio junto a app.py, basta
rem    criar um atalho na Area de Trabalho para este .bat.
rem  - Se copiar o .bat para a Area de Trabalho sem o resto do projeto, defina
rem    ROOT abaixo com o caminho completo da pasta clonada sem barra no fim.
rem ---------------------------------------------------------------------------
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
if not exist "%ROOT%\app.py" (
  set "ROOT=C:\Users\diogosilveira\OneDrive\Documentos\github-clones\sistema-escala-midia"
)

if not exist "%ROOT%\app.py" (
  echo.
  echo [Erro] Nao encontrei app.py em:
  echo   %ROOT%\
  echo.
  echo Coloque este .bat na pasta do projeto ou edite a variavel ROOT neste ficheiro.
  echo.
  pause
  exit /b 1
)

if exist "%ROOT%\.venv\Scripts\python.exe" (
  set "PYEXE=%ROOT%\.venv\Scripts\python.exe"
  echo Python: ambiente virtual .venv
) else (
  set "PYEXE=python"
  echo Python: instalacao do sistema ^(sem pasta .venv^).
  echo Se aparecer erro de modulo em falta, na pasta do projeto execute:
  echo   pip install -r requirements.txt
  echo.
)

echo A abrir o servidor ^(Flask^) em http://127.0.0.1:5050/
echo Mantenha a janela "Escala de comunicacao" aberta enquanto usar o sistema.
echo.

start "Escala de comunicacao — servidor" /D "%ROOT%" cmd /k "%PYEXE%" app.py

rem Dar tempo ao Flask arrancar antes de abrir o browser
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5050/"

echo Navegador pedido. Se a pagina nao carregar, espere mais 2 segundos e atualize ^(F5^).
timeout /t 4 >nul
endlocal
