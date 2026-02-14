import requests
import json

# =========================================================
# [중요] 아래 주소를 아까 배포 성공했을 때 나온 'Service URL'로 바꿔주세요!
# 끝에 /chat 은 꼭 붙여야 합니다.
# 예시: "https://makermon-api-xyz.run.app/chat"
url = "https://makermon-api-625714296992.asia-northeast3.run.app/chat" 
# =========================================================

# 테스트 1: "메이커몬 3D 프린팅 하나요?" (데이터 파일에 '안 한다'고 적어놨음)
payload_1 = {
    "user_id": "guest",
    "question": "혹시 3D 프린팅 의뢰도 받으시나요?"
}

# 테스트 2: "2월 계획이 뭔가요?" (데이터 파일에 '창업도약패키지'라고 적어놨음)
payload_2 = {
    "user_id": "samsung_admin", # 관리자 모드로 질문
    "question": "2026년 2월의 주요 사업 계획을 알려주세요."
}

def send_question(test_name, data):
    print(f"\n--- [{test_name}] 질문 전송 중... ---")
    try:
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            print(f"✅ AI 답변: {response.json()['answer']}")
        else:
            print(f"❌ 에러 발생: {response.text}")
            
    except Exception as e:
        print(f"❌ 연결 실패: {e}")

# 실행
if __name__ == "__main__":
    send_question("일반 고객 테스트", payload_1)
    send_question("관리자 테스트", payload_2)