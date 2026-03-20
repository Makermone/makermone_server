import streamlit as st
import requests
import os
import json
from dotenv import load_dotenv

# 🚀 [최신 무기] 신형 통합 SDK 사용
from google import genai
from google.genai import types

load_dotenv() 

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")
DATASTORE_ID = "maker-knowledge_1773908104525"

st.set_page_config(page_title="메이커몬 AI 포털", page_icon="🤖", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

client_code = st.query_params.get("client_code", "GUEST")

# =====================================================================
# 🚀 신형 엔진 및 지식 창고 세팅 (미국 서버로 강제 고정)
# =====================================================================
@st.cache_resource
def get_ai_client():
    # 1. Gemini 2.0이 존재하는 미국 중부(us-central1)로 연결
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")
    
    # 2. 지식 창고(Data Store) 풀 경로 지정
    datastore_path = f"projects/{PROJECT_ID}/locations/global/collections/default_collection/dataStores/{DATASTORE_ID}"
    
    # 3. 검색 도구 장착
    vertex_tool = types.Tool(
        retrieval=types.Retrieval(
            vertex_ai_search=types.VertexAISearch(datastore=datastore_path)
        )
    )
    return client, vertex_tool

client, vertex_tool = get_ai_client()
MODEL_NAME = "gemini-2.5-flash"

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
    당신은 메이커몬(Makermone)의 수석 엔지니어이자 전문 PM입니다.
    관련 자료 전달 및 추가 문의에 대한 사항은 대표 이메일(aimwon01@gmail.com) 또는 홈페이지의 문의하기를 통해 가능하다고 안내하세요.
    1. [전문성과 PM 역량 어필]: 백과사전처럼 딱딱하게 대답하지 마세요. 
    2. [단가 철벽 방어]: 구체적인 단가나 가격을 물어보면 절대 숫자를 말하지 말고 방어하세요.
    3. [가독성 극대화]: 긴 문장은 피하고 불릿 포인트를 사용하세요.
    4. [영업적 클로징]: 답변의 마지막에는 항상 도면 전달을 유도하는 멘트를 넣으세요.
    """
    temperature_setting = 0.7

# =====================================================================
# 🔀 [분기 B] 기존 프로젝트 고객 (PM) 모드
# =====================================================================
else:
    def get_pm_data(code):
        GAS_URL = "https://script.google.com/macros/s/AKfycbx1pr6BRUutkpO72hNNI0gjrkYxlXK88MRFZScp-kWUgqTSYNirRVETSVIE5WvT5P8v/exec"
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
        st.markdown("---")
        show_raw_data = st.toggle("현재 수신된 DB 원장 보기")
        if show_raw_data:
            st.json(pm_data)

    st.title("🤖 메이커몬 전담 PM AI")
    st.markdown("---")

    system_instruction = f"""
    당신은 팹리스 제조 플랫폼 '메이커몬'의 무결점 전담 AI PM입니다.
    [절대 원칙] 제공된 JSON 데이터를 팩트 기반으로 답변하세요.
    [🚨 링크 제공 절대 규칙] 절대 백틱(`) 기호를 쓰지 말고 [자료명](URL) 형식을 사용하세요.
    
    [프로젝트 원장 데이터]
    {json.dumps(pm_data, ensure_ascii=False, indent=2)}
    """
    temperature_setting = 0.1

# --- 공통 챗봇 화면 렌더링 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt_placeholder = "메이커몬에 대해 궁금한 점을 입력하세요..." if client_code == "GUEST" else "메이커몬 PM에게 질문을 입력하세요..."

if prompt := st.chat_input(prompt_placeholder):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    history_contents = [
        types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=m["content"])])
        for m in st.session_state.messages
    ]

    with st.chat_message("assistant"):
        spinner_msg = "분석 중입니다..."
        with st.spinner(spinner_msg):
            try:
                # 🚀 신형 엔진 호출
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=history_contents,
                    config=types.GenerateContentConfig(
                        tools=[vertex_tool],
                        system_instruction=system_instruction,
                        temperature=temperature_setting
                    )
                )
                answer_text = response.text
                st.markdown(answer_text)
                st.session_state.messages.append({"role": "assistant", "content": answer_text})
                
                # 로그 전송 로직
                GAS_URL = "https://script.google.com/macros/s/AKfycbx1pr6BRUutkpO72hNNI0gjrkYxlXK88MRFZScp-kWUgqTSYNirRVETSVIE5WvT5P8v/exec"
                payload = {"action": "log_inquiry", "client_code": client_code, "query": prompt, "answer": answer_text}
                try:
                    requests.post(GAS_URL, json=payload, timeout=8)
                except:
                    pass
            except Exception as e:
                st.error(f"AI 응답 에러: {e}")