import os
import requests
from flask import Flask, request, jsonify, make_response, send_file
from dotenv import load_dotenv  # 추가
from pathlib import Path
from uno_renderer import render_ods_to_pdf #새롭게 PyUNO 통신 모듈

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
# [v3.0 개편] 문서 자동화 렌더링 팩토리 라우터 (PyUNO 데몬 통신)
# ==========================================
@app.route('/api/v1/generate/po', methods=['POST'])
def generate_po():
    try:
        data = request.get_json()
        
        # 1. 템플릿 경로 지정 (반드시 Native .ods 사용)
        template_path = os.path.join(BASE_DIR, "assets", "templates", "po_template.ods")
        
        # 2. PyUNO 소켓 통신을 통한 데이터 직접 주입 및 PDF 추출
        # (이 함수 내부에서 텍스트 자동 줄바꿈 등 가독성 로직이 적용됨)
        pdf_file_path = render_ods_to_pdf(template_path, data)
        
        print(f" ✅ [렌더링 팩토리] .ods Native 추출 대성공 -> {pdf_file_path}")
        
        return send_file(
            pdf_file_path, 
            as_attachment=True, 
            download_name=os.path.basename(pdf_file_path), 
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f" ❌ 렌더링 오류 발생: {e}")
        # 에러 원인을 명확히 파악하기 위해 땜질식 처방 없이 로직 중단 및 로그 반환
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))