@echo off
echo ============================================================
echo  Fix GitHub Authentication
echo  Using Personal Access Token (PAT)
echo ============================================================
echo.

:: ─────────────────────────────────────────────
:: Remove the old remote that has no auth
:: ─────────────────────────────────────────────
echo [1/3] Removing old remote...
git remote remove origin
echo [OK] Old remote removed
echo.

:: ─────────────────────────────────────────────
:: Prompt for GitHub details
:: ─────────────────────────────────────────────
echo [2/3] Enter your GitHub details:
echo.
set /p GH_USERNAME="Enter your GitHub username (e.g. databytelab): "
set /p GH_TOKEN="Paste your Personal Access Token (ghp_xxx...): "
echo.

:: ─────────────────────────────────────────────
:: Add new remote with token embedded in URL
:: Format: https://TOKEN@github.com/USERNAME/REPO.git
:: ─────────────────────────────────────────────
echo [3/3] Adding authenticated remote and pushing...
git remote add origin https://%GH_TOKEN%@github.com/%GH_USERNAME%/autograde-cs.git

:: Push to main
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo  SUCCESS! Repo pushed to GitHub.
    echo  Visit: https://github.com/%GH_USERNAME%/autograde-cs
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo  FAILED. Check:
    echo  1. Token was copied correctly ^(no spaces^)
    echo  2. Username is correct
    echo  3. Repo exists at github.com/%GH_USERNAME%/autograde-cs
    echo  4. Token has "repo" scope checked
    echo ============================================================
)
echo.

:: ─────────────────────────────────────────────
:: Also configure Git identity if not set
:: (prevents future commit errors)
:: ─────────────────────────────────────────────
echo Checking Git identity config...
git config user.email >nul 2>&1
if %errorlevel% neq 0 (
    set /p GIT_EMAIL="Enter your email for Git commits: "
    set /p GIT_NAME="Enter your name for Git commits: "
    git config --global user.email "%GIT_EMAIL%"
    git config --global user.name "%GIT_NAME%"
    echo [OK] Git identity configured
) else (
    echo [OK] Git identity already configured
)

echo.
pause