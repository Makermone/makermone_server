import streamlit as st
import requests
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

load_dotenv() 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- 2. 페이지 기본 설정 ---
st.set_page_config(page_title="메이커몬 PM 포털", page_icon="🤖", layout="wide")

# [완벽 위장술] Streamlit 기본 메뉴, 헤더, 푸터 완전히 숨기기
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# ... (이하 기존 코드 동일)
if not GOOGLE_API_KEY:
    st.error("🚨 환경 변수에 GOOGLE_API_KEY가 설정되지 않았습니다.")
    st.stop()

client_code = st.query_params.get("client_code")

if not client_code:
    st.warning("⚠️ URL에 고객사 명찰이 없습니다. 주소창 끝에 `?client_code=JD` 를 붙여주세요.")
    st.stop() 

# --- 2. 데이터 라우터 호출 (캐시 완전 삭제!) ---
# @st.cache_data 부분을 삭제하여, 새로고침 할 때마다 무조건 구글 시트의 최신 상태를 퍼오도록 수정했습니다.
def get_pm_data(code):
    GAS_URL = "https://script.google.com/macros/s/AKfycbz4JTfSxbdKMILhG2X9GepP1ZiNjFu7cYTUsqIALZmtL0k3FudVkzNdwK40n7FhZavM/exec"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    response = requests.get(f"{GAS_URL}?action=get_pm_data&client_code={code}", headers=headers, allow_redirects=True)
    if response.status_code == 200:
        return response.json()
    return None

with st.spinner("프로젝트 원장 데이터를 동기화 중입니다... (실시간 로드 중)"):
    pm_data = get_pm_data(client_code)

if not pm_data:
    st.error("데이터 서버와 통신할 수 없습니다.")
    st.stop()

# --- 3. UI/UX 레이아웃 분할 ---
with st.sidebar:
    st.title("📊 프로젝트 대시보드")
    st.markdown("---")
    st.info(f"**진행 고객사:** [{client_code}]")
    st.success("**담당 PM:** 메이커몬 AI 전담 PM")
    
    st.markdown("### 📌 시스템 기능")
    st.markdown("- 실시간 일정 트래킹\n- 최신 리포트 요약\n- 부품/도면 원장 검색")
    st.markdown("---")
    st.markdown("### 🛠️ 관리자 디버그 툴")
    show_raw_data = st.toggle("현재 수신된 DB 원장 보기")
    if show_raw_data:
        st.json(pm_data)

st.title("🤖 메이커몬 전담 PM AI")
st.markdown("고객님, 환영합니다. 프로젝트 진행 상황, 일정, 도면에 대해 무엇이든 말씀해 주세요.")
st.markdown("---")

# --- 4. 무결점 AI 두뇌 세팅 ---
genai.configure(api_key=GOOGLE_API_KEY)

system_instruction = f"""
당신은 팹리스 제조 플랫폼 '메이커몬'의 1인 자동화 팩토리를 지원하는 무결점 전담 AI PM입니다.
현재 고객사 코드는 [{client_code}] 이며, '고객님 전담 PM'이라고 정중히 응대하세요.

[절대 원칙: 강제 데이터 탐색 알고리즘]
당신은 사용자 질문에 답하기 전, 대충 훑어보고 답변을 지어내는 행위(Lazy Evaluation)가 엄격히 금지됩니다. 
반드시 아래 순서대로 제공된 JSON 데이터를 배열 1번부터 끝까지 '글자 단위'로 스캔하세요.

1. 일정 관련: 'schedule' 배열의 모든 항목 스캔.
2. 진행상황/이슈 관련 (예: 목업, 조립, 설계상태 등): 'reports' 배열 내의 모든 `report_title`과 `report_summary`를 처음부터 끝까지 정독.
3. 부품/도면 관련: 'parts' 배열의 모든 항목 스캔.

질문을 받으면 데이터셋에 존재하는 모든 연관 키워드를 추출하여 팩트를 확인한 뒤 답변하세요. 찾은 정보는 반드시 [문서 보기](drive_link) 형태의 마크다운 링크를 포함하세요.

[프로젝트 원장 데이터]
{json.dumps(pm_data, ensure_ascii=False, indent=2)}
"""

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction=system_instruction,
    generation_config=genai.GenerationConfig(temperature=0.1) 
)

if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])

# --- 5. 대화 렌더링 ---
for message in st.session_state.chat_session.history:
    role = "user" if message.role == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(message.parts[0].text)

if prompt := st.chat_input("메이커몬 PM에게 질문을 입력하세요..."):
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.chat_message("assistant"):
        with st.spinner("PM이 원장 데이터를 꼼꼼히 스캔하여 팩트를 확인 중입니다..."):
            try:
                response = st.session_state.chat_session.send_message(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"AI 응답 에러: {e}")