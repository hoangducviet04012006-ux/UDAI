# =====================================================================
# BaoHanhAI (KT2 + KT3) - lenh phat trien cho Windows / PowerShell
#   Dung nhu:   .\dev.ps1 dev        .\dev.ps1 evidence      .\dev.ps1 check
#   Tuong duong Makefile neu dung Git Bash / Linux / macOS:  make <task>
# =====================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Task = 'help',

    # Tham so phu cho mot so task, vi du: .\dev.ps1 seed -Message "ghi chu"
    [Parameter(Position = 1)]
    [string]$Message = ''
)

# 'Continue' (không phải 'Stop'): các lệnh native như python/docker có thể in
# cảnh báo ra stderr (ví dụ DeprecationWarning) - ta kiểm tra kết quả bằng exit code.
$ErrorActionPreference = 'Continue'

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Tests    = Join-Path $Root 'tests'
$Evidence = Join-Path $Root 'docs\evidence'

function Write-Head($text) {
    Write-Host ''
    Write-Host "== $text" -ForegroundColor Cyan
}

function Invoke-InPath($path, [scriptblock]$action) {
    Push-Location $path
    try { & $action } finally { Pop-Location }
}

# Python: uu tien .venv trong backend/, neu chua co thi dung launcher `py -3.12`
# (may co nhieu ban Python: `python` mac dinh co the la 3.11 thieu thu vien)
function Invoke-Py {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PyArgs)
    $venvPy = Join-Path $Backend '.venv\Scripts\python.exe'
    if (Test-Path $venvPy) { & $venvPy @PyArgs } else { & py -3.12 @PyArgs }
}

function Show-Help {
    Write-Host 'BaoHanhAI (KT2 + KT3) - lenh phat trien' -ForegroundColor Green
    @'
  Bat dau nhanh:
    .\dev.ps1 install       - tao backend\.venv va cai requirements (chay 1 lan)
    .\dev.ps1 install-chat  - cai thu vien AI cho chatbot (LangChain/LangGraph - TUY CHON)
    .\dev.ps1 initdb        - tao 16 bang trong database\baohanh_ai.db (11 core + 5 chatbot)
    .\dev.ps1 resetdb       - XOA du lieu demo roi tao lai + nap seed (trang thai sach de demo/chup anh)
    .\dev.ps1 seed          - nap du lieu mau (serial, khach, danh muc loi, phieu)
    .\dev.ps1 dev           - chay API + giao dien web: http://127.0.0.1:8000/docs

  Kiem thu & minh chung:
    .\dev.ps1 evidence      - chay 25 minh chung (KT2 + KT3) -> docs\evidence\minh_chung_KT2_KT3.txt
    .\dev.ps1 test          - chay 25 minh chung, chi in ra man hinh
    .\dev.ps1 workflow      - kiem thu vong doi PHIEU BAO HANH (CASE 1..8) + loi nghiep vu
    .\dev.ps1 workbench     - kiem thu MAN HINH CONG VIEC THEO VAI TRO (CASE A..H)
    .\dev.ps1 ui            - smoke test giao dien phieu (Node, khong can trinh duyet)
    .\dev.ps1 check         - chay minh chung + nghiep vu phieu + bang dieu khien vai tro + giao dien

  Kiem tra nhanh:
    .\dev.ps1 health        - goi /health va /api cua backend dang chay
    .\dev.ps1 tree          - in cay thu muc du an
    .\dev.ps1 clean         - xoa __pycache__ / .pytest_cache

  PostgreSQL (tuy chon - mac dinh dung SQLite):
    .\dev.ps1 up            - chay PostgreSQL 16 bang Docker
    .\dev.ps1 down          - dung container (giu du lieu)
    .\dev.ps1 logs          - xem log db
    .\dev.ps1 psql          - mo psql trong container
'@ | Write-Host
}

switch ($Task.ToLower()) {
    # ------------------------------- Bat dau --------------------------------
    'install' {
        Write-Head 'Tao backend\.venv va cai dependencies'
        Invoke-InPath $Backend {
            if (-not (Test-Path '.venv')) { & py -3.12 -m venv .venv }
            $venv = Join-Path $Backend '.venv\Scripts\python.exe'
            & $venv -m pip install -U pip
            & $venv -m pip install -r requirements.txt
        }
        Write-Host 'Xong. Tiep theo: .\dev.ps1 initdb' -ForegroundColor Green
    }

    'install-chat' {
        # [KT4/P0] Thu vien AI cho chatbot (LangChain RAG + LangGraph Agent) - TUY CHON.
        # Khong cai cung requirements.txt de giu baseline KT2/KT3 nhe va chay offline 100%.
        Write-Head 'Cai thu vien AI cho chatbot (backend\requirements-ai-chat.txt)'
        Invoke-InPath $Backend {
            $venv = Join-Path $Backend '.venv\Scripts\python.exe'
            if (-not (Test-Path $venv)) {
                Write-Warning 'Chua co backend\.venv - hay chay truoc: .\dev.ps1 install'
            } else {
                & $venv -m pip install -r requirements-ai-chat.txt
            }
        }
        Write-Host 'Xong. Chatbot van mac dinh chay offline (CHATBOT_PROVIDER=mock).' -ForegroundColor Green
    }

    'initdb' {
        Write-Head 'Khoi tao 16 bang CSDL (11 bang core KT1 + 5 bang chatbot KT4)'
        Invoke-InPath $Root { Invoke-Py "$Tests\init_db.py" }
    }

    'seed' {
        Write-Head 'Nap du lieu mau'
        Invoke-InPath $Root { Invoke-Py "$Tests\seed_data.py" }
    }

    'resetdb' {
        # Dua CSDL demo ve TRANG THAI SACH: xoa bang -> tao lai -> nap seed.
        # Dung khi can demo/chup anh hoac sau khi chay cac bo kiem thao co tao du lieu.
        Write-Head 'Xoa du lieu demo -> tao lai 16 bang -> nap seed (trang thai sach)'
        Invoke-InPath $Root {
            Invoke-Py "$Tests\init_db.py" '--reset'
            if ($LASTEXITCODE -ne 0) { Write-Host 'CANH BAO: khong tao lai duoc CSDL.' -ForegroundColor Red; exit 1 }
            Invoke-Py "$Tests\seed_data.py"
        }
        Write-Host 'Da dua CSDL demo ve trang thai seed sach.' -ForegroundColor Green
    }

    'dev' {
        Write-Head 'Chay API + giao dien web: http://127.0.0.1:8000/docs'
        Invoke-InPath $Backend {
            Invoke-Py '-m' 'uvicorn' 'app.main:app' '--host' '127.0.0.1' '--port' '8000' '--reload'
        }
    }

    # ------------------------ Kiem thu & minh chung -------------------------
    'evidence' {
        Write-Head 'Chay 25 minh chung KT2 + KT3'
        if (-not (Test-Path $Evidence)) { New-Item -ItemType Directory -Force -Path $Evidence | Out-Null }
        $log = Join-Path $Evidence 'minh_chung_KT2_KT3.txt'
        $output = $null
        $code = 1
        Invoke-InPath $Root {
            $script:output = Invoke-Py "$Tests\test_scenarios.py" 2>&1
            $script:code = $LASTEXITCODE
        }
        $output | Out-Host
        $output | Out-File -Encoding utf8 $log
        Write-Host "Da luu minh chung (UTF-8): $log" -ForegroundColor Green
        if ($code -eq 0) { Write-Host 'KET QUA: 25/25 PASS' -ForegroundColor Green }
        else { Write-Warning "Co minh chung FAIL (exit code $code) - xem chi tiet trong log." }
    }

    'test' {
        Write-Head 'Chay 25 minh chung KT2 + KT3 (khong luu file)'
        Invoke-InPath $Root { Invoke-Py "$Tests\test_scenarios.py" }
    }

    'check' {
        Write-Head 'Cong kiem tra truoc khi nop bai'
        $tail = $null
        $code = 1
        Invoke-InPath $Root {
            $all = Invoke-Py "$Tests\test_scenarios.py" 2>&1
            $script:code = $LASTEXITCODE
            $script:tail = $all | Select-Object -Last 14
        }
        $tail | Out-Host
        if ($code -eq 0) { Write-Host 'OK: toan bo minh chung KT2 + KT3 PASS' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: co minh chung KT2/KT3 FAIL' -ForegroundColor Red; exit 1 }

        # [Dot hoan thien nghiep vu] Kiem thu vong doi phieu bao hanh (CASE 1..8)
        $flowCode = 1
        $flowTail = $null
        Invoke-InPath $Root {
            $flow = Invoke-Py "$Tests\test_ticket_workflow.py" 2>&1
            $script:flowCode = $LASTEXITCODE
            $script:flowTail = $flow | Select-Object -Last 14
        }
        $flowTail | Out-Host
        if ($flowCode -eq 0) { Write-Host 'OK: nghiep vu phieu bao hanh PASS (CASE 1..8)' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: co kich ban nghiep vu phieu FAIL' -ForegroundColor Red; exit 1 }

        # [Dot man hinh cong viec theo vai tro] Bang dieu khiên + quyen + "viec cua toi" (CASE A..H)
        $wbCode = 1
        $wbTail = $null
        Invoke-InPath $Root {
            $wb = Invoke-Py "$Tests\test_role_workbench.py" 2>&1
            $script:wbCode = $LASTEXITCODE
            $script:wbTail = $wb | Select-Object -Last 16
        }
        $wbTail | Out-Host
        if ($wbCode -eq 0) { Write-Host 'OK: man hinh cong viec theo vai tro PASS (CASE A..H)' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: co kich ban man hinh cong viec FAIL' -ForegroundColor Red; exit 1 }

        # [Dot hoan thien nghiep vu] Smoke test lop hien thi (can Node.js)
        Write-Head 'Smoke test giao dien phieu (Node)'
        $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        if (-not $nodeCmd) {
            Write-Warning 'Chua cai Node.js -> bo qua smoke test giao dien (khong anh huong backend).'
        } else {
            $uiCode = 1
            Invoke-InPath $Root {
                & node "$Tests\smoke_frontend.js"
                $script:uiCode = $LASTEXITCODE
            }
            if ($uiCode -eq 0) { Write-Host 'OK: cac ham hien thi cua man hinh phieu PASS' -ForegroundColor Green }
            else { Write-Host 'CANH BAO: smoke test giao dien FAIL' -ForegroundColor Red; exit 1 }
        }
    }

    'workflow' {
        Write-Head 'Kiem thu nghiep vu PHIEU BAO HANH (CASE 1..8)'
        Invoke-InPath $Root { Invoke-Py "$Tests\test_ticket_workflow.py" }
        if ($LASTEXITCODE -eq 0) { Write-Host 'OK: toan bo kich ban nghiep vu phieu PASS' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: co kich ban nghiep vu phieu FAIL' -ForegroundColor Red; exit 1 }
    }

    'workbench' {
        Write-Head 'Kiem thu MAN HINH CONG VIEC THEO VAI TRO (CASE A..H)'
        Invoke-InPath $Root { Invoke-Py "$Tests\test_role_workbench.py" }
        if ($LASTEXITCODE -eq 0) { Write-Host 'OK: moi vai tro thay dung cong viec cua minh' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: co kich ban man hinh cong viec FAIL' -ForegroundColor Red; exit 1 }
    }

    'ui' {
        Write-Head 'Smoke test giao dien phieu (Node, khong can trinh duyet)'
        $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        if (-not $nodeCmd) {
            Write-Warning 'Chua cai Node.js - khong chay duoc smoke test giao dien.'
            exit 1
        }
        Invoke-InPath $Root { & node "$Tests\smoke_frontend.js" }
        if ($LASTEXITCODE -eq 0) { Write-Host 'OK: smoke test giao dien PASS' -ForegroundColor Green }
        else { Write-Host 'CANH BAO: smoke test giao dien FAIL' -ForegroundColor Red; exit 1 }
    }

    # ------------------------------ Tien ich --------------------------------
    'health' {
        foreach ($url in 'http://127.0.0.1:8000/health', 'http://127.0.0.1:8000/api') {
            Write-Head "GET $url"
            try { (Invoke-WebRequest $url -UseBasicParsing).Content } catch { Write-Warning $_.Exception.Message }
        }
    }

    'tree' {
        Get-ChildItem -Path $Root -Recurse -Depth 2 |
            Where-Object { $_.FullName -notmatch '\\(node_modules|\.venv|\.git|__pycache__|\.pytest_cache)(\\|$)' } |
            ForEach-Object { $_.FullName.Replace($Root, '.') } | Sort-Object
    }

    'clean' {
        Write-Head 'Xoa cache (khong dong den CSDL)'
        Get-ChildItem -Path $Root -Recurse -Directory -Force |
            Where-Object { $_.Name -in '__pycache__', '.pytest_cache' } |
            ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
        Write-Host 'Da don cache.' -ForegroundColor Green
    }

    # ------------------------------- Docker ---------------------------------
    'up'   { Invoke-InPath $Root { docker compose up -d db } }
    'down' { Invoke-InPath $Root { docker compose down } }
    'logs' { Invoke-InPath $Root { docker compose logs -f db } }
    'psql' { Invoke-InPath $Root { docker compose exec db psql -U baohanh -d baohanh_ai } }

    default { Show-Help }
}

