@echo off
chcp 65001
echo [메이커몬] LibreOffice 렌더링 데몬 (Port 2002) 가동을 시작합니다...
"C:\Program Files\LibreOffice\program\soffice.exe" --headless --accept="socket,host=localhost,port=2002;urp;" --nofirststartwizard
echo 가동 완료! 창을 닫아도 백그라운드에서 유지됩니다.