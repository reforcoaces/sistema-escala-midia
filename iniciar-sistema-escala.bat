@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem ---------------------------------------------------------------------------
rem  Pasta do projeto:
rem  - Se este ficheiro estiver na raiz do repositório (junto a app.py), basta
rem    criar um atalho na Área de Trabalho para este .bat — não precisa editar nada.
rem  - Se copiar o .bat para a Área de Trabalho sem o resto do projeto, defina
rem    ROOT abaixo com o caminho completo da pasta clonada (com \ no fim).
rem ---------------------------------------------------------------------------
set "ROOT=%~dp0"
if not exist "%ROOT%app.py" (
  set "ROOT=C:\Users\diogosilveira\OneDrive\Documentos\github-clones\sistema-escala-midia\"
)

if not exist "%ROOT%app.py" (
  echo.
  echo [Erro] Nao encontrei app.py em:
  echo   %ROOT%
  echo.
  echo Coloque este .bat na pasta do projeto ou edite a variavel ROOT neste ficheiro.
  echo.
  pause
  exit /b 1
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo.
  echo [Erro] Ambiente virtual nao encontrado: "%ROOT%.venv\Scripts\python.exe"
  echo Crie na pasta do projeto:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo A abrir o servidor (Flask) em http://127.0.0.1:5050/
echo Mantenha a janela "Escala de comunicacao" aberta enquanto usar o sistema.
echo.

start "Escala de comunicacao — servidor" /D "%ROOT%" cmd /k .venv\Scripts\python.exe app.py

rem Dar tempo ao Flask arrancar antes de abrir o browser
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5050/"

echo Navegador pedido. Se a pagina nao carregar, espere mais 2 segundos e atualize (F5).
timeout /t 4 >nul
endlocal
