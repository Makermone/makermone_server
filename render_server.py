import os
import sys
import json
import smtplib
from datetime import datetime  # [신규 추가] 시간 기록을 위한 시계 부품 장착!
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import Flask, request, send_file, jsonify

# ==========================================
# [신규 조치] dotenv 라이브러리 없이 순수 파이썬으로 .env 안전 로드
# ==========================================
def load_env_natively():
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 주석(#) 무시 및 = 기호가 있는 줄만 파싱
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

# 환경 변수 강제 로드 실행
load_env_natively()

# ==========================================
# [핵심 1] 윈도우 환경 LibreOffice DLL 및 PyUNO 경로 강제 주입
# ==========================================
lo_program_path = r"C:\Program Files\LibreOffice\program"

if os.name == 'nt':
    if lo_program_path not in sys.path:
        sys.path.append(lo_program_path)
    if lo_program_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = lo_program_path + os.pathsep + os.environ.get("PATH", "")

# 경로 주입 후 안전하게 uno 임포트
try:
    import uno
    from com.sun.star.beans import PropertyValue
except ImportError as e:
    print(f"❌ PyUNO 라이브러리 임포트 실패 (경로 문제): {e}")
    sys.exit(1)

app = Flask(__name__)

# ==========================================
# [핵심 2] PyUNO 렌더링 코어 함수 (Daemon 직접 통신)
# ==========================================
def render_po_to_pdf(data_json, template_path, output_pdf_path):
    localContext = uno.getComponentContext()
    resolver = localContext.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", localContext
    )
    
    try:
        ctx = resolver.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        
        url_template = uno.systemPathToFileUrl(os.path.abspath(template_path))
        props = (PropertyValue("Hidden", 0, True, 0),)
        doc = desktop.loadComponentFromURL(url_template, "_blank", 0, props)
        sheet = doc.Sheets.getByIndex(0)

        # ==================================================
        # [핵심 방어 로직] 엑셀 '행 높이 팽창(Optimal Height)' 원천 봉쇄
        # 배경 이미지와 텍스트의 싱크가 어긋나는 것을 막기 위해 
        # 0행부터 60행까지의 높이를 무조건 고정(Lock)합니다.
        # ==================================================
        for r_idx in range(60):
            sheet.Rows.getByIndex(r_idx).OptimalHeight = False

        # --------------------------------------------------
        # [Step 1] 고정 변수 매핑 
        # --------------------------------------------------
        sheet.getCellRangeByName("B4").String = data_json.get("doc_no", "")
        sheet.getCellRangeByName("E8").String = data_json.get("vendor_name", "")
        sheet.getCellRangeByName("J8").String = data_json.get("vendor_ceo", "")
        sheet.getCellRangeByName("E9").String = data_json.get("vendor_biz_no", "")
        sheet.getCellRangeByName("E10").String = data_json.get("vendor_address", "")
        sheet.getCellRangeByName("D22").String = data_json.get("po_title", "")
        sheet.getCellRangeByName("D23").String = data_json.get("po_date", "")
        sheet.getCellRangeByName("D24").String = data_json.get("po_details", "")
        sheet.getCellRangeByName("D25").String = data_json.get("due_date", "")
        
        # [수정] 합계(Total) 가로 병합 강제 (J48~L48) 및 우측 정렬
        m_total_range = sheet.getCellRangeByPosition(9, 47, 11, 47)
        m_total_range.merge(True)
        cell_total = sheet.getCellByPosition(9, 47)
        cell_total.String = data_json.get("total_amount", "")
        cell_total.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "RIGHT")
        cell_total.VertJustify = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        sheet.getCellRangeByName("D51").String = data_json.get("manage_no", "")
        sheet.getCellRangeByName("D52").String = data_json.get("attachment", "")

        # --------------------------------------------------
        # [특약/결제 조건 로직] 명칭 주입 + D53~L54 병합 및 자동 폰트/정렬 리사이징
        # --------------------------------------------------
        cond_label = data_json.get("condition_label", "결제 조건")
        cond_text = data_json.get("condition_content", "")

        # 1. 라벨(명칭) 주입: 배경 이미지가 비워져 있다는 전제하에 B53 셀(1, 52)에 주입
        m_label_range = sheet.getCellRangeByPosition(1, 52, 2, 52) # B53~C53 병합
        m_label_range.merge(True)
        cell_label = sheet.getCellByPosition(1, 52)
        cell_label.String = cond_label
        cell_label.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "CENTER")
        cell_label.VertJustify = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        # 2. 내용 주입: D53부터 L54까지의 거대한 블록(3,52 ~ 11,53)을 병합하여 울타리 생성
        m_cond_range = sheet.getCellRangeByPosition(3, 52, 11, 53)
        m_cond_range.merge(True)
        
        cell_cond = sheet.getCellByPosition(3, 52)
        cell_cond.String = cond_text
        cell_cond.IsTextWrapped = True 
        cell_cond.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "LEFT")
        # VertJustify(수직 정렬)는 아래에서 동적으로 부여합니다.

        # 3. 글자 수 감지 기반 동적 폰트 리사이징 및 수직 정렬 제어
        text_len = len(cond_text)
        ALIGN_TOP = uno.Enum("com.sun.star.table.CellVertJustify", "TOP")
        ALIGN_CENTER = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        # [핵심 수정] 한글(Asian) 폰트 크기(CharHeightAsian)를 영문과 함께 반드시 축소해야 합니다.
        if text_len > 100:
            cell_cond.CharHeight = 7.0
            cell_cond.CharHeightAsian = 7.0  # 한글 폰트 크기 7.0으로 동기화
            cell_cond.VertJustify = ALIGN_TOP  
        elif text_len > 70:
            cell_cond.CharHeight = 7.5
            cell_cond.CharHeightAsian = 7.5  # 한글 폰트 크기 7.5로 동기화
            cell_cond.VertJustify = ALIGN_TOP  
        elif text_len > 40:
            cell_cond.CharHeight = 8.5
            cell_cond.CharHeightAsian = 8.5  # 한글 폰트 크기 8.5로 동기화
            cell_cond.VertJustify = ALIGN_CENTER  
        else:
            cell_cond.CharHeight = 10.0
            cell_cond.CharHeightAsian = 10.0 # 기본 한글 폰트 크기
            cell_cond.VertJustify = ALIGN_TOP
            
        # 4. 특약/진행 조건일 경우 '빨간색 + 볼드체'로 자동 강조
        if "특약" in cond_label or "진행" in cond_label:
            cell_label.CharColor = 16711680 
            cell_label.CharWeight = 150.0   
            cell_label.CharWeightAsian = 150.0   # 한글 볼드체도 확실하게 강제 적용
            cell_cond.CharColor = 16711680  
            cell_cond.CharWeight = 150.0    
            cell_cond.CharWeightAsian = 150.0    # 한글 볼드체도 확실하게 강제 적용
        else:
            cell_label.CharColor = 0        
            cell_label.CharWeight = 100.0   
            cell_label.CharWeightAsian = 100.0
            cell_cond.CharColor = 0
            cell_cond.CharWeight = 100.0
            cell_cond.CharWeightAsian = 100.0

        # --------------------------------------------------
        # [Step 2 & 3] 스마트 그룹핑 및 2D 블록 병합 (여백 추가 버전)
        # --------------------------------------------------
        ALIGN_CENTER_HORI = uno.Enum("com.sun.star.table.CellHoriJustify", "CENTER")
        ALIGN_RIGHT_HORI = uno.Enum("com.sun.star.table.CellHoriJustify", "RIGHT")
        ALIGN_CENTER_VERT = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        items = data_json.get("po_items", [])
        
        if items:
            # 1. 항목들을 프로젝트/수량/가격 단위로 먼저 묶습니다.
            groups = []
            current_group = {
                "proj": items[0].get("project_manage_no", ""),
                "qty": items[0].get("qty", ""),
                "price": items[0].get("price", ""),
                "models": [items[0].get("model_no", "")]
            }

            for i in range(1, len(items)):
                item = items[i]
                if (item.get("project_manage_no", "") == current_group["proj"] and
                    item.get("qty", "") == current_group["qty"] and
                    item.get("price", "") == current_group["price"]):
                    current_group["models"].append(item.get("model_no", ""))
                else:
                    groups.append(current_group)
                    current_group = {
                        "proj": item.get("project_manage_no", ""),
                        "qty": item.get("qty", ""),
                        "price": item.get("price", ""),
                        "models": [item.get("model_no", "")]
                    }
            groups.append(current_group)

            # 2. 렌더링 시작 (28행)
            current_row_ptr = 27 

            for g in groups:
                actual_models = g["models"]
                
                # ★ [핵심 방어 로직] 텍스트 잘림을 방지하기 위한 '최소 높이 보장'
                # 파츠 개수가 몇 개든, 무조건 최소 3행(Rows) 높이는 강제로 확보합니다.
                num_rows = max(len(actual_models), 3) 

                s_row = current_row_ptr
                e_row = current_row_ptr + num_rows - 1

                # [모델명] 병합 없이 가로로만 공간 확보 (부족한 파츠 칸은 빈칸으로 두어 높이만 창출)
                for i in range(num_rows):
                    r_idx = s_row + i
                    m_model_range = sheet.getCellRangeByPosition(4, r_idx, 6, r_idx)
                    m_model_range.merge(True)
                    
                    cell_model = sheet.getCellByPosition(4, r_idx)
                    
                    # 파츠 이름이 있으면 넣고, 파츠가 모자라면 빈칸("")으로 두어 높이 지지대 역할만 함
                    if i < len(actual_models):
                        cell_model.String = actual_models[i]
                    else:
                        cell_model.String = ""
                        
                    cell_model.HoriJustify = ALIGN_CENTER_HORI
                    cell_model.VertJustify = ALIGN_CENTER_VERT
                    cell_model.IsTextWrapped = True 

                # [헬퍼 함수] 가로+세로 병합 후 텍스트 넣고 줄바꿈 켬
                def merge_2d_block(col_start, col_end, text, hori_align):
                    m_range = sheet.getCellRangeByPosition(col_start, s_row, col_end, e_row)
                    m_range.merge(True)
                    top_cell = sheet.getCellByPosition(col_start, s_row)
                    top_cell.String = text
                    top_cell.HoriJustify = hori_align
                    top_cell.VertJustify = ALIGN_CENTER_VERT
                    top_cell.IsTextWrapped = True 

                # 각 데이터 주입 (최소 3칸 높이가 보장된 상태에서 병합됨)
                merge_2d_block(2, 3, g["proj"], ALIGN_CENTER_HORI)
                merge_2d_block(7, 8, g["qty"], ALIGN_CENTER_HORI)
                merge_2d_block(9, 11, g["price"], ALIGN_RIGHT_HORI)

                # 시인성 극대화: 다음 그룹은 무조건 1줄(빈 행)을 건너뛰고 시작합니다!
                current_row_ptr = e_row + 2

        # 4. 네이티브 PDF 추출 (Export)
        url_pdf = uno.systemPathToFileUrl(os.path.abspath(output_pdf_path))
        filter_args = (PropertyValue("FilterName", 0, "calc_pdf_Export", 0),)
        doc.storeToURL(url_pdf, filter_args)
        
        doc.close(True)
        return True
        
    except Exception as e:
        print(f"🚨 [PyUNO 브릿지 에러]: {str(e)}")
        return False

# ==========================================
# [핵심 3] 발주서 생성 API 라우터 (서브프로세스 제거)
# ==========================================
@app.route('/api/v1/generate/po', methods=['POST'])
def generate_po():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 전달되지 않았습니다."}), 400

        # [수정됨] 1 Depth 구조 파싱으로 오류 해결
        doc_no = data.get("doc_no", "PO_DEFAULT")
        print(f"📦 [수신 완료] PO 렌더링 요청 수신: {doc_no}")

        template_path = os.path.join(os.getcwd(), "assets", "templates", "template_po.ods")
        
        if not os.path.exists(template_path):
            return jsonify({"error": "템플릿(.ods) 누락", "path": template_path}), 404

        output_pdf_dir = os.path.join(os.getcwd(), "temp_outputs")
        os.makedirs(output_pdf_dir, exist_ok=True)
        output_pdf_path = os.path.join(output_pdf_dir, f"{doc_no}.pdf")

        # 워커(subprocess) 호출 없이 직접 렌더링 코어 실행
        success = render_po_to_pdf(data, template_path, output_pdf_path)

        if success and os.path.exists(output_pdf_path):
            print(f"✅ 렌더링 완료! PDF 추출 성공: {output_pdf_path}")
            return send_file(
                output_pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"{doc_no}.pdf"
            )
        else:
            return jsonify({"error": "PyUNO 렌더링 실패"}), 500

    except Exception as e:
        print(f"❌ 시스템 통신 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# [데이터 파일 관리 모듈] 큐(Queue) 파일 로드 및 저장
# ==========================================
QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")
PRICE_QUEUE_FILE = os.path.join(os.getcwd(), "price_queue.json") # [Phase 2 신규] 원가 관제 큐

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
# [기존 API] HITL 승인 대기열 적재 엔드포인트
# ==========================================
@app.route('/api/v1/queue/po', methods=['POST'])
def add_to_queue():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 없습니다."}), 400
            
        queue_list = load_queue()
        
        # 새 대기열 아이템 생성
        new_item = {
            "id": datetime.now().strftime("%Y%md%H%M%S"),
            "doc_no": data.get("doc_no", ""),
            "manage_no": data.get("manage_no", ""), # 식별코드 (예: BH03V01)
            "vendor_name": data.get("vendor_name", ""),
            "vendor_email": data.get("vendor_email", ""),
            "total_amount": data.get("total_amount", ""),
            "pdf_url": data.get("pdf_url", ""), # 구글 드라이브 다운로드 링크
            "status": "대기중",
            "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        queue_list.append(new_item)
        save_queue(queue_list)
        
        print(f"📥 [대기열 적재 완료] {new_item['doc_no']} - {new_item['vendor_name']}")
        return jsonify({"message": "대기열 적재 성공", "queue_id": new_item["id"]}), 200

    except Exception as e:
        print(f"❌ 대기열 적재 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# [Phase 2 신규 API] AutoDoc.gs 자재 전개 (BOM) 대기열 수신
# ==========================================
@app.route('/api/v1/queue/bom', methods=['POST'])
def receive_bom():
    """AutoDoc.gs로부터 2-Track 자재 전개 데이터를 수신 (po_queue.json 에 통합)"""
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No Payload"}), 400
        
        queue_list = load_queue()
        payload['received_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_list.append(payload) 
        
        save_queue(queue_list)
        print("📥 [BOM 대기열 적재 완료] 새로운 자재 전개 데이터가 수신되었습니다.")
        return jsonify({"status": "success", "message": "BOM queued for rendering"}), 200
        
    except Exception as e:
        print(f"❌ BOM 대기열 적재 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# [Phase 2 신규 API] 원가 변동 내역 (Price_Log) 수신
# ==========================================
@app.route('/api/v1/queue/price', methods=['POST'])
def receive_price_log():
    """AutoDoc.gs로부터 원가 변동 대기 데이터를 수신 (price_queue.json 에 별도 적재)"""
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No Payload"}), 400
        
        queue_list = load_price_queue()
        payload['received_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_list.append(payload)
        
        save_price_queue(queue_list)
        print("📥 [원가 관제 적재 완료] 새로운 단가 변동 이슈가 감지되었습니다.")
        return jsonify({"status": "success", "message": "Price log queued for HITL approval"}), 200
        
    except Exception as e:
        print(f"❌ 원가 대기열 적재 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
# ==========================================
# [Phase 1-3 신규] HITL 승인 완료 시 자동 메일 발송 (Deploy)
# ==========================================
@app.route('/api/v1/deploy/po', methods=['POST'])
def deploy_po_email():
    try:
        data = request.json
        doc_no = data.get("doc_no")
        vendor_email = data.get("vendor_email")
        vendor_name = data.get("vendor_name")

        if not vendor_email:
            return jsonify({"error": "협력사 이메일 정보가 누락되었습니다."}), 400

        # temp_outputs 폴더에서 미리 구워둔 PDF 찾기
        pdf_path = os.path.join(os.getcwd(), "temp_outputs", f"{doc_no}.pdf")
        if not os.path.exists(pdf_path):
            return jsonify({"error": "발송할 PDF 문서를 찾을 수 없습니다."}), 404

        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")

        if not smtp_user or not smtp_pass:
            return jsonify({"error": ".env 파일에 메일 발송 계정 정보가 없습니다."}), 500

        # 1. 메일 양식(MIME) 조립
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = vendor_email
        msg['Subject'] = f"[메이커몬] {vendor_name} 귀하께 발주서를 전송합니다. ({doc_no})"

        body = f"안녕하세요 {vendor_name} 담당자님,\n\n메이커몬에서 양산 제작 발주서를 송부드립니다.\n첨부된 PDF 파일을 확인하시고, 이상이 없을 시 진행 부탁드립니다.\n\n감사합니다.\n- 메이커몬 드림"
        msg.attach(MIMEText(body, 'plain'))

        # 2. PDF 파일 첨부
        with open(pdf_path, 'rb') as f:
            attach = MIMEApplication(f.read(), _subtype="pdf")
            attach.add_header('Content-Disposition', 'attachment', filename=f"{doc_no}_발주서.pdf")
            msg.attach(attach)

        # 3. SMTP 서버 통신 및 발송 (보안 포트 587)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()

        print(f"📧 [메일 발송 완료] {vendor_name} ({vendor_email})")
        return jsonify({"message": "메일 발송 성공"}), 200

    except Exception as e:
        print(f"❌ 메일 발송 에러: {str(e)}")
        return jsonify({"error": f"SMTP 발송 실패: {str(e)}"}), 500
    
# ==========================================
# 4. 서버 가동 스위치 (이 코드가 무조건 파일의 가장 마지막에 있어야 합니다!)
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)