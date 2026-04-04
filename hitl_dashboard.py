import streamlit as st
import json
import os
import requests
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv  # 👈 [신규 추가 1] 환경변수 로더 임포트
load_dotenv()                   # 👈 [신규 추가 2] .env 파일 읽기 실행

# .env에서 구글 Apps Script 웹 앱 URL 로드
SUB_DB_API_URL = os.getenv("SUB_DB_API_URL")

# ==========================================
# [기본 설정 및 데이터 로드]
# ==========================================
st.set_page_config(page_title="메이커몬 HITL 대시보드", layout="wide")

QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")
PRICE_QUEUE_FILE = os.path.join(os.getcwd(), "price_queue.json") # 원가 관제용 신규 큐

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
        "total_amount": "₩ 80,200,000", "manage_no": f"{project_code}-V02-PO", "attachment": "제작도면 (STEP 파일 포함)",
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
    """구글 Apps Script API를 통해 시트 데이터 호출"""
    payload = {"action": action}
    if project_code:
        payload["project_code"] = project_code
        
    try:
        response = requests.post(SUB_DB_API_URL, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json().get("data", [])
    except Exception as e:
        st.error(f"통신 에러: {e}")
    return []

def inject_bom_to_sheet(bom_items):
    """엔지니어가 승인한 최종 BOM을 시트에 주입"""
    payload = {
        "action": "inject_bom",
        "bom_items": bom_items
    }
    try:
        response = requests.post(SUB_DB_API_URL, json=payload, timeout=15)
        if response.status_code == 200:
            return True, response.json().get("message", "성공")
        return False, f"서버 에러: {response.status_code}"
    except Exception as e:
        return False, str(e)

def generate_ai_bom_draft(project_code):
    """Vertex AI를 통한 지능형 BOM 초안 생성"""
    history_data = fetch_factory_data("get_history")
    new_parts = fetch_factory_data("get_new_parts", project_code)
    
    if not new_parts:
        return None, "해당 프로젝트 코드의 신규 부품 데이터를 찾을 수 없습니다."

    # 신형 엔진 Gemini 2.5 Flash 호출 설정 (GCP 프로젝트 ID 필수)
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
                temperature=0.2, # 낮은 온도로 일관성 유지
                response_mime_type="application/json" # JSON 강제 출력
            )
        )
        return json.loads(response.text), "성공"
    except Exception as e:
        return None, f"AI 추론 에러: {str(e)}"

# ==========================================
# [Streamlit UI 프론트엔드]
# ==========================================
st.title("🏭 메이커몬 HITL 중앙 관제 대시보드")

# 4개의 탭으로 확장
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 발주서 렌더링 승인 (Auto)", 
    "⚙️ 수동 발주 테스트 (Manual)", 
    "💰 원가 혁신 관제", 
    "🤖 AI 견적 초안 대기열"
])

# ------------------------------------------
# [탭 1] 자동 대기열 관제 화면 (기존 동일)
# ------------------------------------------
with tab1:
    st.subheader("발주서 최종 승인 대기열")
    if st.button("🔄 대기열 새로고침", key="btn_refresh_1"):
        st.rerun()

    queue_items = load_queue()

    if not queue_items:
        st.info("현재 승인 대기 중인 발주서가 없습니다.")
    else:
        for item in queue_items:
            with st.expander(f"📦 {item.get('doc_no', 'N/A')} | {item.get('vendor_name', 'N/A')} | {item.get('total_amount', 'N/A')}", expanded=True):
                st.write(f"**관리 번호:** {item.get('manage_no', 'N/A')}")
                st.write(f"**수신 일시:** {item.get('received_at', 'N/A')}")
                
                pdf_link = item.get('pdf_url', '#')
                st.markdown(f"📄 **첨부파일 확인:** [발주서 PDF 파일 열기]({pdf_link})")
                
                if st.button(f"✅ 최종 승인 및 발송 ({item.get('doc_no', 'N/A')})", key=item.get('id', 'temp_key')):
                    with st.spinner("발송 중..."):
                        try:
                            deploy_url = "http://localhost:5000/api/v1/deploy/po"
                            deploy_payload = {"doc_no": item.get('doc_no'), "vendor_name": item.get('vendor_name'), "vendor_email": item.get('vendor_email', '')}
                            res = requests.post(deploy_url, json=deploy_payload, timeout=15)
                            
                            if res.status_code == 200:
                                updated_queue = [q for q in queue_items if q.get('id') != item.get('id')]
                                save_queue(updated_queue)
                                st.success("성공적으로 발송되었습니다!")
                                st.rerun()
                            else:
                                st.error(f"❌ Flask 서버 오류: {res.status_code}")
                                st.code(res.text)
                        except Exception as e:
                            st.error(f"❌ 배포 서버 통신 오류: {str(e)}")

# ------------------------------------------
# [탭 2] 수동 렌더링 테스트 화면 (기존 동일)
# ------------------------------------------
with tab2:
    st.subheader("발주 데이터 수동 조립 및 테스트")
    with st.form("po_assembly_form"):
        col1, col2 = st.columns(2)
        with col1:
            selected_project = st.selectbox("식별코드 선택", ["BH03V01", "BH04V01", "JD01V02"])
            selected_qty = st.number_input("발주 수량 (SET)", min_value=1, value=100, step=10)
            selected_cond_label = st.selectbox("하단 조건 명칭", ["결제 조건", "특약 조건", "진행 조건"])
        with col2:
            selected_vendor = st.selectbox("협력사코드 선택", ["PRE-001", "AEX-002", "MOL-005"])
            selected_due_date = st.date_input("납기 요청일")
            
        selected_cond_text = st.text_area("조건 내용 입력", value="12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급", height=80)
        generate_btn = st.form_submit_button("로봇 발주서 초안 생성 ⚙️")

    if generate_btn:
        assembled_json = generate_po_json(selected_project, selected_vendor, selected_qty, selected_due_date, selected_cond_label, selected_cond_text)
        formatted_json_str = json.dumps(assembled_json, ensure_ascii=False, indent=4)
        st.success("조립 완료.")
        st.session_state['pending_po_json'] = formatted_json_str

    if 'pending_po_json' in st.session_state:
        if st.button("🚨 최종 승인 및 문서 발행 트리거 작동"):
            with st.spinner("렌더링 중..."):
                try:
                    po_data_dict = json.loads(st.session_state['pending_po_json'])
                    SERVER_URL = "http://localhost:5000/api/v1/generate/po"
                    response = requests.post(SERVER_URL, json=po_data_dict, timeout=15)
                    
                    if response.status_code == 200:
                        doc_no = po_data_dict.get("doc_no", "PO_문서")
                        pdf_save_dir = os.path.join(os.getcwd(), "temp_outputs")
                        os.makedirs(pdf_save_dir, exist_ok=True)
                        pdf_result_path = os.path.join(pdf_save_dir, f"{doc_no}.pdf")
                        
                        with open(pdf_result_path, 'wb') as f:
                            f.write(response.content)
                        st.success(f"📂 렌더링 완료. 저장 위치: {pdf_result_path}")
                        del st.session_state['pending_po_json']
                    else:
                        st.error(f"❌ 오류: {response.status_code}")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {str(e)}")

# ------------------------------------------
# [탭 3] 원가 혁신 관제 (신규 추가)
# ------------------------------------------
with tab3:
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
# [탭 4] AI 견적 대기열 (통합 완료)
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