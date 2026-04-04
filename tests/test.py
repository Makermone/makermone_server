import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel

# 1. 신분증(JSON 키) 파일에서 진짜 프로젝트 ID를 강제로 뽑아냅니다.
KEY_PATH = "vertex_key.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

try:
    with open(KEY_PATH, 'r') as f:
        key_data = json.load(f)
        REAL_PROJECT_ID = key_data['project_id']
    
    print("==============================================")
    print(f"🔑 신분증에 기록된 진짜 프로젝트 ID: [{REAL_PROJECT_ID}]")
    print("==============================================\n")

    # 2. 뽑아낸 진짜 ID로 구글 AI 심장에 직접 연결합니다.
    vertexai.init(project=REAL_PROJECT_ID, location="us-central1")
    model = GenerativeModel("gemini-1.5-flash")
    
    print("⏳ AI 모델에 연결 중입니다...")
    response = model.generate_content("안녕하세요, 10자 이내로 짧게 대답해주세요.")
    
    print("\n✅ [통신 성공!] AI 응답:", response.text)
    print("🎉 에러 해결! `.env` 파일의 GCP_PROJECT_ID를 위 화면에 나온 진짜 ID로 수정하시면 끝납니다.")

except Exception as e:
    print("\n❌ [여전히 통신 실패!] 에러 메시지:", str(e))
    print("🚨 [최종 판결]: 프로젝트 ID 문제가 아닙니다. 구글 클라우드에서 'Vertex AI API' 전원 스위치가 꺼져 있습니다!")