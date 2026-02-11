# krCalendar 실행 스크립트
# 이 스크립트는 프로젝트 루트에서 실행해야 합니다.

# 현재 디렉토리를 프로젝트 루트로 이동
Set-Location "D:\nextcloud\2. Projects\Y-000. project krCalendar"

# Python main 모듈 실행
python -m src.main

# 종료 대기
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
