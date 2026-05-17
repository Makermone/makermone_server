import streamlit as st
import json
import os
import requests
import time
import base64 # 상단에 필수 임포트
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv  # 👈 [신규 추가 1] 환경변수 로더 임포트
load_dotenv()                   # 👈 [신규 추가 2] .env 파일 읽기 실행

# .env에서 구글 Apps Script 마스터 웹 앱 URL 로드 (수정됨)
MASTER_DB_API_URL = os.getenv("MASTER_DB_API_URL")

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

def generate_ai_bom_draft(project_code):
    history_data = fetch_factory_data("get_history")
    new_parts = fetch_factory_data("get_new_parts", project_code)
    
    if not new_parts:
        return None, "해당 프로젝트 코드의 신규 부품 데이터를 찾을 수 없습니다."
        
    project_id = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")
    client = genai.Client(vertexai=True, project=project_id, location="us-central1")
    
    system_instruction = """
    당신은 메이커몬의 수석 제조 PM입니다. 제공된 [과거 BOM 데이터]를 학습하여 [신규 부품 리스트]에 대한 예상 견적을 산출하세요.
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
            model="gemini-2.5-flash",
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
# [Streamlit UI 프론트엔드]
# ==========================================
st.set_page_config(page_title="메이커몬 HITL 대시보드", page_icon="🏭", layout="wide")
st.title("🏭 메이커몬 HITL 중앙 관제 대시보드 (4-Pillar)")

# 🚨 4기둥(Pillar)으로 탭 레이아웃 재편성
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 8종 문서 승인", 
    "🤖 능동형 Agent 리포팅", # Phase 2 신규 탭
    "💰 원가 혁신 관제", 
    "🧠 AI 지능형 BOM 초안"
])

# ------------------------------------------
# [탭 1] 8종 문서 통합 승인 관제탑 (기존 로직 유지)
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
                    # 💡 임시 방편: 큐 데이터에 client_code가 없다면 프로젝트 코드 등에서 추출하거나 기본값 세팅
                    # 실제 환경에서는 watchdog이 변동 폴더명(예: BH03V01)에서 앞 2자리(client_code)를 추출하여 큐에 넣어두어야 합니다.
                    target_client_code = item.get("client_code", "BH") 
                    
                    with st.spinner("Master DB 기록 및 카카오톡 Push 발송 중..."):
                        # 1. 챗봇 및 카카오톡으로 전송 (Master DB 릴레이)
                        success, result_msg = send_proactive_push(target_client_code, edited_message)
                        
                        if success:
                            # 2. 큐 리스트에서 항목 제거 및 저장
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
        
        # 엑셀처럼 화면에서 직접 셀을 더블클릭해서 수정할 수 있는 마법의 위젯
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