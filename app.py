import streamlit as st
import os
import json
import base64 
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. 환경 변수 로드 (.env 파일에 AZURE_OAI_KEY, AZURE_OAI_ENDPOINT 설정 필수)
load_dotenv() 

# -------------------------------------------------------------
# 2. 설정 및 도구 함수 정의 (NameError 방지 위해 상단에 위치)
# -------------------------------------------------------------
deployment_name = "gpt-4o-mini" 

def get_tax_tip_for_category(category):
    """주요 연말정산 공제 항목에 대한 절세 팁을 제공하는 헬퍼 함수"""
    tips = {
        "insurance": "보장성 보험료는 연 100만 원 한도로 12% 세액 공제됩니다. 맞벌이 부부의 경우, 급여가 적은 배우자 명의로 계약하는 것이 유리할 수 있습니다.",
        "medical": "총 급여액의 3%를 초과하는 금액에 대해 공제됩니다. 특히 산후조리원 비용(200만 원 한도)과 난임 시술비는 공제율이 높으니 관련 영수증을 잘 챙기세요.",
        "education": "본인 교육비는 전액 공제되며, 자녀 교육비는 1인당 한도가 있습니다. 취학 전 아동의 학원비는 공제가능하나, 초/중/고교 학원비는 공제 대상이 아닙니다.",
        "housing": "주택 마련 저축(청약 저축 등)은 연 240만 원 한도로 공제됩니다. 무주택 세대주 여부를 반드시 확인해야 합니다.",
        "pension": "연금저축 및 퇴직연금은 세액 공제율이 높습니다. 총 급여액에 따라 공제 한도와 공제율이 달라지니 최대한 활용하는 것이 좋습니다."
    }
    selected_tip = tips.get(category.lower(), "해당 공제 항목에 대한 일반적인 절세 팁을 찾을 수 없습니다. (카테고리: " + category + ")")
    return json.dumps({"category": category, "tip": selected_tip})


tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "get_tax_tip_for_category",
            "description": "사용자가 질문한 연말정산 공제 항목(예: 보험료, 의료비, 교육비 등)에 대한 구체적인 절세 팁과 공제 요건을 조회합니다. 카테고리는 반드시 영어로 변환하여 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "The tax deduction category (e.g., 'insurance', 'medical', 'education', 'housing', 'pension')."},
                },
                "required": ["category"],
            },
        }
    }
]

available_functions = {
    "get_tax_tip_for_category": get_tax_tip_for_category,
}

# -------------------------------------------------------------
# 3. Streamlit UI 및 클라이언트 설정
# -------------------------------------------------------------
st.title("💰 연말정산 공제 팁 챗봇")

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OAI_KEY"),
    api_version="2024-05-01-preview",
    azure_endpoint=os.getenv("AZURE_OAI_ENDPOINT")
)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

uploaded_file = st.file_uploader("연말정산 서류(PDF, PNG, JPG)를 여기에 첨부하세요.", type=["pdf", "png", "jpg", "jpeg"], key="tax_doc_uploader")

SYSTEM_PROMPT = """당신은 '연말정산 절세 코치'입니다. 당신의 목표는 사용자가 합법적으로 세액 공제나 소득 공제를 최대한 많이 받을 수 있도록 구체적이고 실용적인 팁과 요건을 안내하는 것입니다.
1. 역할: ...
2. 서류 분석: ...
3. 도구 사용: ...
4. 태도: ...
5. 제한: ..."""


# -------------------------------------------------------------
# 4. 사용자 입력 처리 및 API 호출 (오류 방지 최종 로직)
# -------------------------------------------------------------
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    
    # 1. 현재 사용자 메시지 구성 (API 전송용)
    with st.chat_message("user"):
        st.markdown(prompt)
        
        # API 전송용 멀티모달 메시지 리스트 생성: 항상 리스트로 시작
        current_api_user_content = []
        
        # 파일 첨부 처리 및 Base64 인코딩
        if uploaded_file is not None:
            try:
                file_bytes = uploaded_file.read()
                encoded_file = base64.b64encode(file_bytes).decode('utf-8')
                mime_type = uploaded_file.type 
                
                current_api_user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{encoded_file}",
                        "detail": "high"
                    }
                })
                st.info(f"첨부된 파일({uploaded_file.name}, 타입: {mime_type})을 분석 요청에 포함했습니다.")
                
            except Exception as e:
                st.error(f"파일 처리 중 오류가 발생했습니다: {e}")

        # 텍스트 프롬프트를 API 요청 리스트에 추가
        current_api_user_content.append({"type": "text", "text": prompt})
        
    # **오류 방지 1:** 세션 상태에는 순수한 텍스트 문자열만 저장 (History 표시용)
    st.session_state.messages.append({"role": "user", "content": prompt})


    # -------------------------------------------------------------------
    # 2. API 요청 메시지 리스트 구성
    # -------------------------------------------------------------------
    with st.chat_message("assistant"):
        placeholder = st.empty()

        # 시스템 메시지 추가
        messages_for_completion = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # **오류 방지 2:** 기존 세션 기록 추가 (엄격한 안전 필터링)
        # 과거 메시지는 반드시 단일 문자열 content를 가져야 함.
        safe_history = []
        for m in st.session_state.messages[:-1]: # 마지막 요소(현재 텍스트 프롬프트) 제외
            content = m.get("content")
            if content and isinstance(content, str) and content.strip():
                safe_history.append({"role": m["role"], "content": content})
            # 만약 과거 메시지가 문자열이 아닌 다른 형식이었다면 (오류 유발 가능성 있음), 해당 메시지는 건너뜀
        
        messages_for_completion.extend(safe_history)
        
        # 현재 사용자의 최종 API 요청 메시지 추가 (멀티모달 객체 리스트 형식)
        messages_for_completion.append({
            "role": "user",
            "content": current_api_user_content
        })


        # -------------------------------------------------------------------
        # 3. API 호출 및 도구 사용 로직 (Line 163이 여기서 시작됩니다.)
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
            # 1차 응답 메시지를 히스토리에 추가하여 2차 호출 시 모델에게 전달
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

        # 4. AI 응답 화면에 출력 및 저장
        placeholder.markdown(assistant_reply)
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
