import streamlit as st
import json
import os
import requests
import time
import base64 # 상단 필수 임포트 유지
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv  # 👈 [신규 추가 1] 환경변수 로더 임포트
load_dotenv()                   # 👈 [신규 추가 2] .env 파일 읽기 실행

# .env에서 구글 Apps Script 마스터 웹 앱 URL 로드
MASTER_DB_API_URL = os.getenv("MASTER_DB_API_URL")

# 👈 [인프라 제어 신규 추가] .env 파일에서 Tailscale 고정 가상 IP 기반의 에이전트 주소 로드
SERVER_AGENT_URL = os.getenv("SERVER_AGENT_URL")

# ==========================================
# 📂 [파일 경로 설정] 다양한 큐(Queue) 메모리 파일
# ==========================================
QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")                 # Tab 1: 문서 결재용
AGENT_QUEUE_FILE = os.path.join(os.getcwd(), "hitl_approval_queue.json")# Tab 2: Agent 능동 리포팅용 (Phase 2 신규)
PRICE_QUEUE_FILE = os.path.join(os.getcwd(), "price_queue.json")        # Tab 3: 원가 변동용

# ==========================================
# 🛠️ [코어 함수] 큐 데이터 입출력 (I/O)
# ==========================================
def load_json_queue(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
             return []
    return []

def save_json_queue(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 호환성을 위한 기존 래퍼 함수 유지
def load_queue(): return load_json_queue(QUEUE_FILE)
def save_queue(data): save_json_queue(QUEUE_FILE, data)
def load_price_queue(): return load_json_queue(PRICE_QUEUE_FILE)
def save_price_queue(data): save_json_queue(PRICE_QUEUE_FILE, data)
def load_agent_queue(): return load_json_queue(AGENT_QUEUE_FILE)
def save_agent_queue(data): save_json_queue(AGENT_QUEUE_FILE, data)

# ==========================================
# [메이커몬 HITL 통제 센터] 발주서 수동 조립 모듈
# ==========================================
def get_mock_vendor_data(vendor_code):
    vendors = {"PRE-001": {"name": "프리시전(가칭)", "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"}}
    return vendors.get(vendor_code, {"name": "미상", "payment_condition": "협의 필요"})

def generate_po_json(project_code, vendor_code, total_qty, due_date, cond_label, cond_text):
    vendors = {
        "PRE-001": {"name": "프리시전(가칭)", "biz_no": "123-45-67890", "address": "경기도 시흥시 산기대학로 123", "ceo": "김정밀", "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"}
    }
    v_info = vendors.get(vendor_code, {"name": "미상", "biz_no": "", "address": "", "ceo": "", "payment_condition": ""})
    
    po_data = {
        "doc_no": f"MK-PO-{datetime.now().strftime('%Y%m%d')}-01",
        "vendor_name": v_info["name"], "vendor_biz_no": v_info["biz_no"], "vendor_address": v_info["address"], "vendor_ceo": v_info["ceo"],
        "po_title": f"{project_code} AI Robot 양산 제작 발주", "po_date": datetime.now().strftime("%Y-%m-%d"),
        "po_details": f"기구물 파츠 외 (하단 표 참조)", "due_date": due_date.strftime("%Y-%m-%d"),
        "total_amount": "₩ 80,200,000", "manage_no": f"{project_code}", "attachment": "제작도면 (STEP 파일 포함)",
        "payment_condition": v_info["payment_condition"], "condition_label": cond_label, "condition_content": cond_text,
        "po_items": [
            {"project_manage_no": f"{project_code}\n(Ver.정방향)", "model_no": "TOP Ass'y", "qty": "60 SET", "price": "₩ 51,600,000"},
            {"project_manage_no": f"{project_code}\n(Ver.대칭)", "model_no": "BOTTOM Ass'y", "qty": "20 SET", "price": "₩ 17,200,000"}
        ]
    }
    return po_data

# ==========================================
# [Phase 2.5 신규] AI 견적용 통신 및 추론 엔진 함수
# ==========================================
def fetch_factory_data(action, project_code=None):
    payload = {"action": action}
    if project_code:
        payload["project_code"] = project_code
        
    try:
        response = requests.post(MASTER_DB_API_URL, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json().get("data", [])
    except Exception as e:
        st.error(f"통신 에러: {e}")
    return []

# ==========================================
# [구글 정책 우회 마이그레이션 완료] AI 지능형 견적 추론 엔진
# ==========================================
def generate_ai_bom_draft(project_code):
    """
    [공학적 마이그레이션 핵심 주석]
    구글 정책 변화에 대응하여, 코드 수정 없이 .env 파일에서 GEMINI_MODEL_NAME 변경만으로
    최신형 3.5 Flash 엔진 등으로 즉시 무중단 원격 스위칭되도록 연동 설계를 완료했습니다.
    """
    history_data = fetch_factory_data("get_history")
    new_parts = fetch_factory_data("get_new_parts", project_code)
     
    if not new_parts:
        return None, "해당 프로젝트 코드의 신규 부품 데이터를 찾을 수 없습니다."
        
    project_id = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")
    
    # 💡 [신규 연동] .env에서 모델명을 유동적으로 스캔 (설정 누락 시 기본값으로 최신형 gemini-3.5-flash 가동)
    target_model = os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash")
    
    # 구글 클라우드 IAM 보안 권한인 ADC 기반의 엔터프라이즈 클라이언트 초기화 체계 유지
    client = genai.Client(vertexai=True, project=project_id, location="us-central1")
    
    system_instruction = """
    당신은 메이커몬의 수석 제조 PM입니다.
    제공된 [과거 BOM 데이터]를 학습하여 [신규 부품 리스트]에 대한 예상 견적을 산출하세요.
    [필수 고려 사항]
    - 재질과 부품명의 유사성을 최우선으로 비교할 것.
    - MOQ(소요량)에 따른 단가 최적화(수량이 많으면 단가 인하)를 반영할 것.
    - 후처리 명칭이 포함된 경우 공정비를 가산할 것.
    [출력 포맷] 반드시 아래 키를 가진 JSON 배열로만 답변하세요.
    [{"projectCode": "...", "assembly": "...", "category": "...", "partName": "...", "partNo": "...", "qty": 숫자, "vendorCost": 숫자, "reasoning": "추론 근거"}]
    """
    
    user_prompt = f"""
    [과거 BOM 데이터]
    {json.dumps(history_data[:30], ensure_ascii=False)} 
    
    [신규 부품 리스트]
    {json.dumps(new_parts, ensure_ascii=False)}
    
    위 데이터를 바탕으로 신규 프로젝트 {project_code}의 BOM 초안을 JSON 배열로 작성해줘.
    """

    try:
        response = client.models.generate_content(
            model=target_model, # 👈 동적 환경 변수 기반 스위칭 매킹 완료
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2, 
                response_mime_type="application/json" 
            )
        )
        return json.loads(response.text), "성공"
    except Exception as e:
        return None, f"AI 추론 에러: {str(e)}"

# ==========================================
# [Phase 2 신규] 고객 챗봇 & 카카오톡 Push 발송 브릿지
# ==========================================
def send_proactive_push(client_code, message):
    """
    대표님이 승인한 메시지를 Master DB(API.gs)로 전송합니다.
    API.gs는 이 데이터를 Inquire_Logs에 기록하고 카카오톡 알림톡을 발송합니다.
    (GCP VPC 외부 송신 차단 규칙 준수)
    """
    payload = {
        "action": "send_push",
        "client_code": client_code,  # 예: "BH"
        "sender": "PM_Agent",
        "message": message,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        # Zero Trust: MASTER_DB_API_URL은 .env에서 호출된 안전한 주소입니다.
        response = requests.post(MASTER_DB_API_URL, json=payload, timeout=10)
        if response.status_code == 200:
            return True, response.json().get("message", "발송 성공")
        else:
            return False, f"서버 통신 오류: {response.status_code}"
    except Exception as e:
        return False, f"네트워크 에러: {str(e)}"

def inject_bom_to_sheet(bom_items):
    payload = {
        "action": "inject_bom",
        "bom_items": bom_items
    }
    try:
        response = requests.post(MASTER_DB_API_URL, json=payload, timeout=15)
        if response.status_code == 200:
            return True, response.json().get("message", "성공")
        return False, f"서버 에러: {response.status_code}"
    except Exception as e:
        return False, str(e)


# ==========================================
# 📊 [Phase 3 신규 추가] 10초 주기 독립형 인프라 텔레메트리 렌더러
# ==========================================
@st.fragment(run_every=10)
def render_isolated_telemetry():
    """
    [공학적 설계 핵심 주석]
    @st.fragment 데코레이터를 지정하여, 10초 주기로 수집되는 하드웨어 데이터가
    전체 Streamlit 대시보드 화면을 리프레시(st.rerun)하지 않도록 '격리 루프'를 형성합니다.
    덕분에 대표님이 다른 탭에서 텍스트 입력을 하는 도중에도 폼 내용이 지워지지 않고 실시간 유지됩니다.
    """
    try:
        # Muscle 2 에이전트의 /telemetry 엔드포인트에 1.5초 타임아웃 쿼리 전송
        response = requests.get(f"{SERVER_AGENT_URL}/telemetry", timeout=1.5)
        if response.status_code == 200:
            infra_data = response.json()
            status_indicator = "🟢 ONLINE (연동 완벽)"
        else:
            infra_data = {"cpu_temp": 0.0, "gpu_temp": 0.0, "gpu_power": 0.0, "gpu_fan": 0.0, "gpu_limit": 0.0}
            status_indicator = "🟡 AGENT RESPONSE ERROR"
    except:
        # 통신 장애 또는 서버 셧다운 상태일 경우 안전 프로필 대입
        infra_data = {"cpu_temp": 0.0, "gpu_temp": 0.0, "gpu_power": 0.0, "gpu_fan": 0.0, "gpu_limit": 0.0}
        status_indicator = "🔴 OFFLINE (서버 동면 또는 에이전트 미가동)"

    st.markdown(f"#### 📡 Muscle 2 텔레메트리 실시간 상태: **{status_indicator}**")
    
    # 대표님 관제 가독성을 위한 4단 스펙 게이지 카드 매트릭스 렌더링
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.metric(label="🌡️ 라이젠 CPU 온도", value=f"{infra_data['cpu_temp']} °C")
    with g2:
        st.metric(label="🔥 RTX 4000 Ada 온도", value=f"{infra_data['gpu_temp']} °C")
    with g3:
        st.metric(label="⚡ 실시간 전력 사용량", value=f"{infra_data['gpu_power']} W")
    with g4:
        st.metric(label="🌀 그래픽카드 팬 속도", value=f"{infra_data['gpu_fan']} %")
        
    st.write(f"현재 하드웨어 전력 리미트 스펙: **{infra_data['gpu_limit']} W** (최종 동기화: {datetime.now().strftime('%H:%M:%S')})")


# ==========================================
# [Streamlit UI 프론트엔드]
# ==========================================
st.set_page_config(page_title="메이커몬 HITL 대시보드", page_icon="🏭", layout="wide")
st.title("🏭 메이커몬 HITL 중앙 관제 대시보드 (6-Pillar Hub)")

# 🚨 5기둥(Pillar)에서 6기둥으로 탭 레이아웃 완벽 확장 (Tab 6 인프라 관제 기둥 신규 추가 결합)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 8종 문서 통합 승인", 
    "🤖 능동형 Agent 리포팅", 
    "💰 원가 혁신 관제",
    "🧠 AI 지능형 BOM 초안",
    "👁️ 품질/수량 검수 (AI-Ready)", # 👈 [Phase 2 신규 탭]
    "🖥️ 서버 인프라 관제 (WebMCP)"   # 👈 [Phase 3 하이브리드 제어 센터 탭 탑재]
])

# ------------------------------------------
# [탭 1] 8종 문서 통합 승인 관제탑 (기존 로직 및 주석 완벽 보존)
# ------------------------------------------
with tab1:
    st.subheader("문서 자동화 렌더링 및 메일 라우팅 승인")
    
    col_title, col_refresh = st.columns([8, 2])
    with col_refresh:
        if st.button("🔄 문서 대기열 새로고침", use_container_width=True):
            st.rerun()

    queue_items = load_queue()

    if not queue_items:
        st.info("현재 승인 대기 중인 문서가 없습니다.")
    else:
        for item in queue_items:
            item_id = item.get('id')
            preview_key = f"preview_pdf_{item_id}"
            
            with st.expander(f"📦 {item.get('doc_no', 'N/A')} | {item.get('vendor_name', 'N/A')} | {item.get('total_amount', 'N/A')}", expanded=True):
                
                # [신규 추가] 상단 정보 및 삭제 버튼 배치
                col_info, col_del = st.columns([8, 2])
                with col_info:
                     st.write(f"**관리 번호:** {item.get('manage_no', 'N/A')} / **수신 일시:** {item.get('received_at', 'N/A')}")
                with col_del:
                    if st.button("🗑️ 대기열 삭제", key=f"del_{item_id}", use_container_width=True):
                        updated_queue = [q for q in queue_items if q.get('id') != item_id]
                        save_queue(updated_queue)
                        if preview_key in st.session_state:
                            del st.session_state[preview_key]
                        st.rerun()
                
                st.divider()
                
                # --------------------------------------------------
                # [Step 1] PDF 미리보기 렌더링 로직
                # --------------------------------------------------
                if preview_key not in st.session_state:
                    if st.button(f"🔍 문서 미리보기 생성 (PDF)", key=f"btn_prev_{item_id}"):
                        with st.spinner("렌더링 엔진 가동 중... (발송되지 않습니다)"):
                            try:
                                PREVIEW_URL = "http://localhost:5000/api/v1/generate/preview"
                                res = requests.post(PREVIEW_URL, json=item, timeout=15)
                                
                                if res.status_code == 200:
                                    st.session_state[preview_key] = res.content
                                    st.rerun()
                                else:
                                    st.error("❌ 미리보기 생성 실패 (LibreOffice Daemon 실행 여부를 확인하세요)")
                            except Exception as e:
                                 st.error(f"❌ 통신 오류: {e}")
                
                # --------------------------------------------------
                # [Step 2] PDF 검수 및 이메일 수정/발송 로직
                # --------------------------------------------------
                else:
                    st.success("✅ 미리보기 렌더링 완료. 문서를 검토해 주세요.")
                    
                    # 1) 내장 PDF 뷰어 출력
                    base64_pdf = base64.b64encode(st.session_state[preview_key]).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                    
                    st.divider()
                    
                    # 2) 이메일 초안 수정 UI
                    st.markdown("### 📧 이메일 발송 초안 검토")
                    default_subj = f"[메이커몬] {item.get('vendor_name', '협력사')} 귀하께 양산 제작 발주서를 전송합니다."
                    default_body = f"안녕하세요 {item.get('vendor_name', '협력사')} 담당자님,\n\n메이커몬 발주서 송부드립니다. 이상이 없을 시 진행 부탁드립니다.\n\n감사합니다."
                    
                    custom_subject = st.text_input("이메일 제목", value=default_subj, key=f"subj_{item_id}")
                    custom_body = st.text_area("이메일 본문", value=default_body, height=100, key=f"body_{item_id}")

                    # 3) 최종 승인 및 라우팅 버튼
                    col_cancel, col_send = st.columns([1, 4])
                    
                    with col_cancel:
                        if st.button("닫기 및 재검토", key=f"cancel_{item_id}"):
                             del st.session_state[preview_key]
                             st.rerun()
                            
                    with col_send:
                        if st.button(f"🚨 최종 승인 및 문서 발송", type="primary", key=f"approve_{item_id}"):
                            with st.spinner("최종 문서 렌더링, 라우팅 및 메일 발송 중..."):
                                try:
                                    if MASTER_DB_API_URL:
                                        try:
                                             project_code_prefix = item.get('manage_no', '').split('-')[0]
                                             apps_script_payload = {"action": "route_to_secure_folder", "project_code": project_code_prefix, "doc_no": item.get('doc_no', ''), "folder_target": "[B_협력사_보안용]"}
                                             requests.post(MASTER_DB_API_URL, json=apps_script_payload, timeout=5)
                                        except: pass

                                    flask_payload = item.copy()
                                    flask_payload["Is_Approved"] = True  
                                    flask_payload["email_subject"] = custom_subject 
                                    flask_payload["email_body"] = custom_body       
                                    
                                    SEND_URL = "http://localhost:5000/api/v1/generate/send"
                                    res_send = requests.post(SEND_URL, json=flask_payload, timeout=30)
                                    
                                    if res_send.status_code == 200:
                                        updated_queue = [q for q in queue_items if q.get('id') != item_id]
                                        save_queue(updated_queue)
                                        del st.session_state[preview_key]
                                        st.toast("🚀 문서 렌더링 및 메일 발송 완벽 완료!", icon="✅")
                                        time.sleep(1.5)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 발송 실패: {res_send.status_code}")
                                        
                                except Exception as e:
                                    st.error(f"❌ 통신 오류: {e}")

# ------------------------------------------
# [탭 2] 능동형 Agent 리포팅 (Phase 2 신규 추가)
# ------------------------------------------
with tab2:
    st.subheader("Agent 1 (PM) 능동형 고객 알림 발송 관제")
    st.markdown("watchdog 데몬이 감지하고 압축한 도면/시트 변동 사항을 검토 후, 챗봇으로 푸시(Push) 알림을 보냅니다.")
    
    if st.button("🔄 리포팅 대기열 새로고침", key="btn_refresh_agent"):
        st.rerun()

    agent_queue = load_agent_queue()

    if not agent_queue:
        st.success("✅ 현재 대기 중인 Agent 1의 고객 알림 초안이 없습니다.")
    else:
        st.warning(f"🚨 승인 대기 중인 고객 발송용 알림이 {len(agent_queue)}건 있습니다.")

        for idx, item in enumerate(agent_queue):
             dt_object = datetime.fromtimestamp(item.get("timestamp", time.time()))
             time_str = dt_object.strftime("%Y-%m-%d %H:%M:%S")

             with st.expander(f"📥 [대기열 #{idx+1}] {time_str} 시스템 변동 감지 건", expanded=True):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown("### 🤖 Agent 작성 푸시 알림 초안 (직접 수정 가능)")
                    
                    draft_text = f"[{item.get('agent', 'PM_Agent')}] 고객님, 프로젝트에 새로운 변동 사항이 업데이트되었습니다.\n\n"
                    if item.get("detected_files"):
                         draft_text += f"📂 신규 도면 및 파일 감지:\n- {', '.join(item['detected_files'])}\n\n"
                    if item.get("db_events"):
                        draft_text += f"📊 시스템 DB 변동 감지:\n- {len(item['db_events'])}건의 시스템 이벤트 처리됨\n\n"
                    
                    draft_text += "엔지니어 관제탑에서 내용을 최종 확인하였으며, 대시보드(V01/V02)에 실시간 동기화되었습니다."

                    edited_message = st.text_area("고객의 하이브리드 앱/카카오톡으로 발송될 최종 메시지", value=draft_text, height=180, key=f"agent_msg_{idx}")

                with col2:
                    st.markdown("### 🔍 감지 상세 데이터 (근거)")
                    st.json({
                        "트리거 소스": item.get("trigger_source", "Watchdog & Webhook"),
                        "도면 파일": item.get("detected_files", []),
                        "DB 이벤트": item.get("db_events", [])
                     })

                st.markdown("---")
                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

                if btn_col1.button("✅ 승인 및 발송 (Approve)", key=f"agent_approve_{idx}", type="primary", use_container_width=True):
                    target_client_code = item.get("client_code", "BH")
                    
                    with st.spinner("Master DB 기록 및 카카오톡 Push 발송 중..."):
                         success, result_msg = send_proactive_push(target_client_code, edited_message)
                        
                         if success:
                             agent_queue.pop(idx)
                             save_agent_queue(agent_queue)
                            
                             st.success(f"🚀 승인 완료! [{target_client_code}] 고객의 카카오톡 및 챗봇으로 푸시 발송되었습니다. (새로고침 중...)")
                             time.sleep(1.5)
                             st.rerun()
                         else:
                              st.error(f"❌ 발송 실패: {result_msg}\n시스템을 점검해 주세요.")

                if btn_col2.button("❌ 반려 및 폐기 (Reject)", key=f"agent_reject_{idx}", use_container_width=True):
                    agent_queue.pop(idx)
                    save_agent_queue(agent_queue)
                    st.info("🗑️ 반려되었습니다. 해당 알림은 외부로 발송되지 않고 안전하게 폐기되었습니다.")
                    time.sleep(1.5)
                    st.rerun()

# ------------------------------------------
# [탭 3] 원가 혁신 관제 (기존 로직 유지)
# ------------------------------------------
with tab3:
    st.subheader("단가 변동 승인 대기열")
    if st.button("🔄 단가 대기열 새로고침", key="btn_refresh_price"):
        st.rerun()

    price_queue = load_price_queue()
    
    if not price_queue:
         st.info("현재 승인 대기 중인 원가 변동 내역이 없습니다.")
    else:
        for idx, log in enumerate(price_queue):
            with st.container(border=True):
                st.warning(f"🚨 [변동 감지] 식별코드: **{log.get('projectCode', 'N/A')}** / 파트: **{log.get('partName', 'N/A')}**")
                st.write(f"📉 변동률: **{log.get('changeRate', 'N/A')}** (이전가: {log.get('oldPrice', 'N/A')} ➡️ 현재가: {log.get('newPrice', 'N/A')})")
        
                comment = st.text_input("고객 송출용 엔지니어 코멘트 입력 (필수)", key=f"comment_{idx}")
                
                if st.button("✅ 아임웹 타임라인 발행 승인", key=f"pub_{idx}"):
                    if not comment:
                         st.error("코멘트를 입력해야 발행할 수 있습니다.")
                    else:
                        st.success(f"[{comment}] 사유가 아임웹으로 송출되었습니다!")
                        price_queue.pop(idx)
                        save_price_queue(price_queue)
                        st.rerun()

# ------------------------------------------
# [탭 4] AI 견적 대기열 (기존 로직 유지)
# ------------------------------------------
with tab4:
    st.subheader("🤖 AI 지능형 BOM 초안 자동 생성")
    st.info("과거 비용 패턴을 학습하여 신규 프로젝트의 BOM 초안과 예상 원가를 제안합니다.")

    # [스텝 1] 프로젝트 코드 입력 및 AI 실행
    with st.container(border=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            target_project_code = st.text_input("견적 산출 프로젝트 코드 (예: BH05V01)")
            generate_btn = st.button("🚀 AI 지능형 견적 실행")

    if generate_btn and target_project_code:
        with st.spinner("AI가 구글 시트의 과거 데이터를 분석하여 단가를 추론하고 있습니다..."):
            ai_draft_data, msg = generate_ai_bom_draft(target_project_code)
            
            if ai_draft_data:
                st.session_state['ai_bom_draft'] = ai_draft_data
                st.success("🎉 AI 견적 초안 생성이 완료되었습니다!")
            else:
                st.error(f"❌ 초안 생성 실패: {msg}")

    # [스텝 2] 데이터 에디터를 통한 HITL(Human-in-the-Loop) 미세 조정
    if 'ai_bom_draft' in st.session_state:
        st.markdown("### 📝 견적 초안 검토 및 미세 조정 (HITL)")
        st.markdown("아래 표에서 AI가 산출한 `vendorCost`(협력사 원가)를 대표님의 판단에 따라 직접 클릭하여 수정할 수 있습니다. 스크롤하여 우측의 `reasoning`(추론 근거)을 확인하세요.")
        
        edited_df = st.data_editor(
            st.session_state['ai_bom_draft'], 
            num_rows="dynamic", 
            use_container_width=True,
            key="ai_bom_editor"
        )
         
        # [스텝 3] 확정 및 주입
        if st.button("✅ 최종 승인 및 BOM_Master 주입 (DB 기록)"):
            with st.spinner("Sub DB로 확정 데이터를 전송하여 시트를 채우고 있습니다..."):
                success, inject_msg = inject_bom_to_sheet(edited_df)
                
                if success:
                    st.success(f"🎉 {inject_msg}")
                    del st.session_state['ai_bom_draft'] # 뷰 초기화
                    st.rerun()
                else:
                     st.error(f"❌ 데이터 주입 실패: {inject_msg}")
                    
# ------------------------------------------
# [탭 5] 품질/수량 수동 검수 (AI-Ready JSON 규격 변환기)
# ------------------------------------------
with tab5:
    st.subheader("👁️ 현장 품질 및 수량 검수 (AI-Ready 변환기)")
    st.markdown("엔지니어가 수동으로 입력한 검수 결과를 **미래의 Vision AI 로봇이 전송할 JSON 표준 규격**으로 변환하여 Sub DB에 적재합니다.")
    st.divider()

    col_input, col_json = st.columns([1.2, 1])

    with col_input:
        st.markdown("### 📝 검수 데이터 입력 (Human Input)")
        
        with st.container(border=True):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                insp_project_code = st.text_input("프로젝트 식별코드", value="BH03V02", key="insp_code")
            with col_p2:
                insp_part_id = st.text_input("부품명 / 품번", placeholder="예: TOP-ASSY-01", key="insp_part")
            
            insp_image = st.file_uploader("📸 현장 조립/검수 사진 업로드 (선택)", type=['jpg', 'png', 'jpeg'])
        
            st.markdown("#### 📊 수량 및 판정")
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                insp_ok_qty = st.number_input("✅ 양품(OK) 수량", min_value=0, value=100, step=1)
            with col_q2:
                insp_ng_qty = st.number_input("❌ 불량(NG) 수량", min_value=0, value=0, step=1)
            
            insp_total_qty = insp_ok_qty + insp_ng_qty
            
            insp_status = "OK" if insp_ng_qty == 0 else "NG_DETECTED"
            insp_error_type = "없음 (전량 양품)"
            
            if insp_status == "NG_DETECTED":
                insp_error_type = st.selectbox(
                    "불량 사유 분류",
                    options=["치수 오차 (공차 초과)", "표면 스크래치/찍힘", "조립 불량 (간섭 발생)", "후처리(아노다이징 등) 불량", "기타 수기 입력"]
                )
                if insp_error_type == "기타 수기 입력":
                    insp_error_type = st.text_input("상세 불량 사유 입력")
                    
            insp_comment = st.text_area("엔지니어 특이사항 코멘트", placeholder="예: 치수 불량 파츠는 재가공 지시 완료함.")

    with col_json:
        st.markdown("### 🤖 전송 대기 JSON (AI-Ready Format)")
        st.info("이 규격은 향후 Dark Factory의 비전 검수 로봇이 백엔드로 쏘아 올릴 페이로드와 100% 동일합니다.")
        
        # 💡 [문법오류 해결] 딕셔너리 내부의 불필요한 walrus(:=) 연산 기호 오타를 완전히 걷어내어 정상 할당 처리했습니다.
        ai_ready_payload = {
             "action": "submit_quality_inspection",
            "project_code": insp_project_code.strip().upper(),
            "inspection_data": [
                {
                    "part_id": insp_part_id,
                    "total_qty": insp_total_qty,
                    "ok_qty": insp_ok_qty,
                    "ng_qty": insp_ng_qty,
                    "status": insp_status,
                    "error_type": insp_error_type, # 👈 오타 수정 완료
                    "inspector": "Human_Engineer_Proxy",
                    "comment": insp_comment,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ]
        }
        
        st.json(ai_ready_payload)
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🚀 검수 완료 및 DB 전송 (Sub DB 동기화)", type="primary", use_container_width=True):
            if not insp_project_code or not insp_part_id:
                st.error("프로젝트 식별코드와 부품명을 정확히 입력해 주세요.")
            else:
                with st.spinner("구글 Sub DB(Stock_Live 및 Project_Log)에 검수 데이터를 주입 중입니다..."):
                    try:
                         response = requests.post(MASTER_DB_API_URL, json=ai_ready_payload, timeout=10)
                        
                         if response.status_code == 200:
                            res_data = response.json()
                            if res_data.get("status") == "success":
                                st.success("🎉 데이터 적재 성공! 아임웹 V02 대시보드의 생산 수량과 불량률이 즉시 동기화됩니다.")
                                st.toast("✅ 수동 검수 데이터 AI 규격 변환 및 DB 적재 완료")
                            else:
                                  st.error(f"❌ DB 적재 실패: {res_data.get('message', '알 수 없는 오류')}")
                         else:
                            st.error(f"❌ 서버 통신 오류 (HTTP {response.status_code})")
                    except Exception as e:
                          st.error(f"❌ 네트워크 연결 실패: {str(e)}")


# ------------------------------------------
# [탭 6] 인프라 실시간 관제 및 하이브리드 제어 (WebMCP)
# ------------------------------------------
with tab6:
    st.subheader("🖥️ 로컬 AI 인프라 자원 및 하이브리드 제어 (Pillar 6)")
    st.markdown("Tailscale 가상 메시 VPN 암호화 터널을 통해 Muscle 2 하드웨어 자원을 무인 통제합니다.")
    st.divider()

    # 10초 독립 루프 프래그먼트 실시간 렌더링 호출
    render_isolated_telemetry()
    
    st.divider()

    # ==================================================
    # 💡 [양방향 상태 동기화 피드백 반영 핵심 주석]
    # 라디오 버튼을 그리기 전에 서버의 실제 'gpu_limit' 값을 1회 즉시 조회합니다.
    # 만약 서버가 50W(ECO) 상태라면 기본 인덱스를 1로, 90W(PROD)라면 0으로 능동 세팅하여
    # 화면을 새로 켤 때도 현재 작동 중인 물리 모드가 체크박스에 정확히 일치하여 마킹되도록 잠금을 맵핑합니다.
    # ==================================================
    try:
        init_res = requests.get(f"{SERVER_AGENT_URL}/telemetry", timeout=1.0)
        if init_res.status_code == 200:
            current_limit = init_res.json().get("gpu_limit", 90.0)
        else:
            current_limit = 90.0
    except:
        current_limit = 90.0

    # 전력 수치값 매핑을 통한 기본 체크 박스 인덱스 자동 추론
    if current_limit == 50.0:
        default_radio_index = 1  # ECO 모드로 기본 체크 락 주입
    else:
        default_radio_index = 0  # PROD 모드로 기본 체크 락 주입

    # ----------------------------------------------------
    # 기존 [탭 6] 하단 'HITL 가동 모드 원격 제어' 부분을 아래 코드로 대체합니다.
    # ----------------------------------------------------
    st.markdown("### 🕹️ HITL 가동 모드 원격 제어")
    
    selected_mode = st.radio(
        "변경할 시스템 운전 프로필을 선택하십시오:",
        ("PROD 모드 [업무 시간 - 90W 전력 해제 및 CPU 가속]", 
         "ECO 모드 [심야/새벽 - 50W 압착 저전력 소모 서행]", 
         "⚡ SHUTDOWN [주말 벙커 모드 - 시스템 완전 종료]"),
        index=default_radio_index
    )

    mode_key = "PROD" if "PROD" in selected_mode else "ECO" if "ECO" in selected_mode else "SHUTDOWN"
    
    # 💡 [스트림릿 상태 버그 완전 해결] 
    # SHUTDOWN 선택 시, 안전 가드레일 체크박스를 동기화 버튼 '바깥'에 선제 렌더링하여 세션 꼬임을 방지합니다.
    confirm_shutdown = False
    if mode_key == "SHUTDOWN":
        st.warning("⚠️ 경고: 서버가 완전 셧다운되면 원격으로 다시 깨울 수 없습니다. 정말 진행하시겠습니까?")
        confirm_shutdown = st.checkbox("네, 메이커몬 공장 인프라 심장을 멈추는 것에 동의합니다.", key="strict_shutdown_lock")

    if st.button("🔄 모드 제어 프로필 시스템 동기화 투하", type="primary"):
        if mode_key == "SHUTDOWN":
            if confirm_shutdown:
                with st.spinner("Muscle 2 인프라 완전 셧다운 명령 송신 중..."):
                    try:
                        # 1초 뒤 서버 하드웨어를 완전 정지시키는 API 커널 다이렉트 호출
                        res = requests.post(f"{SERVER_AGENT_URL}/control", json={"mode": "SHUTDOWN"}, timeout=5)
                        st.error("🔥 SHUTDOWN 명령 완료. 서버 가동이 정지됩니다.")
                    except Exception as e:
                        st.error("서버가 안전 종료 단계에 진입하여 가상 터널이 끊어졌습니다. (정상적인 현상)")
            else:
                st.info("안전 잠금 장치가 발동되었습니다. 확인 체크박스를 체크한 후 실행해 주세요.")
        else:
            with st.spinner(f"Muscle 2 인프라로 {mode_key} 모드 제어 신호 송신 중..."):
                try:
                    res = requests.post(f"{SERVER_AGENT_URL}/control", json={"mode": mode_key}, timeout=5)
                    if res.status_code == 200:
                        st.success(f"✅ 동기화 완벽 완료: {res.json().get('message')}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ 에이전트 제어 실패 (HTTP {res.status_code})")
                except Exception as e:
                    st.error(f"❌ 제어 명령 통신 실패: {str(e)}")