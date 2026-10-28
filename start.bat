@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title BaoHanhAI - He Thong Quan Ly Bao Hanh San Pham

REM ===================================================================
REM 1. Chuyen thu muc lam viec ve thu muc goc chua start.bat
REM    Ho tro ca duong dan co khoang trang va ky tu Unicode / tieng Viet
REM ===================================================================
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo =====================================================================
echo    HE THONG QUAN LY BAO HANH SAN PHAM TICH HOP AI (BAOHANHAI)
echo =====================================================================
echo.

REM ===================================================================
REM 2. Khoi tao .env tu mau neu chua ton tai (bao toan .env hien co)
REM ===================================================================
if not exist ".env" (
    if exist "backend\.env" (
        copy /y "backend\.env" ".env" >nul
        echo [*] Da khoi tao tep cau hinh .env tu backend\.env
    ) else if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [*] Da khoi tao tep cau hinh .env tu .env.example
    )
)

REM ===================================================================
REM 3. Kiem tra Python va moi truong ao backend\.venv
REM ===================================================================
set "VENV_DIR=%PROJECT_DIR%backend\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if exist "%PYTHON_EXE%" (
    echo [*] Su dung moi truong ao Python: backend\.venv
) else (
    echo [*] Chua tim thay moi truong ao backend\.venv, dang tim Python...
    where py >nul 2>&1
    if not errorlevel 1 (
        set "SYS_PYTHON=py -3"
    ) else (
        where python >nul 2>&1
        if not errorlevel 1 (
            set "SYS_PYTHON=python"
        ) else (
            echo.
            echo [LOI] Khong tim thay Python tren may tinh cua ban!
            echo Vui long cai dat Python 3.10 tro len tai https://www.python.org/
            echo va nho danh dau chon Add Python to PATH khi cai dat.
            echo.
            echo Nhan phim bat ky de thoat...
            pause >nul
            exit /b 1
        )
    )

    echo [*] Dang khoi tao moi truong ao tai backend\.venv...
    !SYS_PYTHON! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo [LOI] Khong the tao moi truong ao Python tai backend\.venv.
        echo Vui long kiem tra quyen ghi thu muc hoac bo cai dat Python.
        echo.
        echo Nhan phim bat ky de thoat...
        pause >nul
        exit /b 1
    )
    echo [+] Da khoi tao moi truong ao thanh cong.
)

REM ===================================================================
REM 4. Kiem tra thu vien phu thuoc (chi cai khi thieu, khong cai lai moi lan)
REM ===================================================================
echo [*] Kiem tra cac thu vien phu thuoc...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, sqlalchemy, pydantic, dotenv, httpx" >nul 2>&1
if errorlevel 1 (
    echo [*] Dang cai dat thu vien phu thuoc tu backend\requirements.txt lan dau...
    "%VENV_DIR%\Scripts\pip.exe" install -r "%PROJECT_DIR%backend\requirements.txt"
    if errorlevel 1 (
        echo.
        echo [LOI] Cai dat goi phu thuoc that bai!
        echo Vui long kiem tra ket noi mang va thu chay lai.
        echo.
        echo Nhan phim bat ky de thoat...
        pause >nul
        exit /b 1
    )
    echo [+] Da cai dat thanh cong cac thu vien phu thuoc.
) else (
    echo [+] Thu vien phu thuoc da day du va san sang.
)

REM ===================================================================
REM 5. Khoi dong trinh khoi dong tich hop
REM ===================================================================
echo [*] Dang khoi dong may chu web va kiem tra ket noi...
echo.
"%PYTHON_EXE%" "%PROJECT_DIR%backend\app\launcher.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [THONG BAO] Ung dung dung lai voi ma thoat: %EXIT_CODE%
    echo.
    echo Cua so duoc giu lai de ban doc thong bao. Nhan phim bat ky de dong...
    pause >nul
)
