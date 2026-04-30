import os
import time
import requests
from flask import Flask, request, render_template
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

app = Flask(__name__)

# 대표님 지적사항 반영: 기존 명칭(MASTER_DB_API_URL) 복구
MASTER_DB_API_URL = os.getenv("MASTER_DB_API_URL")

# =========================================================================
# 🚀 메이커몬 초경량 인메모리 캐시 (Zero-Latency)
# =========================================================================
CACHE = {}
CACHE_TTL = 60  # 데이터 유지 시간 (초) -> 1분간 네이티브 앱 속도 보장

def get_cached_data(client_code):
    """메모리에 캐시된 데이터가 있고, 1분이 지나지 않았다면 즉시 반환"""
    if client_code in CACHE:
        data, timestamp = CACHE[client_code]
        if time.time() - timestamp < CACHE_TTL:
            return data
    return None

def set_cached_data(client_code, data):
    """구글에서 새로 받아온 데이터를 현재 시간과 함께 메모리에 저장"""
    CACHE[client_code] = (data, time.time())
# =========================================================================

@app.route('/app')
def makermon_spa_router():
    """
    [메이커몬 1-Page SPA 통합 라우터]
    호출 예시: /app?code=BH&view=v01&target=BH03V01
    """
    # 1. 파라미터 파싱
    code_param = request.args.get('code', '').strip().upper()
    view_mode = request.args.get('view', 'main').lower()
    target_project = request.args.get('target', '')

    # 2. 1차 방어막: 명찰 길이 검증
    if len(code_param) < 2:
        return "보안 경고: 유효하지 않은 식별 코드입니다.", 403
    
    client_code = code_param[:2] # 예: "BH"

    # 🚨 2차 방어막: 고객사별 독립 보안 코드 매칭 (대표님 지적사항 반영)
    # .env에서 'SECRET_BH' 등의 키값을 찾아옵니다.
    client_secret = os.getenv(f"SECRET_{client_code}")
    
    if not client_secret:
        return "보안 경고: 등록되지 않은 고객사 시스템입니다.", 403

    # 🚨 1. 메모리 캐시 확인 (구글 요청 건너뛰기)
    full_data = get_cached_data(client_code)

    # 🚨 2. 캐시가 없거나 1분이 지났을 때만 Code.gs 호출 (서버 과부하 방지)
    if full_data is None:
        try:
            res = requests.get(f"{MASTER_DB_API_URL}?code={client_code}&req_type=data", timeout=10)
            res_json = res.json()
            full_data = res_json.get('data', {}) if res.status_code == 200 else {}
            
            # 받아온 새 데이터를 캐시에 저장
            set_cached_data(client_code, full_data)
        except Exception as e:
            return f"데이터베이스 동기화 오류 (A2A Timeout): {str(e)}", 500

    # 4. 뷰(View) 모드에 따른 동적 템플릿 렌더링
    # 고유 발급된 client_secret을 secret_code 변수에 담아 HTML로 쏴줍니다.
    
    if view_mode == 'v01':
        return render_template(
            'dashboard_v01.html',
            client_code=code_param,
            target=target_project,
            data=full_data.get('v01_projects', {}),
            secret_code=client_secret,        # 고객사 맞춤 보안 코드 주입
            master_db_api_url=MASTER_DB_API_URL
        )
        
    elif view_mode == 'v02':
        return render_template(
            'dashboard_v02.html',
            client_code=code_param,
            target=target_project,
            data=full_data.get('v02_projects', {}),
            secret_code=client_secret,        # 고객사 맞춤 보안 코드 주입
            master_db_api_url=MASTER_DB_API_URL
        )
        
    else:
        # 메인 대시보드
        return render_template(
            'dashboard_main.html',
            client_code=code_param,
            data=full_data,
            secret_code=client_secret,        # 고객사 맞춤 보안 코드 주입
            master_db_api_url=MASTER_DB_API_URL
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)