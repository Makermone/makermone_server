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
# [기본 설정 및 데이터 로드]
# ==========================================
st.set_page_config(page_title="메이커몬 HITL 대시보드", layout="wide")

QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")
PRICE_QUEUE_FILE = os.path.join(os.getcwd(), "price_queue.json")

def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_queue(data):
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_price_queue():
    if os.path.exists(PRICE_QUEUE_FILE):
        with open(PRICE_QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_price_queue(data):
    with open(PRICE_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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
st.title("🏭 메이커몬 HITL 중앙 관제 대시보드")

tab1, tab2, tab3 = st.tabs([
    "📋 통합 승인 관제탑 (Auto)", 
    "💰 원가 혁신 관제", 
    "🤖 AI 견적 초안 대기열"
])

# ------------------------------------------
# [탭 1] 자동 대기열 관제 화면 (개별 삭제 기능 추가)
# ------------------------------------------
with tab1:
    st.subheader("8종 문서 통합 승인 관제탑")
    
    col_title, col_refresh = st.columns([8, 2])
    with col_refresh:
        if st.button("🔄 대기열 새로고침", use_container_width=True):
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
# [탭 2] 원가 혁신 관제 (신규 추가)
# ------------------------------------------
with tab2:
    st.subheader("단가 변동 승인 대기열")
    if st.button("🔄 대기열 새로고침", key="btn_refresh_price"):
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
                        # 승인 완료된 데이터 큐에서 제거
                        price_queue.pop(idx)
                        save_price_queue(price_queue)
                        st.rerun()

# ------------------------------------------
# [탭 3] AI 견적 대기열 (통합 완료)
# ------------------------------------------
with tab3:
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