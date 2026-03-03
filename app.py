import streamlit as st
import requests
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

# --- 1. 기본 설정 및 보안 ---
load_dotenv() 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

st.set_page_config(page_title="메이커몬 AI 포털", page_icon="🤖", layout="wide")

# [위장술] Streamlit 기본 메뉴 숨기기
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

if not GOOGLE_API_KEY:
    st.error("🚨 환경 변수에 GOOGLE_API_KEY가 설정되지 않았습니다.")
    st.stop()

# URL에서 명찰 가져오기 (없으면 기본값 'GUEST' 부여)
client_code = st.query_params.get("client_code", "GUEST")
genai.configure(api_key=GOOGLE_API_KEY)

# =====================================================================
# 🔀 [분기 A] 일반 방문객 (GUEST) 모드
# =====================================================================
if client_code == "GUEST":
    with st.sidebar:
        st.title("💡 메이커몬 안내")
        st.markdown("---")
        st.info("**접속 상태:** 일반 방문자")
        st.success("**담당 AI:** 메이커몬 공식 어시스턴트")
        st.markdown("### 📌 무엇을 도와드릴까요?")
        st.markdown("- 회사 소개 및 서비스 안내\n- 제조/양산 프로세스 상담\n- 견적 및 미팅 문의")

    st.title("🤖 메이커몬 AI 어시스턴트")
    st.markdown("안녕하세요!")
    st.markdown("AI 자동화 Micro-Factory 플랫폼 메이커몬입니다. 무엇이든 편하게 물어보세요.")
    st.markdown("---")

    system_instruction = """
    당신은 팹리스 제조 플랫폼 '메이커몬'의 공식 AI 어시스턴트입니다.
    현재 방문자는 아직 프로젝트를 진행하지 않은 '일반 고객'입니다.
    메이커몬은 단순 제조 대행이 아니라, "엔지니어링 기반의 전주기(Full-cycle) 제품 개발 관리 및 PM(Project Management) 서비스"이며,
    제품 기획부터 기구 설계, 목업 제작, 금형, 양산까지 한 번에 해결하는 전문 제품 제조 플랫폼입니다.
    서비스에 대해 친절하게 안내하고, 구체적인 견적이나 미팅이 필요한 경우 "공식 홈페이지의 문의하기를 이용해 주시면 담당자가 신속히 연락드리겠습니다"라고 정중히 응대하세요.
    """
    
    # 일반 응대는 자연스럽고 친절해야 하므로 창의성(Temperature)을 0.7로 설정
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(temperature=0.7) 
    )

# =====================================================================
# 🔀 [분기 B] 기존 프로젝트 고객 (PM) 모드
# =====================================================================
else:
    def get_pm_data(code):
        GAS_URL = "https://script.google.com/macros/s/AKfycbz4JTfSxbdKMILhG2X9GepP1ZiNjFu7cYTUsqIALZmtL0k3FudVkzNdwK40n7FhZavM/exec"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        response = requests.get(f"{GAS_URL}?action=get_pm_data&client_code={code}", headers=headers, allow_redirects=True)
        if response.status_code == 200:
            return response.json()
        return None

    with st.spinner("프로젝트 원장 데이터를 동기화 중입니다..."):
        pm_data = get_pm_data(client_code)

    if not pm_data:
        st.error("데이터 서버와 통신할 수 없습니다.")
        st.stop()

    with st.sidebar:
        st.title("📊 프로젝트 대시보드")
        st.markdown("---")
        st.info(f"**진행 고객사:** [{client_code}]")
        st.success("**담당 PM:** 메이커몬 AI 전담 PM")
        st.markdown("### 📌 시스템 기능")
        st.markdown("- 실시간 일정 트래킹\n- 최신 리포트 요약\n- 부품/도면 원장 검색")
        st.markdown("---")
        show_raw_data = st.toggle("현재 수신된 DB 원장 보기")
        if show_raw_data:
            st.json(pm_data)

    st.title("🤖 메이커몬 전담 PM AI")
    st.markdown("고객님, 환영합니다. 프로젝트 진행 상황, 일정, 도면에 대해 무엇이든 말씀해 주세요.")
    st.markdown("---")

    system_instruction = f"""
    당신은 팹리스 제조 플랫폼 '메이커몬'의 무결점 전담 AI PM입니다.
    현재 고객사 코드는 [{client_code}] 입니다.
    [절대 원칙] 반드시 아래 제공된 JSON 데이터를 배열 1번부터 끝까지 꼼꼼히 스캔하여 팩트 기반으로 답변하세요.
    [프로젝트 원장 데이터]
    {json.dumps(pm_data, ensure_ascii=False, indent=2)}
    """
    
    # PM은 사실만 말해야 하므로 창의성(Temperature)을 0.1로 억제
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(temperature=0.1) 
    )

# --- 공통 챗봇 화면 렌더링 ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])

for message in st.session_state.chat_session.history:
    role = "user" if message.role == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(message.parts[0].text)

# 모드에 따라 입력창 문구 변경
prompt_placeholder = "메이커몬에 대해 궁금한 점을 입력하세요..." if client_code == "GUEST" else "메이커몬 PM에게 질문을 입력하세요... (예: 목업 진행상황 알려줘)"

# (app.py 맨 아래 부분 수정)

if prompt := st.chat_input(prompt_placeholder):
    # 1. 고객 질문 화면에 출력
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # 2. AI 대답 생성 및 출력
    with st.chat_message("assistant"):
        spinner_msg = "메이커몬 AI가 답변을 작성 중입니다..." if client_code == "GUEST" else "PM이 원장 데이터를 꼼꼼히 스캔 중입니다..."
        with st.spinner(spinner_msg):
            try:
                # 챗봇이 생각하고 대답을 뱉어냅니다.
                response = st.session_state.chat_session.send_message(prompt)
                answer_text = response.text
                st.markdown(answer_text)
                
                # 💡 [도청기 장착] 질문과 '대답'을 묶어서 구글 시트로 조용히 쏩니다!
                # 캡처본에 있던 대표님의 배포 URL을 그대로 적용했습니다.
                GAS_URL = "https://script.google.com/macros/s/AKfycbz4JTfSxbdKMILhG2X9GepP1ZiNjFu7cYTUsqIALZmtL0k3FudVkzNdwK40n7FhZavM/exec"
                payload = {
                    "action": "log_inquiry",
                    "client_code": client_code,
                    "query": prompt,
                    "answer": answer_text # AI가 방금 한 대답(text)을 통째로 추가!
                }
                
                # 챗봇 속도에 영향을 주지 않도록 2초만 던지고 빠집니다.
                try:
                    requests.post(GAS_URL, json=payload, timeout=2)
                except:
                    pass
                    
            except Exception as e:
                st.error(f"AI 응답 에러: {e}")