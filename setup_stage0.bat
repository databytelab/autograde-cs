@echo off
echo ============================================================
echo  AutoGrade CS - Stage 0 Setup Script
echo  Running on Windows
echo ============================================================
echo.

:: ─────────────────────────────────────────────
:: STEP 1: Verify correct Python and pip
:: ─────────────────────────────────────────────
echo [1/7] Verifying Python and pip versions...
echo.

py -3.11 --version
echo Above should say Python 3.11.x

py -3.11 -m pip --version
echo Above pip should reference Python311 path, NOT Python310
echo.

:: Fix: always use "py -3.11 -m pip" instead of bare "pip"
:: We will alias this properly via the venv in Stage 1
:: For now just confirm 3.11 pip works
py -3.11 -m pip install --upgrade pip
echo.
echo [OK] pip upgraded on Python 3.11
echo.

:: ─────────────────────────────────────────────
:: STEP 2: Check Git
:: ─────────────────────────────────────────────
echo [2/7] Checking Git...
git --version
if %errorlevel% neq 0 (
    echo [ERROR] Git not found. Download from https://git-scm.com and re-run this script.
    pause
    exit /b 1
)
echo [OK] Git is installed
echo.

:: ─────────────────────────────────────────────
:: STEP 3: Install VSCode Extensions
:: ─────────────────────────────────────────────
echo [3/7] Installing VSCode extensions...
call code --install-extension ms-python.python
call code --install-extension ms-python.vscode-pylance
call code --install-extension humao.rest-client
call code --install-extension eamodio.gitlens
call code --install-extension ms-azuretools.vscode-docker
call code --install-extension rangav.vscode-thunder-client
echo [OK] VSCode extensions installed
echo.

:: ─────────────────────────────────────────────
:: STEP 4: Initialize Git repo (if not already)
:: ─────────────────────────────────────────────
echo [4/7] Initializing Git repository...
if not exist ".git" (
    git init
    git branch -M main
    echo [OK] Git repo initialized
) else (
    echo [OK] Git repo already initialized, skipping
)
echo.

:: ─────────────────────────────────────────────
:: STEP 5: Create .gitignore
:: ─────────────────────────────────────────────
echo [5/7] Creating .gitignore...
(
echo # Python
echo __pycache__/
echo *.py[cod]
echo *$py.class
echo *.pyc
echo venv/
echo .venv/
echo env/
echo.
echo # Environment variables - NEVER commit these
echo .env
echo .env.*
echo !.env.example
echo.
echo # Database files
echo *.db
echo *.sqlite
echo *.sqlite3
echo.
echo # Uploads - student files stay local
echo uploads/
echo.
echo # Logs
echo *.log
echo logs/
echo.
echo # OS files
echo .DS_Store
echo Thumbs.db
echo.
echo # VSCode
echo .vscode/settings.json
echo .vscode/launch.json
echo.
echo # Docker
echo *.override.yml
echo.
echo # Distribution / packaging
echo dist/
echo build/
echo *.egg-info/
echo.
echo # Node
echo node_modules/
echo .next/
) > .gitignore
echo [OK] .gitignore created
echo.

:: ─────────────────────────────────────────────
:: STEP 6: Create README.md
:: ─────────────────────────────────────────────
echo [6/7] Creating README.md...
(
echo # AutoGrade CS
echo.
echo AI-powered assignment grading tool for CS courses.
echo Supports .ipynb, .html, and .py student submissions.
echo.
echo ## Stack
echo - Backend: FastAPI ^(Python 3.11^)
echo - Frontend: Streamlit ^(MVP^) then Next.js
echo - AI: Anthropic Claude API
echo - Database: PostgreSQL ^(SQLite for local dev^)
echo.
echo ## Setup
echo See docs/ folder for full setup instructions.
) > README.md
echo [OK] README.md created
echo.

:: ─────────────────────────────────────────────
:: STEP 7: Initial Git commit
:: ─────────────────────────────────────────────
echo [7/7] Making initial Git commit...
git add .gitignore README.md
git commit -m "Stage 0: Initial repo setup with .gitignore and README"
echo [OK] Initial commit made
echo.

:: ─────────────────────────────────────────────
:: DONE
:: ─────────────────────────────────────────────
echo ============================================================
echo  Stage 0 script complete!
echo.
echo  NEXT MANUAL STEP (one-time, cannot be scripted):
echo  1. Go to github.com
echo  2. Click + then New Repository
echo  3. Name: autograde-cs
echo  4. Set to Private
echo  5. Do NOT add README/.gitignore/license (we made those)
echo  6. Click Create Repository
echo  7. Copy the repo URL shown
echo  8. Run these two commands with YOUR repo URL:
echo.
echo     git remote add origin https://github.com/YOURUSERNAME/autograde-cs.git
echo     git push -u origin main
echo.
echo  Once pushed, come back and we start Stage 1.
echo ============================================================
pause