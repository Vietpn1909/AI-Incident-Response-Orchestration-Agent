# Dừng hệ thống demo.
#
#     powershell -ExecutionPolicy Bypass -File scripts\dung_demo.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\dung_demo.ps1 -CaDocker
#
# Mặc định CHỈ dừng ba tiến trình trên máy (backend, UI, Agent) và để nguyên
# stack Docker. Vì sao mặc định như vậy: `docker compose down` sẽ xóa container
# Postgres, mà container đó KHÔNG có volume — mất luôn `deploy_history` đã seed,
# và lần demo sau phải seed lại. Giữ container chạy thì lần sau bật lên là dùng
# được ngay.
#
# Tham số:
#   -CaDocker   dừng luôn stack Docker (`docker compose stop` — KHÔNG xóa
#               container, nên dữ liệu seed vẫn còn)
#   -Xoa        xóa hẳn container và volume. CHỈ dùng khi muốn làm lại từ đầu;
#               sau lệnh này phải seed lại.

param(
    [switch]$CaDocker,
    [switch]$Xoa
)

$ErrorActionPreference = 'Continue'

$Repo = Split-Path -Parent $PSScriptRoot
$Compose = Join-Path $Repo 'docker-compose.demo.yml'

# Lọc theo dòng lệnh chứ không tắt mọi `python.exe`: máy có thể đang chạy
# python cho việc khác, và tắt nhầm là mất việc của người ta.
$MauLenh = 'uvicorn|streamlit|run_agent'
$TienTrinh = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match $MauLenh }

if (-not $TienTrinh) {
    Write-Host 'Khong co backend/UI/Agent nao dang chay.'
} else {
    foreach ($p in $TienTrinh) {
        $ten = 'khong ro'
        if ($p.CommandLine -match 'uvicorn') { $ten = 'backend :8000' }
        elseif ($p.CommandLine -match 'streamlit') { $ten = 'UI      :8501' }
        elseif ($p.CommandLine -match 'run_agent') { $ten = 'Agent' }
        # "Không tìm thấy tiến trình" KHÔNG phải lỗi: mỗi tiến trình ở đây có một
        # PowerShell mẹ, và tắt mẹ thì con đi theo. Ảnh chụp `Get-CimInstance` lấy
        # từ trước vòng lặp nên vẫn còn tên những PID vừa chết vì lý do đó.
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host "  da dung   $ten (pid $($p.ProcessId))" -ForegroundColor Green
        } catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
            Write-Host "  da tat san $ten (pid $($p.ProcessId))" -ForegroundColor DarkGray
        } catch {
            Write-Host "  KHONG dung duoc $ten (pid $($p.ProcessId)): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# Streamlit đẻ tiến trình con để phục vụ; tiến trình cha chết mà con còn sống là
# cổng 8501 vẫn bị giữ, lần khởi động sau báo "Port 8501 is already in use".
$ConSot = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match $MauLenh }
if ($ConSot) {
    Write-Host '  Con tien trinh sot lai — dung tiep' -ForegroundColor Yellow
    $ConSot | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Xoa) {
    Write-Host "`nXoa container va volume — se phai seed lai lan sau." -ForegroundColor Yellow
    docker compose -f $Compose down -v
} elseif ($CaDocker) {
    Write-Host "`nDung stack Docker (giu container, giu du lieu seed)."
    docker compose -f $Compose stop
} else {
    Write-Host "`nStack Docker van chay. Them -CaDocker de dung luon."
}
