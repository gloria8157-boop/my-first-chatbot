import streamlit as st
import os
import json
import requests
from openai import AzureOpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone 
import warnings
import base64 

# 1. 환경 변수 로드 (.env 파일에 AZURE_OAI_KEY, AZURE_OAI_ENDPOINT 설정 필수)
load_dotenv() 

# -------------------------------------------------------------
# 설정 및 도구 정의 (생략) - 이 부분은 문제가 없는 것으로 가정합니다.
# -------------------------------------------------------------
deployment_name = "gpt-4o-mini"
# ... (get_tax_tip_for_category 함수, tools_definitions, available_functions 정의 생략) ...

# -------------------------------------------------------------
# 3. Streamlit UI 및 챗봇 로직
# -------------------------------------------------------------

st.title("💰 연말정산 공제 팁 챗봇")

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OAI_KEY"),
    api_version="2024-05-01-preview",
    azure_endpoint=os.getenv("AZURE_OAI_ENDPOINT")
)

# 대화기록(Session State) 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 화면에 기존 대화 내용 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 파일 업로더
uploaded_file = st.file_uploader("연말정산 서류(PDF, PNG, JPG)를 여기에 첨부하세요.", type=["pdf", "png", "jpg", "jpeg"], key="tax_doc_uploader")

# 시스템 프롬프트 정의
SYSTEM_PROMPT = """당신은 '연말정산 절세 코치'입니다. 당신의 목표는 사용자가 합법적으로 세액 공제나 소득 공제를 최대한 많이 받을 수 있도록 구체적이고 실용적인 팁과 요건을 안내하는 것입니다.
1. 역할: ...
2. 서류 분석: ...
3. 도구 사용: ...
4. 태도: ...
5. 제한: ..."""


# -------------------------------------------------------------
# 4. 사용자 입력 처리 및 API 호출 (BadRequestError 방지 최종 코드)
# -------------------------------------------------------------
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    
    # 1. 현재 사용자 메시지 구성 (UI 표시 및 API 전송용)
    with st.chat_message("user"):
        st.markdown(prompt)
        
        # API 전송용 멀티모달 메시지 리스트 생성: 항상 리스트로 시작
        current_api_user_content = []
        
        # 파일 첨부 처리 및 Base64 인코딩
        is_file_attached = False
        if uploaded_file is not None:
            try:
                file_bytes = uploaded_file.read()
                encoded_file = base64.b64encode(file_bytes).decode('utf-8')
                mime_type = uploaded_file.type 
                
                # 파일 데이터를 API 요청 리스트에 추가
                current_api_user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{encoded_file}",
                        "detail": "high"
                    }
                })
                st.info(f"첨부된 파일({uploaded_file.name}, 타입: {mime_type})을 분석 요청에 포함했습니다.")
                is_file_attached = True
                
            except Exception as e:
                st.error(f"파일 처리 중 오류가 발생했습니다: {e}")
                
        # 텍스트 프롬프트를 API 요청 리스트에 추가
        current_api_user_content.append({"type": "text", "text": prompt})
        
    # **오류 방지 핵심 1:** 세션 상태에는 순수한 텍스트 문자열만 저장
    st.session_state.messages.append({"role": "user", "content": prompt})


    # -------------------------------------------------------------------
    # 2. API 요청 메시지 리스트 구성
    # -------------------------------------------------------------------
    with st.chat_message("assistant"):
        placeholder = st.empty()

        # 시스템 메시지 추가
        messages_for_completion = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # **오류 방지 핵심 2:** 기존 세션 기록 추가 (안전 필터링)
        safe_history = []
        for m in st.session_state.messages[:-1]:
            # content가 문자열이고 비어있지 않은 경우에만 API History에 포함
            if m.get("content") and isinstance(m["content"], str) and m["content"].strip():
                safe_history.append({
                    "role": m["role"],
                    "content": m["content"]
                })
        
        messages_for_completion.extend(safe_history)
        
        # 현재 사용자의 최종 API 요청 메시지 추가
        messages_for_completion.append({
            "role": "user",
            "content": current_api_user_content
        })


        # -------------------------------------------------------------------
        # 3. API 호출 및 도구 사용 로직 (Line 177이 여기서 시작됩니다.)
        # -------------------------------------------------------------------
        response = client.chat.completions.create( 
            model=deployment_name, 
            messages=messages_for_completion,
            tools=tools_definitions,
            tool_choice="auto",
        )

        response_message = response.choices[0].message
        assistant_reply = ""

        # 도구 호출이 필요한 경우 (1차 호출)
        if response_message.tool_calls:
            # 1차 응답 메시지 추가 (API 재호출용)
            messages_for_completion.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                function_response = available_functions[function_name](**function_args)

                messages_for_completion.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })

            # 2차 호출: 도구 결과를 바탕으로 최종 답변 생성
            final_response = client.chat.completions.create(
                model=deployment_name,
                messages=messages_for_completion,
            )
            assistant_reply = final_response.choices[0].message.content

        # 도구 호출이 필요 없거나 2차 호출 결과가 나온 경우
        else:
            assistant_reply = response_message.content

        # (4) AI 응답 화면에 출력 및 저장
        placeholder.markdown(assistant_reply)
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})






