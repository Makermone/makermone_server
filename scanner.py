import vertexai
from vertexai.generative_models import GenerativeModel
import os

# 신분증 장착
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "vertex_key.json"
PROJECT_ID = "makermone-ai-core"

# 1.5와 2.0 모델 모두 검사
models_to_test = ["gemini-1.5-flash-002", "gemini-2.0-flash"]

print("🔍 메이커몬 클라우드 정밀 스캐너 구동 중...\n")

vertexai.init(project=PROJECT_ID, location="us-central1")

for model_name in models_to_test:
    try:
        model = GenerativeModel(model_name)
        response = model.generate_content("테스트, 10자 이내로 대답해.")
        print(f"✅ [통신 뚫림!] 모델: {model_name} -> AI 응답: {response.text}")
    except Exception as e:
        print(f"❌ [실패] 모델: {model_name} -> 사유: {str(e)[:100]}...")