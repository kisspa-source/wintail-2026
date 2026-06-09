# wintail-2026 단일 EXE 빌드 (Nuitka onefile)
#
# 전제:
#   - Python 3.12+ (64-bit)
#   - MSVC C 컴파일러 (Visual Studio Build Tools) 또는 Nuitka가 안내하는 MinGW
#   - Nuitka:  python -m pip install nuitka
#
# 사용법:
#   ./build.ps1                 # dist/wintail.exe 생성
#   ./build.ps1 -Icon app.ico   # 아이콘 포함
#
# 산출물은 설치 불필요·빠른 시작의 단일 실행 파일이다(외부 의존성 0, 표준 라이브러리만).

param([string]$Icon = "")

$ErrorActionPreference = "Stop"

$nuitkaArgs = @(
    "--onefile",
    "--enable-plugin=tk-inter",
    "--windows-console-mode=disable",
    "--assume-yes-for-downloads",
    "--company-name=wintail",
    "--product-name=wintail-2026",
    "--file-version=0.1.0",
    "--output-filename=wintail.exe",
    "--output-dir=dist"
)
if ($Icon -ne "") {
    $nuitkaArgs += "--windows-icon-from-ico=$Icon"
}

Write-Host "Nuitka onefile 빌드 시작..." -ForegroundColor Cyan
python -m nuitka @nuitkaArgs wintail.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "완료: dist/wintail.exe" -ForegroundColor Green
} else {
    Write-Host "빌드 실패 (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}
