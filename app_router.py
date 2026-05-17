import os
import time
import requests
import json
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드 (Zero Trust 보안 원칙 적용)
load_dotenv()

app = Flask(__name__)

# 기존 명칭(MASTER_DB_API_URL) 유지
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
# 🛡️ [Phase 2] 백엔드 재무 연산 및 영업비밀 격리 (Information Isolation)
# =========================================================================
def process_financial_data_and_isolate(full_data):
    """
    [절대 규칙] 프론트엔드(JS)에서 원가 계산 금지. 파이썬이 1원 단위까지 직접 계산.
    협력사용 민감 데이터(원가 상세 등)를 고객사 렌더링 전 완벽히 필터링(블라인드).
    """
    if not full_data:
        return full_data

    # V02 양산 프로젝트 백엔드 사전 연산
    v02_projects = full_data.get('v02_projects', {})
    for p_code, p_data in v02_projects.items():
        total_production_cost = 0
        
        # 1. BOM(파츠마스터) 기반 총 생산원가(L열) 누적 계산
        if 'bom' in p_data and isinstance(p_data['bom'], list):
            for item in p_data['bom']:
                total_production_cost += item.get('unit_cost', 0)
                # 🚨 협력사 매입 원가 등 고객사에게 노출되면 안 되는 영업비밀 Key를 여기서 삭제 (격리)
                item.pop('vendor_secret_cost', None) 
        
        # 2. 백엔드 연산 결과 주입 (프론트엔드는 이 값을 그대로 출력만 함)
        p_data['calculated_total_production_cost'] = total_production_cost
        
        # 3. BEP 마진 시뮬레이션 데이터 사전 연산
        market_price = p_data.get('market_price', 0)
        if market_price > 0:
            margin = market_price - total_production_cost
            p_data['calculated_margin'] = margin
            p_data['calculated_margin_ratio'] = round((margin / market_price) * 100, 1) if market_price else 0
        else:
            p_data['calculated_margin'] = 0
            p_data['calculated_margin_ratio'] = 0
            
    full_data['v02_projects'] = v02_projects
    return full_data

# =========================================================================
# 🤖 [Phase 2] Agent 1 (PM) 능동형 Webhook 수신 엔드포인트
# =========================================================================
@app.route('/webhook/subdb', methods=['POST'])
def subdb_webhook_receiver():
    """
    구글 Sub DB(시트)에 변동 발생 시 Code.gs가 여기로 신호를 쏩니다.
    받은 데이터는 즉시 처리하지 않고, watchdog_daemon.py의 Agent 1 큐로 이관합니다.
    """
    try:
        payload = request.json
        # 수신된 웹훅 데이터를 Agent가 읽을 수 있도록 임시 큐 파일에 적재 (비동기 처리)
        queue_file = 'agent1_webhook_queue.json'
        
        existing_queue = []
        if os.path.exists(queue_file):
            with open(queue_file, 'r', encoding='utf-8') as f:
                existing_queue = json.load(f)
                
        payload['received_at'] = time.time()
        existing_queue.append(payload)
        
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(existing_queue, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": "Agent 1 이벤트 큐 적재 완료"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# =========================================================================
# 🚀 메이커몬 1-Page SPA 통합 라우터
# =========================================================================
@app.route('/app')
def makermon_spa_router():
    """
    [호출 예시] /app?code=BH&view=v01&target=BH03V01
    """
    # 1. 파라미터 파싱
    code_param = request.args.get('code', '').strip().upper()
    view_mode = request.args.get('view', 'main').lower()
    target_project = request.args.get('target', '')

    # 2. 1차 방어막: 명찰 길이 검증
    if len(code_param) < 2:
        return "보안 경고: 유효하지 않은 식별 코드입니다.", 403
    
    client_code = code_param[:2] # 예: "BH"

    # 🚨 2차 방어막: 고객사별 독립 보안 코드 매칭 (.env 환경변수 호출)
    client_secret = os.getenv(f"SECRET_{client_code}")
    
    if not client_secret:
        return "보안 경고: 등록되지 않은 고객사 시스템입니다.", 403

    # 🚨 3. 메모리 캐시 확인 (구글 요청 건너뛰기)
    full_data = get_cached_data(client_code)

    # 🚨 4. 캐시가 없거나 1분이 지났을 때만 Code.gs 호출 (서버 과부하 방지)
    if full_data is None:
        try:
            res = requests.get(f"{MASTER_DB_API_URL}?code={client_code}&req_type=data", timeout=10)
            res_json = res.json()
            raw_data = res_json.get('data', {}) if res.status_code == 200 else {}
            
            # 🛡️ 백엔드에서 1원 단위 재무 연산 및 영업비밀 필터링 선행 처리
            full_data = process_financial_data_and_isolate(raw_data)
            
            # 받아온 '정제된' 새 데이터를 캐시에 저장
            set_cached_data(client_code, full_data)
        except Exception as e:
            return f"데이터베이스 동기화 오류 (A2A Timeout): {str(e)}", 500

    # 5. 뷰(View) 모드에 따른 동적 템플릿 렌더링
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