import requests
import os
from dotenv import load_dotenv

# .env 파일의 환경변수를 불러옵니다.
load_dotenv()

# 직접 입력했던 키 대신 아래와 같이 수정합니다.
API_KEY = os.getenv("GOOGLE_API_KEY")

# 모델 목록 조회 주소
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"

print("---- [모델 목록 조회 시작] ----")
response = requests.get(url)

if response.status_code == 200:
    print("✅ 연결 성공!")
else:
    print(f"❌ 연결 실패 (상태 코드: {response.status_code})")