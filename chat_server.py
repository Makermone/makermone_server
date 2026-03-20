from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

# 🚀 최신 통합 SDK 적용
from google import genai
from google.genai import types

load_dotenv()
app = Flask(__name__)

# ==========================================
# 1. 인프라 및 신형 클라이언트 초기화
# ==========================================
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")
DATASTORE_ID = "maker-knowledge_1773908104525"
PYTHON_API_KEY = os.getenv("PYTHON_API_KEY")

# 🚀 핵심: Gemini 2.0이 존재하는 미국 중부(us-central1)로 연결
client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")

datastore_path = f"projects/{PROJECT_ID}/locations/global/collections/default_collection/dataStores/{DATASTORE_ID}"

vertex_tool = types.Tool(
    retrieval=types.Retrieval(
        vertex_ai_search=types.VertexAISearch(datastore=datastore_path)
    )
)

MODEL_NAME = "gemini-2.5-flash"

# ==========================================
# 2. [분기 A] 신규 고객 (GUEST) 카카오톡 엔드포인트
# ==========================================
@app.route('/api/guest_rag', methods=['POST'])
def guest_rag():
    auth_header = request.headers.get('Authorization', '')
    if PYTHON_API_KEY and auth_header != f"Bearer {PYTHON_API_KEY}":
        return jsonify({"answer": "서버 보안 인증에 실패했습니다."}), 401

    data = request.json
    query = data.get('query', '')
    
    guest_instruction = """
    당신은 메이커몬(Makermone)의 전문 AI PM입니다.
    연결된 Data Store를 최우선으로 검색하여 답변하고, 3D 프린팅 단순 출력은 하지 않는다고 단호히 안내하세요.
    가격이나 단가를 물어보면 숫자를 제시하지 말고 '형상과 소재에 따라 상이하다'고 방어하세요.
    답변은 300자 이내로 핵심만 요약하십시오.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[vertex_tool],
                system_instruction=guest_instruction,
                temperature=0.7
            )
        )
        return jsonify({"answer": response.text})
    except Exception as e:
        return jsonify({"answer": f"시스템 응답 에러가 발생했습니다: {str(e)}"})

# ==========================================
# 3. [분기 B] 기존 고객 (PM) 홈페이지/모바일 엔드포인트
# ==========================================
@app.route('/api/client_pm', methods=['POST'])
def client_pm():
    auth_header = request.headers.get('Authorization', '')
    if PYTHON_API_KEY and auth_header != f"Bearer {PYTHON_API_KEY}":
        return jsonify({"answer": "서버 보안 인증에 실패했습니다."}), 401

    data = request.json
    client_code = data.get('client_code', 'UNKNOWN')
    query = data.get('query', '')
    context_data = data.get('context_data', {}) 

    pm_instruction = f"""
    당신은 팹리스 제조 플랫폼 '메이커몬'의 무결점 전담 AI PM입니다.
    현재 고객사 코드는 [{client_code}] 입니다.
    [절대 원칙] 반드시 아래 제공된 JSON 데이터를 꼼꼼히 스캔하여 팩트 기반으로 답변하세요.
    [🚨 메이커몬 헌법] 절대 백틱(`) 기호로 링크나 파일명을 감싸지 마세요. 반드시 마크다운 하이퍼링크 형식인 [자료명](URL)을 사용하세요.
    
    [실시간 프로젝트 원장 데이터]
    {context_data}
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[vertex_tool],
                system_instruction=pm_instruction,
                temperature=0.1
            )
        )
        return jsonify({"answer": response.text})
    except Exception as e:
        return jsonify({"answer": f"원장 데이터를 분석하는 중 오류가 발생했습니다: {str(e)}"})

if __name__ == '__main__':
    app.run(port=5000, debug=True)