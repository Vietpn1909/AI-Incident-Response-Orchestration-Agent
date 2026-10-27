# Dựng toàn bộ hệ thống demo bằng MỘT lệnh.
#
#     powershell -ExecutionPolicy Bypass -File scripts\khoi_dong_demo.ps1
#
# Vì sao cần script này thay vì mấy dòng lệnh chép tay: buổi demo có 8 thứ phải
# lên đúng thứ tự, và bốn trong số đó hỏng theo kiểu IM LẶNG — không báo lỗi,
# chỉ cho ra màn hình trống hoặc số sai:
#
#   1. Postgres phải khỏe TRƯỚC service-thanh-toan. Pool asyncpg khởi tạo đúng
#      một lần trong `lifespan` và KHÔNG thử lại; lên trước Postgres là pool
#      chết vĩnh viễn, `/pay` trả 503 "Pool chưa khởi tạo" cho tới khi restart.
#   2. Container Postgres KHÔNG có volume (xem `docker-compose.demo.yml` — chỉ
#      khai `prometheus_data`). `docker compose up` mà recreate nó là mất sạch
#      `deploy_history`, và UC-4 mất luôn `change_note` — nguồn phi cấu trúc duy
#      nhất để LLM nêu đúng nguyên nhân. Script tự dò và seed lại.
#   3. Prometheus mới lên thì chưa có series nào. Biểu đồ trắng trơn, Agent log
#      đầy "PromQL không trả series nào". Phải bắn tải nhẹ để hâm nóng.
#   4. Streamlit KHÔNG đọc `.env` (chỉ backend đọc, qua pydantic-settings). Thiếu
#      biến nào là mất đúng chức năng đó, mà trang vẫn lên bình thường.
#
# Tham số:
#   -KhongHamNong   bỏ bước bắn tải hâm nóng (nhanh hơn ~75 giây, nhưng biểu đồ
#                   sẽ trống vài phút đầu cho tới khi có traffic thật)
#   -UC4            bật cờ deploy hỏng cho service-thanh-toan (kịch bản UC-4)

param(
    [switch]$KhongHamNong,
    [switch]$UC4
)

$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Repo '.venv\Scripts\python.exe'
$LogDir = Join-Path $env:TEMP 'p035-logs'
$Compose = Join-Path $Repo 'docker-compose.demo.yml'

function Buoc($so, $chu) { Write-Host "`n[$so] $chu" -ForegroundColor Cyan }
function Xong($chu) { Write-Host "    OK  $chu" -ForegroundColor Green }
function Canh($chu) { Write-Host "    !!  $chu" -ForegroundColor Yellow }

# ── 0. Môi trường Python ───────────────────────────────────────────────────
# Thư mục là `.venv` CÓ DẤU CHẤM. Có giai đoạn nó tên `venv`, nên lệnh chép từ
# tài liệu cũ sẽ báo "No such file or directory" mà không nói vì sao.
Buoc 0 'Kiem tra moi truong Python'
if (-not (Test-Path $Py)) {
    Write-Host "    Khong thay $Py" -ForegroundColor Red
    Write-Host '    Tao moi truong: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt -r demo/requirements.txt'
    exit 1
}
Xong $Py

# ── 1. Docker Desktop ──────────────────────────────────────────────────────
Buoc 1 'Docker Desktop'
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    # Docker Desktop không nằm ở Program Files trên máy này mà ở LOCALAPPDATA —
    # bản cài theo user. Thử cả hai chỗ trước khi bỏ cuộc.
    $UngVien = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    )
    $Exe = $UngVien | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Exe) {
        Write-Host '    Khong tim thay Docker Desktop. Mo tay roi chay lai script.' -ForegroundColor Red
        exit 1
    }
    Canh 'Docker chua chay — dang khoi dong, doi toi 180 giay'
    Start-Process $Exe
    $HetGio = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $HetGio) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 5
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '    Docker van chua san sang sau 180 giay.' -ForegroundColor Red
        exit 1
    }
}
Xong 'Docker daemon san sang'

# ── 2. Stack demo ──────────────────────────────────────────────────────────
Buoc 2 'Stack demo (Postgres, 4 service, Prometheus)'
Push-Location $Repo
try {
    docker compose -f $Compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up that bai' }

    if ($UC4) {
        # Cờ này làm `/pay` INSERT vào cột `idempotency_key` KHÔNG tồn tại →
        # UndefinedColumnError → 500. Đó là kịch bản "deploy hỏng" của UC-4, và
        # là kịch bản DUY NHẤT mà rollback chạy THẬT (`executors.py` chỉ thi hành
        # thật khi phát hiện container đang bật cờ lỗi).
        #
        # ⚠️ Phải chạy SAU `up -d`, không phải trước. `docker compose up` so cấu
        # hình đã resolve với cấu hình của container đang chạy; dựng container
        # với cờ bật rồi mới gọi `up -d` (lúc đó biến môi trường đã bị xoá) thì
        # compose thấy lệch và dựng LẠI container với cờ tắt — im lặng, không báo
        # gì, và `-UC4` coi như không có tác dụng.
        $env:SIMULATE_MISSING_MIGRATION = '1'
        Canh 'Bat co UC-4 — /pay se tra 500 (deploy hong)'
        docker compose -f $Compose up -d --force-recreate service-thanh-toan
        Remove-Item Env:\SIMULATE_MISSING_MIGRATION
    }
} finally {
    Pop-Location
}

# Đợi từng service trả lời thật, không tin `docker ps` — container "Up" chỉ nghĩa
# là tiến trình còn sống, chưa chắc đã nghe được cổng.
$Cong = @{ 'service-thanh-toan' = 8001; 'service-dat-hang' = 8002; 'service-kho-hang' = 8003; 'service-van-chuyen' = 8004; 'prometheus' = 9090 }
foreach ($ten in $Cong.Keys) {
    $p = $Cong[$ten]
    $HetGio = (Get-Date).AddSeconds(90)
    $San = $false
    while ((Get-Date) -lt $HetGio -and -not $San) {
        try {
            Invoke-WebRequest -Uri "http://localhost:$p/" -TimeoutSec 3 -UseBasicParsing *> $null
            $San = $true
        } catch {
            # 404 vẫn là "có người trả lời" — service không có route `/`.
            if ($_.Exception.Response) { $San = $true } else { Start-Sleep -Seconds 2 }
        }
    }
    if ($San) { Xong "$ten :$p" } else { Canh "$ten :$p KHONG tra loi sau 90 giay" }
}

# ── 3. Seed database ───────────────────────────────────────────────────────
# Chỉ seed khi `deploy_history` trống. Seed lại khi đã có dữ liệu thì vô hại
# (`seed.py` tự xóa trước) nhưng mất ~10 giây, và mỗi lần chạy lại là một lần
# đổi mốc thời gian deploy — làm hỏng sự cố UC-4 đang mở dở.
Buoc 3 'Du lieu seed (deploy_history)'
$SoDeploy = (docker exec p035-demo-postgres-1 psql -U demo -d demo -tAc 'select count(*) from deploy_history' 2>$null)
if ($LASTEXITCODE -ne 0 -or [int]($SoDeploy -replace '\s', '') -eq 0) {
    Canh 'Bang trong hoac chua ton tai — dang seed lai'
    Push-Location $Repo
    try {
        $env:DATABASE_URL = 'postgresql://demo:demo@localhost:5432/demo'
        $env:PYTHONIOENCODING = 'utf-8'
        & $Py demo/seed.py
    } finally {
        Pop-Location
    }
    $SoDeploy = (docker exec p035-demo-postgres-1 psql -U demo -d demo -tAc 'select count(*) from deploy_history')
}
Xong "deploy_history: $($SoDeploy -replace '\s', '') ban ghi"

# ── 4. Ba tiến trình chạy trên máy ─────────────────────────────────────────
# `Start-Process` chứ không chạy nền trong chính cửa sổ này: ba tiến trình phải
# sống độc lập, đóng terminal không được làm chúng chết theo.
#
# ⚠️ Backend chạy THẲNG trên máy, KHÔNG bỏ vào container. `GET
# /api/incidents/{key}/logs` gọi `docker logs` qua subprocess; nằm trong
# container thì phải mount `/var/run/docker.sock` — trên Windows là chuyện phiền
# và thừa.
Buoc 4 'Backend, UI, Agent'
New-Item -ItemType Directory -Force $LogDir | Out-Null

# Dọn bản cũ TRƯỚC khi phóng bản mới. Chạy script hai lần liên tiếp mà không dọn
# thì lần sau phóng thêm một bộ nữa; bộ mới không bind được cổng (8000/8501 đang
# bận) và chết ngay, nhưng bảng kiểm cuối script VẪN XANH vì bộ cũ còn phục vụ.
# Kết quả: tưởng đã khởi động lại với cấu hình mới, thực ra vẫn đang chạy cấu
# hình cũ — đúng loại lỗi im lặng mà buổi demo không cần thêm.
$CuLenh = 'uvicorn|streamlit|run_agent'
$Cu = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match $CuLenh }
if ($Cu) {
    Canh "Da co $($Cu.Count) tien trinh cu — dung truoc khi phong lai"
    $Cu | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    # Cho Windows tra lai cong. Khong doi thi Streamlit bao "Port 8501 is already
    # in use" roi tu nhay sang 8502 — trang van len, nhung o dia chi khong ai mo.
    Start-Sleep -Seconds 3
}

$LenhApi = "Set-Location '$Repo'; `$env:CORS_ORIGINS='https://035.emmetech.id.vn,http://localhost:8501'; & '$Py' -m uvicorn src.main:app --host 127.0.0.1 --port 8000"

# Năm biến, thiếu cái nào là mất đúng chức năng đó — mà trang VẪN LÊN bình
# thường, nên lỗi này không tự lộ:
#   API_URL          thiếu → UI đọc dữ liệu ở đâu đó khác, không phải máy này
#   PROM_URL         thiếu → khối biểu đồ và ô "Ảnh hưởng" trống
#   API_PUBLIC_URL   thiếu → trình duyệt gọi `localhost:8000`, người xem từ máy
#                            khác qua tunnel thấy trang đứng im
#   PROM_PUBLIC_URL  thiếu → link "Mở trên Prometheus" trỏ localhost, bấm không ra
#   JIRA_BASE_URL    thiếu → nút sang Jira thành ô xám "Chưa đặt JIRA_BASE_URL"
$LenhUi = "Set-Location '$Repo'; " +
    "`$env:API_URL='http://localhost:8000'; " +
    "`$env:PROM_URL='http://localhost:9090'; " +
    "`$env:API_PUBLIC_URL='https://api-035.emmetech.id.vn'; " +
    "`$env:PROM_PUBLIC_URL='https://prom-035.emmetech.id.vn'; " +
    "`$env:JIRA_BASE_URL='https://jibinarybro.atlassian.net'; " +
    "& '$Py' -m streamlit run ui/status_page.py --server.port 8501 --server.headless true"

$LenhAgent = "Set-Location '$Repo'; & '$Py' scripts/run_agent.py"

$Cai = @(
    @{ Ten = 'api'; Lenh = $LenhApi },
    @{ Ten = 'ui'; Lenh = $LenhUi },
    @{ Ten = 'agent'; Lenh = $LenhAgent }
)
foreach ($c in $Cai) {
    Start-Process powershell `
        -ArgumentList '-NoProfile', '-Command', $c.Lenh `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "$($c.Ten).log") `
        -RedirectStandardError (Join-Path $LogDir "$($c.Ten).err")
}

foreach ($muc in @(@{ Url = 'http://localhost:8000/docs'; Ten = 'Backend  :8000' }, @{ Url = 'http://localhost:8501/_stcore/health'; Ten = 'UI       :8501' })) {
    $HetGio = (Get-Date).AddSeconds(120)
    $San = $false
    while ((Get-Date) -lt $HetGio -and -not $San) {
        try {
            Invoke-WebRequest -Uri $muc.Url -TimeoutSec 3 -UseBasicParsing *> $null
            $San = $true
        } catch { Start-Sleep -Seconds 2 }
    }
    if ($San) { Xong $muc.Ten } else { Canh "$($muc.Ten) khong len sau 120 giay — xem $LogDir" }
}
Xong "Agent (log o $LogDir\agent.err)"

# ── 5. Hâm nóng ────────────────────────────────────────────────────────────
# Mức tải THẤP, cố ý: chỉ để Prometheus có series và baseline p95 bắt đầu tích
# điểm. Không dùng `demo/loadtest.py` ở đây — file đó ramp lên hàng trăm
# concurrent và cố ý làm p95 vượt ngưỡng, tức là mở sự cố ngay lúc chuẩn bị.
if (-not $KhongHamNong) {
    Buoc 5 'Ham nong (~75 giay) — de bieu do co duong ve ngay'
    Push-Location $Repo
    try {
        $env:PYTHONIOENCODING = 'utf-8'
        & $Py scripts/ham_nong.py 75
    } finally {
        Pop-Location
    }
} else {
    Buoc 5 'Bo qua ham nong (-KhongHamNong) — bieu do se trong cho toi khi co traffic'
}

# ── 6. Bảng kiểm cuối ──────────────────────────────────────────────────────
Buoc 6 'Bang kiem'
$Kiem = @(
    @{ Ten = 'Status page (may nay)'; Url = 'http://localhost:8501' },
    @{ Ten = 'War room  (may nay)'; Url = 'http://localhost:8501/war_room' },
    @{ Ten = 'Backend'; Url = 'http://localhost:8000/api/status' },
    @{ Ten = 'Prometheus'; Url = 'http://localhost:9090/-/ready' },
    @{ Ten = 'Status page (tunnel)'; Url = 'https://035.emmetech.id.vn' },
    @{ Ten = 'Backend    (tunnel)'; Url = 'https://api-035.emmetech.id.vn/api/status' },
    @{ Ten = 'Prometheus (tunnel)'; Url = 'https://prom-035.emmetech.id.vn/-/ready' }
)
foreach ($k in $Kiem) {
    try {
        $r = Invoke-WebRequest -Uri $k.Url -TimeoutSec 25 -UseBasicParsing
        Write-Host ("    {0,-24} {1}" -f $k.Ten, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("    {0,-24} HONG — {1}" -f $k.Ten, $_.Exception.Message) -ForegroundColor Yellow
    }
}

$Co = (docker exec p035-demo-service-thanh-toan-1 printenv SIMULATE_MISSING_MIGRATION 2>$null)
if (-not $Co) { $Co = '0' }
Write-Host "`nSIMULATE_MISSING_MIGRATION = $($Co -replace '\s','')  (1 = dang o kich ban UC-4 deploy hong)"
Write-Host "Log: $LogDir   (Agent ghi vao agent.err, KHONG phai agent.log)"
Write-Host "Dung tat ca: powershell -ExecutionPolicy Bypass -File scripts\dung_demo.ps1`n"
