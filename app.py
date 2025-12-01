import streamlit as st
import os
import json
import requests
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()

# -------------------------------------------------------------
# 2. Azure OpenAI 클라이언트 및 Assistant 설정
# -------------------------------------------------------------
deployment_name = "gpt-4o-mini" # 채팅 모델 이름 (Assistant와는 별개로 사용)
# Assistant API는 모델 배포 이름이 아닌 모델 이름(gpt-4o-mini)을 직접 사용합니다.

client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT"),
    api_key= os.getenv("AZURE_OAI_KEY"),
    api_version="2024-05-01-preview" # Assistant API는 2024-05-01-preview 버전 이상이 필요
)

# Assistant ID와 Vector Store ID는 한번 생성되면 변경되지 않습니다.
# (실제 환경에서는 ID를 하드코딩하지 않고 환경 변수 등으로 관리하는 것이 좋습니다.)
ASSISTANT_ID = os.getenv("AZURE_ASSISTANT_ID", "asst_placeholder_id") # 실제 Assistant ID로 대체 필요
VECTOR_STORE_ID = os.getenv("AZURE_VECTOR_STORE_ID", "vs_0HHlYCADIv0m8l3mWHLxbQp4")

# Streamlit 세션 상태에 Thread ID와 File ID 저장
if "thread_id" not in st.session_state:
    # 챗봇 시작 시 새로운 Thread 생성
    try:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        st.session_state.file_ids = []
    except Exception as e:
        st.error(f"Thread 생성 실패: {e}")
        st.stop()


# -------------------------------------------------------------
# 3. Streamlit UI 및 파일 업로드 처리
# -------------------------------------------------------------
st.title("💰 연말정산 서류 분석 챗봇 (Assistant API)")

# 4. 화면에 기존 대화 내용 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


uploaded_file = st.file_uploader("연말정산 서류(PDF, PNG, JPG)를 여기에 첨부하세요.", type=["pdf", "png", "jpg", "jpeg"], key="tax_doc_uploader")


# -------------------------------------------------------------
# 5. 사용자 입력 받기 및 Assistant Run 실행
# -------------------------------------------------------------
if prompt := st.chat_input("서류 분석을 요청하거나 질문하세요."):
    
    # 1. 사용자 메시지 화면 표시
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 2. 파일 처리 및 Assistant File 객체 생성
    file_ids_to_add = []
    if uploaded_file is not None:
        try:
            # 파일을 Azure OpenAI에 업로드하여 File ID를 받음
            with st.spinner(f"파일 업로드 중: {uploaded_file.name}"):
                file = client.files.create(
                    file=uploaded_file,
                    purpose="assistants" # 파일 검색 목적으로 사용
                )
            file_ids_to_add.append(file.id)
            st.session_state.file_ids.append(file.id)
            st.info(f"파일 업로드 완료. (File ID: {file.id})")
        
        except Exception as e:
            st.error(f"파일 업로드 실패: {e}")

    # 3. Thread에 메시지 추가
    try:
        # 메시지에 파일 ID를 연결하여 파일 내용을 분석하도록 지시
        message = client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt,
            file_ids=file_ids_to_add
        )
    except Exception as e:
        st.error(f"메시지 추가 실패: {e}")
        st.stop()
    

    # 4. Run 실행 및 결과 대기
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        try:
            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSISTANT_ID
            )
        except Exception as e:
            placeholder.error(f"Assistant Run 실행 실패: {e}")
            st.stop()
            
        
        # Looping until the run completes (비동기 처리)
        with st.spinner("AI가 서류를 분석하고 답변을 생성 중입니다..."):
            while run.status in ['queued', 'in_progress', 'cancelling']:
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id
                )
        
        assistant_reply = ""
        
        if run.status == 'completed':
            messages = client.beta.threads.messages.list(
                thread_id=st.session_state.thread_id,
                order='desc', # 최신 메시지부터 가져옴
                limit=1
            )
            # Assistant의 최종 응답 텍스트 추출
            assistant_reply = messages.data[0].content[0].text.value
            
        elif run.status == 'requires_action':
             assistant_reply = "Assistant가 함수 호출을 요청했지만, 이 버전에서는 지원하지 않습니다."
        else:
            assistant_reply = f"오류 발생 또는 Run 상태: {run.status}"

        # 5. AI 응답 화면에 출력 및 저장
        placeholder.markdown(assistant_reply)
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
