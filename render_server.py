import os
import sys
import json
import smtplib
import base64
import subprocess # [핵심] 리브레오피스 하청 실행을 위한 모듈
import tempfile   # [핵심] 데이터를 안전하게 파일로 묶어서 전달하기 위한 모듈
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import Flask, request, send_file, jsonify

# =====================================================================
# 1. 환경 설정 및 초기화
# =====================================================================

def load_env_natively():
    """
    [보안] 외부 라이브러리(python-dotenv) 의존 없이, 
    순수 파이썬 로직만으로 .env 파일의 환경 변수(이메일 비밀번호 등)를 안전하게 로드합니다.
    """
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 주석('#')이 아니고, '='가 포함된 정상적인 설정값만 추출
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

# 서버 구동 전 환경 변수 강제 주입
load_env_natively()

app = Flask(__name__)

# =====================================================================
# 2. 렌더링 코어 호출부 (클라우드 네이티브 격리 아키텍처 적용)
# =====================================================================

def render_po_to_pdf(data_json, template_path, output_pdf_path):
    """
    [핵심 렌더링 로직]
    Flask 서버가 직접 엑셀을 만지지 않습니다. (메모리 충돌 방지)
    들어온 데이터(data_json)를 '임시 파일(.json)'로 예쁘게 포장한 뒤,
    리브레오피스의 내장 파이썬(uno_engine.py)에게 던져주고 렌더링 결과만 받아옵니다.
    """
    # 1. 하청을 맡길 리브레오피스 전용 파이썬의 절대 경로 (윈도우 환경)
    lo_python = r"C:\Program Files\LibreOffice\program\python.exe"
    # 2. 렌더링 작업을 수행할 스크립트 파일 (프로젝트 폴더 내 존재해야 함)
    uno_engine_script = os.path.join(os.getcwd(), "uno_engine.py")

    # 3. 데이터를 안전하게 넘겨주기 위해 임시 JSON 파일을 생성 (이름이 겹치지 않게 자동 생성됨)
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as f:
        json.dump(data_json, f, ensure_ascii=False)
        temp_json_path = f.name # 생성된 임시 파일의 경로 저장

    try:
        print(f"🚀 [격리 렌더링] LibreOffice 독립 프로세스(uno_engine.py) 하청 가동...")
        
        # 4. subprocess.run()을 통해 외부 프로세스 실행
        # 구조: [python.exe, 스크립트.py, 데이터.json, 템플릿.ods, 출력.pdf]
        result = subprocess.run(
            [lo_python, uno_engine_script, temp_json_path, template_path, output_pdf_path],
            capture_output=True, # 엔진이 뱉어내는 로그를 캡처
            text=True,
            encoding='utf-8'
        )
        
        # 5. 실행 결과 검증 (returncode가 0이면 정상 종료)
        if result.returncode == 0 and os.path.exists(output_pdf_path):
            print("✅ [격리 렌더링 완료] 템플릿 오차 0% 네이티브 PDF 생성 성공")
            return True
        else:
            # 실패 시 엔진이 뱉어낸 진짜 에러 메시지를 출력하여 디버깅 용이
            print(f"🚨 [격리 렌더링 내부 에러]: {result.stderr}")
            return False
            
    finally:
        # 6. 작업이 끝났거나 에러가 났어도, 보안과 용량 확보를 위해 임시 데이터 파일은 무조건 삭제
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

# =====================================================================
# 3. 대시보드 API 엔드포인트 (2-Step 관제탑 로직)
# =====================================================================

@app.route('/api/v1/generate/preview', methods=['POST'])
def generate_preview():
    """
    [Step 1] 문서 미리보기 엔드포인트
    메일 발송 없이 순수하게 PDF만 생성하여 대시보드 화면(Iframe)에 띄워줍니다.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 없습니다."}), 400

        doc_no = data.get("doc_no", "PO_PREVIEW")
        print(f"🔍 [미리보기 요청 수신] {doc_no} 렌더링 파이프라인 시작...")

        # 템플릿 및 아웃풋 파일 경로 설정
        template_path = os.path.join(os.getcwd(), "assets", "templates", "template_po.ods")
        output_pdf_dir = os.path.join(os.getcwd(), "temp_outputs")
        os.makedirs(output_pdf_dir, exist_ok=True)
        output_pdf_path = os.path.join(output_pdf_dir, f"{doc_no}_preview.pdf")

        # 격리 엔진 구동
        success = render_po_to_pdf(data, template_path, output_pdf_path)

        if not success or not os.path.exists(output_pdf_path):
            return jsonify({"error": "미리보기 렌더링 실패 (엔진 에러를 확인하세요)"}), 500

        print(f"✅ [미리보기 반환] 생성된 PDF를 대시보드 프론트엔드로 즉시 전송합니다.")
        return send_file(output_pdf_path, mimetype='application/pdf')

    except Exception as e:
        print(f"❌ [미리보기 시스템 에러]: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/generate/send', methods=['POST'])
def generate_and_send():
    """
    [Step 2] 최종 렌더링 및 이메일 발송 엔드포인트 (제로 트러스트 적용)
    엔지니어의 육안 검증 및 승인 플래그(Is_Approved)가 있어야만 작동합니다.
    """
    try:
        data = request.json
        doc_no = data.get("doc_no", "PO_DEFAULT")
        vendor_name = data.get("vendor_name", "협력사")
        vendor_email = data.get("vendor_email", "")
        
        # 🔒 물리적 잠금 장치 확인 (HITL)
        is_approved = data.get("Is_Approved", False)

        print(f"🚀 [최종 발송 지시] {doc_no} (엔지니어 승인 상태: {is_approved})")

        if not is_approved:
            return jsonify({"error": "보안 경고: 엔지니어 승인(Is_Approved=True)이 누락되어 자동 발송이 영구 차단됩니다."}), 403

        # 최종 PDF 렌더링 (미리보기 이후 수정된 사항이 있을 수 있으므로 새롭게 렌더링)
        template_path = os.path.join(os.getcwd(), "assets", "templates", "template_po.ods")
        output_pdf_path = os.path.join(os.getcwd(), "temp_outputs", f"{doc_no}_final.pdf")
        
        success = render_po_to_pdf(data, template_path, output_pdf_path)
        if not success:
            return jsonify({"error": "최종 PDF 렌더링 과정에서 문제가 발생했습니다."}), 500

        # SMTP 메일 발송 서버 설정 로드
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        
        # 대시보드에서 수정 가능한 커스텀 이메일 제목/본문 적용
        custom_subject = data.get("email_subject", f"[메이커몬] {vendor_name} 귀하께 발주서를 전송합니다.")
        custom_body = data.get("email_body", "메이커몬 발주서입니다.")

        # 이메일 객체 조립
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = vendor_email
        msg['Subject'] = custom_subject

        # 메이커몬 공식 B2B HTML 서명 포맷 적용
        html_body = f"""
        <html>
          <body style="font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; line-height: 1.6; color: #333;">
            <p>{custom_body.replace(chr(10), '<br>')}</p>
            <br><br>
            <hr style="border: 0; border-top: 1px solid #ddd; margin: 20px 0;">
            <div style="font-size: 13px; color: #666; line-height: 1.4;">
              <p style="margin: 0;"><b>[메이커몬 팩토리 팀]</b></p>
              <p style="margin: 0;">기구설계 기반 제품 제조 & 자동화 매니지먼트 플랫폼</p>
              <p style="margin: 0; margin-top: 5px;">E-mail: hello@makermon.com | Web: www.makermon.com</p>
            </div>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        # 렌더링 된 네이티브 PDF 첨부
        with open(output_pdf_path, 'rb') as f:
            attach = MIMEApplication(f.read(), _subtype="pdf")
            attach.add_header('Content-Disposition', 'attachment', filename=f"{doc_no}_발주서.pdf")
            msg.attach(attach)

        # 구글 Gmail SMTP 서버를 통한 발송 처리
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()

        print(f"📧 [관제탑 송출 완료] {vendor_email} 주소로 발주서와 이메일이 안전하게 전송되었습니다.")
        return jsonify({"message": "렌더링 및 자동 메일 발송 성공"}), 200

    except Exception as e:
        print(f"❌ [SMTP 발송 에러]: {str(e)}")
        return jsonify({"error": str(e)}), 500

# =====================================================================
# 4. JSON 대기열(Queue) 관리 시스템 (Database 역할)
# =====================================================================

QUEUE_FILE = os.path.join(os.getcwd(), "po_queue.json")
PRICE_QUEUE_FILE = os.path.join(os.getcwd(), "price_queue.json")

def load_queue():
    """발주서 승인 대기열 로드"""
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_queue(data):
    """발주서 승인 대기열 갱신 저장"""
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_price_queue():
    """원가 변동(Price Log) 관제 대기열 로드"""
    if os.path.exists(PRICE_QUEUE_FILE):
        with open(PRICE_QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_price_queue(data):
    """원가 변동 관제 대기열 갱신 저장"""
    with open(PRICE_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# =====================================================================
# 5. 구글 Apps Script 연동 수신부 (Webhook Endpoints)
# =====================================================================

@app.route('/api/v1/queue/po', methods=['POST'])
def add_to_queue():
    """
    [문서 1] AutoDoc.gs로부터 발주서(PO) 데이터를 수신하여 대기열에 적재합니다.
    (모든 Payload를 하나도 버리지 않고 100% 보존합니다.)
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 없습니다."}), 400
            
        queue_list = load_queue()
        
        new_item = data.copy()
        new_item["id"] = datetime.now().strftime("%Y%m%d%H%M%S") # 타임스탬프 기반 고유 ID 생성
        new_item["status"] = "대기중"
        new_item["received_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        queue_list.append(new_item)
        save_queue(queue_list)
        
        doc_no = new_item.get('doc_no', 'Unknown')
        print(f"📥 [수신 완료] 발주서({doc_no}) 데이터가 대기열에 성공적으로 적재되었습니다.")
        return jsonify({"message": "대기열 적재 성공", "queue_id": new_item["id"]}), 200

    except Exception as e:
        print(f"❌ [수신 에러]: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/queue/bom', methods=['POST'])
def receive_bom():
    """[Phase 2] AutoDoc.gs로부터 자재 전개(BOM) 데이터를 수신합니다."""
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No Payload"}), 400
        
        queue_list = load_queue()
        payload['received_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_list.append(payload) 
        
        save_queue(queue_list)
        print("📥 [수신 완료] 새로운 자재 전개(BOM) 데이터가 대기열에 적재되었습니다.")
        return jsonify({"status": "success", "message": "BOM queued for rendering"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/queue/price', methods=['POST'])
def receive_price_log():
    """[Phase 2] 원가 변동 내역(Price_Log)을 수신하여 관제탑에 적재합니다."""
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No Payload"}), 400
        
        queue_list = load_price_queue()
        payload['received_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_list.append(payload)
        
        save_price_queue(queue_list)
        print("📥 [수신 완료] 단가 변동 이슈가 감지되어 원가 관제 대기열에 적재되었습니다.")
        return jsonify({"status": "success", "message": "Price log queued for HITL approval"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================================
# 6. 서버 가동 스위치
# =====================================================================
if __name__ == '__main__':
    # 0.0.0.0 개방을 통해 구글 시트(외부)의 포트 포워딩 접근을 허용합니다.
    app.run(host='0.0.0.0', port=5000)