import os
import requests
import json
import tempfile
import subprocess
from flask import Flask, request, jsonify, make_response, send_file
from dotenv import load_dotenv  # 추가
from pathlib import Path


# .env 파일의 내용을 환경 변수로 로드
load_dotenv()  # 추가

# 현재 파일의 위치를 기준으로 경로 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "makermone_data.txt"

app = Flask(__name__)

# [중요] 성공한 만능 열쇠 (FSSE)
API_KEY = os.getenv("GOOGLE_API_KEY")
# [중요] 성공한 최신 모델 (Gemini 2.0 Flash)
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

# --- [1. 지식 파일 읽어오기] ---
def load_knowledge():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return "회사 정보 파일이 없습니다."

COMPANY_KNOWLEDGE = load_knowledge()

# --- [2. AI에게 물어보는 함수 (공통 사용)] ---
def ask_gemini(question, user_id="guest"):
    # 페르소나 설정
    persona = "당신은 제조 플랫폼 '메이커몬'의 전문 AI 매니저입니다. 친절하고 전문적으로 답변하세요."
    
    # 프롬프트 조립
    final_prompt = f"""
    [역할]
    {persona}

    [참고해야 할 회사 정보 (지식 베이스)]
    {COMPANY_KNOWLEDGE}

    [답변 원칙]
    1. 위 '참고 정보'에 있는 내용만 사실대로 답변하세요.
    2. 정보에 없는 내용은 "죄송하지만 해당 정보는 아직 확인되지 않았습니다"라고 솔직하게 말하세요.
    3. 3D 프린팅 관련 질문이 나오면 단호하게 안 한다고 말하세요.
    4. 답변은 300자 이내로 간결하게 줄여서 말하세요. (카카오톡 가독성 위해)

    [사용자 질문]
    {question}
    """

    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}]
    }
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(GEMINI_URL, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"죄송합니다. AI 서버 오류가 발생했습니다. (Error: {response.status_code})"
    except Exception as e:
        return f"서버 접속 오류: {str(e)}"

# ==========================================
# [기존] 웹/테스트용 주소 (유지)
# ==========================================
@app.route('/', methods=['GET'])
def home():
    return "🤖 메이커몬 AI (카카오톡 연결 준비 완료!)"

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    answer = ask_gemini(data.get('question'), data.get('user_id', 'guest'))
    return jsonify({"answer": answer})

# ==========================================
# [신규] 카카오톡 전용 주소 (여기가 핵심!)
# ==========================================
@app.route('/kakao', methods=['POST'])
def kakao_chat():
    try:
        # 1. 카카오톡이 보내준 복잡한 데이터 받기
        body = request.get_json()
        
        # 2. 고객이 쓴 '진짜 질문 내용'만 쏙 뽑아내기
        user_question = body['userRequest']['utterance']
        
        # 3. Gemini에게 물어보기
        ai_answer = ask_gemini(user_question)
        
        # 4. 카카오톡이 좋아하는 포맷(JSON)으로 포장해서 보내주기
        response_body = {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": ai_answer
                        }
                    }
                ]
            }
        }
        return jsonify(response_body)

    except Exception as e:
        # 에러 나면 로그 출력
        print(f"카카오 오류: {e}")
        return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "오류가 발생했습니다."}}]}})

# ==========================================
# [v3.0 개편] 문서 자동화 렌더링 팩토리 라우터 (격리형 워커 통신)
# ==========================================
@app.route('/api/v1/generate/po', methods=['POST'])
def generate_po():
    try:
        # 1. AutoDoc.gs로부터 데이터(Payload) 수신
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 전달되지 않았습니다."}), 400

        print(f"📦 [수신 완료] 발주서 렌더링 요청: {data.get('doc_no')} / {data.get('clientCode')}")

        # 2. 에셋 템플릿 경로 설정 (.ods)
        template_path = os.path.join(BASE_DIR, "assets", "templates", "template_po.ods")
        data["_template_path"] = template_path

        # 3. DLL 충돌 방지를 위한 격리용 임시 JSON 파일 생성
        temp_json_fd, temp_json_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(temp_json_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        # 4. [핵심] LibreOffice 내장 파이썬(워커) 호출 (서브프로세스 격리)
        lo_python_exe = r"C:\Program Files\LibreOffice\program\python.exe"
        worker_script = os.path.join(BASE_DIR, "render_worker.py")

        print("⚙️ 렌더링 워커 가동 중... (LibreOffice 통신)")
        result = subprocess.run(
            [lo_python_exe, worker_script, temp_json_path],
            capture_output=True, text=True, check=True
        )

        # 통신이 끝났으므로 임시 JSON 파일 삭제
        os.remove(temp_json_path)

        # 5. 생성된 PDF 파일 경로 확보
        pdf_result_path = result.stdout.strip()
        print(f"✅ 렌더링 완료! PDF 추출 성공: {pdf_result_path}")

        # 6. 완성된 PDF를 이진 파일(Blob) 형태로 AutoDoc.gs에 반환
        return send_file(
            pdf_result_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{data.get('doc_no', 'PO')}.pdf"
        )

    except subprocess.CalledProcessError as e:
        print(f"❌ 워커 실행 에러: {e.stderr}")
        return jsonify({"error": "렌더링 팩토리 워커 에러", "details": e.stderr}), 500
    except Exception as e:
        print(f"❌ 시스템 통신 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))