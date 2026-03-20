import streamlit as st
import json
import os
import tempfile
import subprocess
from datetime import datetime

# ==========================================
# [메이커몬 HITL 통제 센터] 발주서 자동 조립 모듈
# ==========================================

def get_mock_vendor_data(vendor_code):
    """(가상) Vender DB에서 협력사 정보 및 단가를 긁어오는 함수"""
    # 실제로는 Code.gs를 통하거나 서버에서 Sub DB CSV를 읽어옵니다.
    vendors = {
        "PRE-001": {"name": "프리시전(가칭)", "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"},
    }
    return vendors.get(vendor_code, {"name": "미상", "payment_condition": "협의 필요"})

def generate_po_json(project_code, vendor_code, total_qty, due_date):
    """
    엔지니어의 단순 입력을 완벽한 1:1 매핑 JSON 페이로드로 자동 조립
    """
    # 임시 목업(Mock) 데이터 (추후 실제 DB 연동)
    vendors = {
        "PRE-001": {
            "name": "프리시전(가칭)", 
            "biz_no": "123-45-67890",
            "address": "경기도 시흥시 산기대학로 123",
            "ceo": "김정밀",
            "payment_condition": "12월 29일 40대 선금 지급, 이후 납품 수량에 따라 지급"
        },
    }
    v_info = vendors.get(vendor_code, {"name": "미상", "biz_no": "", "address": "", "ceo": "", "payment_condition": ""})
    
    unit_price = 802000
    total_amount = unit_price * total_qty
    
    # 워커(render_worker.py)가 기대하는 1:1 키값으로 조립
    po_data = {
        "doc_no": f"MK-PO-{datetime.now().strftime('%Y%m%d')}-01",
        "vendor_name": v_info["name"],
        "vendor_biz_no": v_info["biz_no"],
        "vendor_address": v_info["address"],
        "vendor_ceo": v_info["ceo"],
        
        "po_title": f"북미향 AI Chef Robot 양산 제작 발주",
        "po_date": datetime.now().strftime("%Y-%m-%d"),
        "po_details": f"제품 4종 (총 {total_qty}SET)",
        "due_date": due_date.strftime("%Y-%m-%d"),
        
        "total_amount": f"{total_amount:,}",
        "manage_no": f"{project_code}-V02-PO",
        "attachment": "4종 제작도면 (Headless 2종 제외)",
        "payment_condition": v_info["payment_condition"],
        
        "po_items": [
            {
                "project_manage_no": project_code,
                "model_no": f"{project_code}{vendor_code}-A",
                "qty": f"{total_qty} SET",
                "price": f"₩ {total_amount:,}"
            }
        ]
    }
    return po_data

# --- [Streamlit UI 프론트엔드] ---
st.title("🏭 메이커몬 HITL 통제 센터 (V02)")
st.header("발주 데이터 자동 조립기")

with st.form("po_assembly_form"):
    col1, col2 = st.columns(2)
    with col1:
        selected_project = st.selectbox("식별코드 선택", ["BH03V01", "BH04V01", "JD01V02"])
        selected_qty = st.number_input("발주 수량 (SET)", min_value=1, value=100, step=10)
    with col2:
        selected_vendor = st.selectbox("협력사코드 선택", ["PRE-001", "AEX-002", "MOL-005"])
        selected_due_date = st.date_input("납기 요청일")
        
    # '초안 생성' 버튼
    generate_btn = st.form_submit_button("로봇 발주서 초안 생성 ⚙️")

if generate_btn:
    # 1. 기계가 백그라운드에서 JSON을 조립합니다.
    assembled_json = generate_po_json(
        selected_project, 
        selected_vendor, 
        selected_qty, 
        selected_due_date
    )
    
    # 2. 엔지니어가 식별하기 좋게 '자동 줄바꿈(indent=4)'을 적용하여 표출합니다. (HITL 규칙 준수)
    formatted_json_str = json.dumps(assembled_json, ensure_ascii=False, indent=4)
    
    st.success("✅ 발주 데이터가 성공적으로 조립되었습니다. 아래 내용을 검토해 주십시오.")
    
    # 화면에 가독성 좋게 출력 (엔지니어 시각적 확인용)
    st.text_area("승인 대기 중인 발주 JSON 데이터 (자동 줄바꿈 적용됨)", value=formatted_json_str, height=400)
    
    # 세션 스테이트에 임시 저장하여 다음 버튼에서 쓸 수 있게 함
    st.session_state['pending_po_json'] = formatted_json_str

# 3. 인간(엔지니어)의 최종 통제 - 승인 및 렌더링 트리거
if 'pending_po_json' in st.session_state:
    st.warning("⚠️ 위 데이터를 확인하셨습니까? 승인 시 즉시 PDF 문서가 렌더링됩니다.")
    
    if st.button("🚨 최종 승인 및 문서 발행 트리거 작동"):
        with st.spinner("안전 격리 환경에서 PDF를 굽고 있습니다..."):
            try:
                import json
                po_data_dict = json.loads(st.session_state['pending_po_json'])
                
                # 1. 템플릿 경로를 JSON 안에 몰래 껴넣음
                template_path = os.path.join(os.getcwd(), "assets", "templates", "template_po.ods")
                po_data_dict["_template_path"] = template_path
                
                # 2. 충돌 방지를 위해 데이터를 임시 JSON 파일로 저장
                temp_json_fd, temp_json_path = tempfile.mkstemp(suffix=".json")
                with os.fdopen(temp_json_fd, 'w', encoding='utf-8') as f:
                    json.dump(po_data_dict, f, ensure_ascii=False)
                
                # 3. [핵심] LibreOffice 내장 파이썬으로 독립 스크립트 실행 (DLL 충돌 원천 차단)
                lo_python_exe = r"C:\Program Files\LibreOffice\program\python.exe"
                worker_script = os.path.join(os.getcwd(), "render_worker.py")
                
                # 서브프로세스 호출
                result = subprocess.run(
                    [lo_python_exe, worker_script, temp_json_path],
                    capture_output=True, text=True, check=True
                )
                
                # 4. 임시 파일 청소
                os.remove(temp_json_path)
                
                pdf_result_path = result.stdout.strip()
                
                st.success(f"🎉 렌더링 대성공! 완벽한 PDF가 생성되었습니다.")
                st.info(f"📂 파일 저장 위치: {pdf_result_path}")
                
                del st.session_state['pending_po_json']
                
            except subprocess.CalledProcessError as e:
                st.error("❌ 렌더링 워커 내부 오류 발생!")
                st.code(e.stderr)  # LibreOffice 파이썬이 뱉은 에러를 그대로 보여줌
            except Exception as e:
                st.error(f"❌ 시스템 통신 오류 발생: {str(e)}")