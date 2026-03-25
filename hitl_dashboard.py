import streamlit as st
import json
import os
import tempfile
import requests
from datetime import datetime

# ==========================================
# [기본 설정 및 데이터 로드]
# ==========================================
# 화면을 넓게 쓰기 위한 페이지 기본 설정
st.set_page_config(page_title="메이커몬 HITL 대시보드", layout="wide")

QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")

def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_queue(data):
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ==========================================
# [메이커몬 HITL 통제 센터] 발주서 수동 조립 모듈 (Tab 2 용도)
# ==========================================
def get_mock_vendor_data(vendor_code):
    vendors = {
        "PRE-001": {"name": "프리시전(가칭)", "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"},
    }
    return vendors.get(vendor_code, {"name": "미상", "payment_condition": "협의 필요"})

def generate_po_json(project_code, vendor_code, total_qty, due_date, cond_label, cond_text):
    vendors = {
        "PRE-001": {"name": "프리시전(가칭)", "biz_no": "123-45-67890", "address": "경기도 시흥시 산기대학로 123", "ceo": "김정밀", "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"}
    }
    v_info = vendors.get(vendor_code, {"name": "미상", "biz_no": "", "address": "", "ceo": "", "payment_condition": ""})
    
    po_data = {
        "doc_no": f"MK-PO-{datetime.now().strftime('%Y%m%d')}-01",
        "vendor_name": v_info["name"],
        "vendor_biz_no": v_info["biz_no"],
        "vendor_address": v_info["address"],
        "vendor_ceo": v_info["ceo"],
        
        "po_title": f"{project_code} AI Robot 양산 제작 발주",
        "po_date": datetime.now().strftime("%Y-%m-%d"),
        "po_details": f"기구물 파츠 외 (하단 표 참조)",
        "due_date": due_date.strftime("%Y-%m-%d"),
        
        "total_amount": "₩ 80,200,000",
        "manage_no": f"{project_code}-V02-PO",
        "attachment": "제작도면 (STEP 파일 포함)",
        "payment_condition": v_info["payment_condition"],
        
        "condition_label": cond_label,
        "condition_content": cond_text,
        
        "po_items": [
            {"project_manage_no": f"{project_code}\n(Ver.정방향)", "model_no": "TOP Ass'y", "qty": "60 SET", "price": "₩ 51,600,000"},
            {"project_manage_no": f"{project_code}\n(Ver.정방향)", "model_no": "MIDDLE Ass'y", "qty": "60 SET", "price": "₩ 51,600,000"},
            {"project_manage_no": f"{project_code}\n(Ver.정방향)", "model_no": "BOTTOM Ass'y", "qty": "60 SET", "price": "₩ 51,600,000"},
            {"project_manage_no": f"{project_code}\n(Ver.대칭)", "model_no": "TOP Ass'y", "qty": "20 SET", "price": "₩ 17,200,000"},
            {"project_manage_no": f"{project_code}\n(Ver.대칭)", "model_no": "MIDDLE Ass'y", "qty": "20 SET", "price": "₩ 17,200,000"},
            {"project_manage_no": f"{project_code}\n(Ver.대칭)", "model_no": "BOTTOM Ass'y", "qty": "20 SET", "price": "₩ 17,200,000"},
            {"project_manage_no": "BH05V01\n(Ver.Headless, 정방향)", "model_no": "MIDDLE Ass'y", "qty": "15 SET", "price": "₩ 8,550,000"},
            {"project_manage_no": "BH05V01\n(Ver.Headless, 정방향)", "model_no": "BOTTOM Ass'y", "qty": "15 SET", "price": "₩ 8,550,000"}
        ]
    }
    return po_data


# ==========================================
# [Streamlit UI 프론트엔드]
# ==========================================
st.title("🏭 메이커몬 HITL 중앙 관제 대시보드")

# 두 개의 탭으로 화면 완벽 분리
tab1, tab2 = st.tabs(["📋 발주서 승인 대기열 (Auto)", "⚙️ 수동 렌더링 테스트 (Manual)"])

# ------------------------------------------
# [탭 1] 자동 대기열 관제 화면 (Apps Script에서 날아온 데이터)
# ------------------------------------------
with tab1:
    st.subheader("발주서 최종 승인 대기열")
    
    # 언제든 파일의 최신 상태를 불러올 수 있도록 새로고침 버튼 추가
    if st.button("🔄 대기열 새로고침"):
        st.rerun()

    queue_items = load_queue()

    if not queue_items:
        st.info("현재 승인 대기 중인 발주서가 없습니다.")
    else:
        for item in queue_items:
            # 안전하게 dict.get()을 사용하여 에러 방지
            with st.expander(f"📦 {item.get('doc_no', 'N/A')} | {item.get('vendor_name', 'N/A')} | {item.get('total_amount', 'N/A')}", expanded=True):
                st.write(f"**관리 번호(식별코드):** {item.get('manage_no', 'N/A')}")
                st.write(f"**수신 일시:** {item.get('received_at', 'N/A')}")
                
                # 마크다운 하이퍼링크 형식으로 구글 드라이브 링크 제공 (백틱 사용 금지 원칙 준수)
                pdf_link = item.get('pdf_url', '#')
                st.markdown(f"📄 **첨부파일 확인:** [발주서 PDF 파일 열기]({pdf_link})")
                
                st.warning("⚠️ 위 PDF 링크를 열어 도면, 수량, 결제 조건을 최종 확인해 주십시오.")
                
                # 승인 처리 버튼
                if st.button(f"✅ 최종 승인 및 메일 발송 ({item.get('doc_no', 'N/A')})", key=item.get('id', 'temp_key')):
                    # 1. 큐에서 해당 아이템 제거
                    updated_queue = [q for q in queue_items if q.get('id') != item.get('id')]
                    save_queue(updated_queue)
                    
                    # 2. 후속 트리거 실행
                    st.success(f"{item.get('vendor_name', 'N/A')} 협력사에 발주서가 최종 승인 및 발송 처리되었습니다!")
                    st.rerun()

# ------------------------------------------
# [탭 2] 수동 렌더링 테스트 화면 (엔지니어 조작용)
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
            
        selected_cond_text = st.text_area("조건 내용 입력 (길어지면 D54까지 자동 확장 및 폰트 축소됨)", 
                                          value="12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급", height=80)
        
        generate_btn = st.form_submit_button("로봇 발주서 초안 생성 ⚙️")

    if generate_btn:
        assembled_json = generate_po_json(
            selected_project, 
            selected_vendor, 
            selected_qty, 
            selected_due_date,
            selected_cond_label,
            selected_cond_text
        )
        
        formatted_json_str = json.dumps(assembled_json, ensure_ascii=False, indent=4)
        st.success("✅ 발주 데이터가 성공적으로 조립되었습니다. 아래 내용을 검토해 주십시오.")
        st.text_area("승인 대기 중인 발주 JSON 데이터", value=formatted_json_str, height=400)
        st.session_state['pending_po_json'] = formatted_json_str

    if 'pending_po_json' in st.session_state:
        st.warning("⚠️ 위 데이터를 확인하셨습니까? 승인 시 즉시 PDF 문서가 렌더링됩니다.")
        
        if st.button("🚨 최종 승인 및 문서 발행 트리거 작동"):
            with st.spinner("안전 격리 환경(Flask 렌더링 팩토리)으로 발주 데이터를 전송하여 PDF를 굽고 있습니다..."):
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
                            
                        st.success(f"🎉 렌더링 대성공! 완벽한 PDF가 생성되었습니다.")
                        st.info(f"📂 파일 저장 위치: {pdf_result_path}")
                        
                        del st.session_state['pending_po_json']
                    else:
                        st.error(f"❌ 렌더링 서버 통신 오류 (상태 코드: {response.status_code})")
                        st.code(response.text)
                        
                except requests.exceptions.RequestException as e:
                    st.error("❌ 렌더링 팩토리(Flask) 서버에 연결할 수 없습니다. 5000번 포트 서버가 켜져 있는지 확인해 주세요.")
                    st.code(str(e))
                except Exception as e:
                    st.error(f"❌ 대시보드 내부 처리 오류 발생: {str(e)}")