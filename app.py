import streamlit as st
import os
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. 환경 설정 및 클라이언트 초기화
load_dotenv() 

# -------------------------------------------------------------
# 파일 연결에 필요한 안정적인 API 버전을 명시합니다.
# 현재 사용하시는 코드에서 이 방식이 작동하는 것을 확인했으므로, 이 버전을 사용합니다.
# -------------------------------------------------------------
client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT"),
    api_key= os.getenv("AZURE_OAI_KEY"),
    api_version="2024-05-01-preview" 
)

# Assistant ID는 미리 생성하여 환경 변수 등에 저장해야 합니다.
ASSISTANT_ID = "gpt-4o-mini" 

# Streamlit 세션 상태 초기화
if "thread_id" not in st.session_state:
    try:
        # 챗봇 시작 시 새로운 Thread 생성
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        st.session_state.messages = []
    except Exception as e:
        st.error(f"Assistant Thread 생성 실패: {e} (ASSISTANT_ID 및 API 버전 확인 필요)")
        st.stop()
# -------------------------------------------------------------


# -------------------------------------------------------------
# 2. UI 및 파일 업로드
# -------------------------------------------------------------
st.title("💰 연말정산 서류 분석 챗봇 (Attachments 기반)")

# 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 파일 업로더
uploaded_file = st.file_uploader("분석할 연말정산 서류(PDF/이미지)를 업로드하세요.", 
                                 type=["pdf", "png", "jpg", "jpeg"], 
                                 key="tax_doc_uploader")


# -------------------------------------------------------------
# 3. 사용자 입력 및 Run 실행 (파일 처리 포함)
# -------------------------------------------------------------
if prompt := st.chat_input("서류에 대한 질문이나 분석 요청을 입력하세요."):
    
    # 1. 사용자 메시지 화면 표시 및 세션 저장
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    file_id_to_attach = None
    
    # 2. 파일 업로드 및 File ID 획득
    if uploaded_file is not None:
        try:
            with st.spinner(f"파일 업로드 중: {uploaded_file.name}"):
                # 파일을 OpenAI 서버에 업로드하고 File ID를 받습니다.
                file = client.files.create(
                    file=uploaded_file,
                    purpose="assistants" # 파일 검색 목적으로 사용
                )
            file_id_to_attach = file.id
            st.info(f"파일 업로드 완료. (File ID: {file.id})")
        
        except Exception as e:
            st.error(f"파일 업로드 실패: {e}")
            st.stop()


    # 3. Thread에 메시지 추가 (attachments 연결)
    attachments_list = []
    if file_id_to_attach:
        # 파일이 성공적으로 업로드되었을 때만 attachments 매개변수를 구성합니다.
        attachments_list = [
            {
                "file_id": file_id_to_attach,
                "tools": [{"type": "file_search"}]
            }
        ]

    message_params = {
        "thread_id": st.session_state.thread_id,
        "role": "user",
        "content": prompt,
    }
    
    # attachments가 있을 경우에만 메시지 생성 매개변수에 추가
    if attachments_list:
         message_params["attachments"] = attachments_list
    
    try:
        client.beta.threads.messages.create(**message_params)
    except Exception as e:
        # 이전에 발생했던 'unexpected keyword argument' 오류는 이 단계에서 API 버전을 정확히 맞춰야 해결됩니다.
        st.error(f"메시지 추가 실패: {e}")
        st.stop()
    

    # 4. Run 실행 및 결과 대기
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        try:
            # Run을 실행할 때, Assistant는 파일 검색 도구를 사용하여 첨부된 파일을 분석합니다.
            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSISTANT_ID
            )
        except Exception as e:
            placeholder.error(f"Assistant Run 실행 실패: {e}")
            st.stop()
            
        
        # Run 상태 대기 (비동기 처리)
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
                order='desc',
                limit=1
            )
            # Assistant의 최종 응답 텍스트 추출
            assistant_reply = messages.data[0].content[0].text.value
            
        else:
            assistant_reply = f"오류 발생 또는 Run 상태: {run.status}"

        # 5. 응답 출력 및 저장
        placeholder.markdown(assistant_reply)
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})


