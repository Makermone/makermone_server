import os
import sys
import platform
import subprocess
import site
from pathlib import Path

def print_table(results):
    print("\n" + "="*80)
    print(f"{'점검 항목':<40} | {'상태':<15} | {'상세 내용'}")
    print("="*80)
    for item in results:
        status_color = "🟢 안전" if item['status'] == "Safe" else "🔴 위험"
        print(f"{item['check']:<40} | {status_color:<15} | {item['detail']}")
    print("="*80 + "\n")

def run_scanner():
    results = []
    os_name = platform.system()
    print(f"🔍 [시스템 감지] 운영체제: {os_name} 기반 보안 스캔을 시작합니다...")

    # ==========================================
    # 1. npm (axios) 공급망 공격 점검
    # ==========================================
    try:
        npm_out = subprocess.check_output(['npm', 'list', 'axios', '-g', '--depth=0'], stderr=subprocess.STDOUT, text=True)
        if "1.14.1" in npm_out or "0.30.4" in npm_out:
            results.append({"check": "글로벌 axios 버전 확인", "status": "Danger", "detail": "악성 버전(1.14.1 또는 0.30.4) 감지됨"})
        else:
            results.append({"check": "글로벌 axios 버전 확인", "status": "Safe", "detail": "안전한 버전이거나 설치되지 않음"})
    except FileNotFoundError:
        results.append({"check": "글로벌 axios 버전 확인", "status": "Safe", "detail": "npm이 설치되지 않음"})
    except subprocess.CalledProcessError:
        results.append({"check": "글로벌 axios 버전 확인", "status": "Safe", "detail": "글로벌 axios 없음"})

    # 악성 페이로드 파일 확인
    payload_found = False
    if os_name == "Windows":
        payload_path = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / 'wt.exe'
    elif os_name == "Darwin": # macOS
        payload_path = Path('/Library/Caches/com.apple.act.mond')
    else: # Linux
        payload_path = Path('/tmp/ld.py')

    if payload_path.exists():
        results.append({"check": f"axios 페이로드 파일 존재 여부", "status": "Danger", "detail": f"악성 파일 발견: {payload_path}"})
    else:
        results.append({"check": f"axios 페이로드 파일 존재 여부", "status": "Safe", "detail": f"악성 파일 없음 ({payload_path})"})

    # ==========================================
    # 2. PyPI (litellm) 공급망 공격 점검
    # ==========================================
    try:
        pip_out = subprocess.check_output([sys.executable, '-m', 'pip', 'show', 'litellm'], stderr=subprocess.STDOUT, text=True)
        version_line = [line for line in pip_out.split('\n') if line.startswith('Version:')]
        if version_line:
            version = version_line[0].split(': ')[1]
            if version in ["1.82.7", "1.82.8"]: # 악성으로 판명된 버전
                results.append({"check": "litellm 설치 버전 확인", "status": "Danger", "detail": f"악성 버전 감지됨 (v{version})"})
            else:
                results.append({"check": "litellm 설치 버전 확인", "status": "Safe", "detail": f"설치됨 (안전한 버전: v{version})"})
    except subprocess.CalledProcessError:
         results.append({"check": "litellm 설치 버전 확인", "status": "Safe", "detail": "현재 환경에 litellm 설치되지 않음"})

    # site-packages 내 악성 .pth 파일 검색
    pth_found = False
    site_packages = site.getsitepackages() + [site.getusersitepackages()]
    for sp in site_packages:
        sp_path = Path(sp)
        if sp_path.exists():
            malicious_pth = sp_path / 'litellm_init.pth'
            if malicious_pth.exists():
                pth_found = True
                results.append({"check": "악성 .pth 파일 존재 여부", "status": "Danger", "detail": f"백도어 발견: {malicious_pth}"})
                break
    
    if not pth_found:
        results.append({"check": "악성 .pth 파일 존재 여부", "status": "Safe", "detail": "litellm_init.pth 파일 없음"})

    # 결과 출력
    print_table(results)

if __name__ == "__main__":
    run_scanner()