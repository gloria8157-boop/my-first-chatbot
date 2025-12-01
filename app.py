import streamlit as st
import os
import json
import requests
from openai import AzureOpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone # 시간 계산을 위해 추가
import warnings

# 1. 환경 변수 로드 (.env 파일이 같은 폴더에 있어야 함)
load_dotenv()

def get_tax_tip_for_category(category):
    tips = {
        "insurance": "보장성 보험료는 연 100만 원 한도로 12% 세액 공제됩니다. 맞벌이 부부의 경우, 급여가 적은 배우자 명의로 계약하는 것이 유리할 수 있습니다.",
        "medical": "총 급여액의 3%를 초과하는 금액에 대해 공제됩니다. 특히 산후조리원 비용(200만 원 한도)과 난임 시술비는 공제율이 높으니 관련 영수증을 잘 챙기세요.",
        "education": "본인 교육비는 전액 공제되며, 자녀 교육비는 1인당 한도가 있습니다. 취학 전 아동의 학원비는 공제가능하나, 초/중/고교 학원비는 공제 대상이 아닙니다.",
        "housing": "주택 마련 저축(청약 저축 등)은 연 240만 원 한도로 공제됩니다. 무주택 세대주 여부를 반드시 확인해야 합니다.",
        "pension": "연금저축 및 퇴직연금은 세액 공제율이 높습니다. 총 급여액에 따라 공제 한도와 공제율이 달라지니 최대한 활용하는 것이 좋습니다."
    }
    
    selected_tip = tips.get(category.lower(), "해당 공제 항목에 대한 일반적인 절세 팁을 찾을 수 없습니다. (카테고리: " + category + ")")
    
    return json.dumps({
        "category": category,
        "tip": selected_tip
    })

OPENWEATHER_API_KEY = "586cc15ec5c2aabe7f9cd119ed9ca9e4"
deployment_name = "gpt-4o-mini" # 사용하는 모델 배포명

def get_location_data(location):
    """OpenWeatherMap API를 통해 날씨와 타임존 오프셋 정보를 가져오는 헬퍼 함수"""
    if not OPENWEATHER_API_KEY:
        return None
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            # 404 오류 등을 모델에게 간결하게 전달
            return json.dumps({"error": f"API Error: {response.status_code}"})
    except Exception as e:
        return json.dumps({"error": f"Request failed: {e}"})

def get_current_weather(location, unit="celsius"):
    """실제 API를 호출하여 날씨 정보를 반환"""
    data = get_location_data(location)
    if data and "error" not in data:
        temp_c = data["main"]["temp"]
        weather_desc = data["weather"][0]["description"]
        final_temp = temp_c
        if unit == "fahrenheit":
            final_temp = (temp_c * 9/5) + 32

        return json.dumps({
            "location": location,
            "temperature": round(final_temp, 1),
            "unit": unit,
            "description": weather_desc
        })
    return json.dumps({"location": location, "temperature": "unknown"})

def get_current_time(location):
    """실제 API를 호출하여 날씨 정보를 반환"""
    data = get_location_data(location)
    if data and "error" not in data:
        temp_c = data["main"]["temp"]
        weather_desc = data["weather"][0]["description"]
        final_temp = temp_c
        if unit == "fahrenheit":
            final_temp = (temp_c * 9/5) + 32

        return json.dumps({
            "location": location,
            "temperature": round(final_temp, 1),
            "unit": unit,
            "description": weather_desc
        })
    return json.dumps({"location": location, "temperature": "unknown"})

tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "지역의 현재 날씨(온도, 상태)를 조회합니다. 도시 이름은 반드시 영어로 변환하여 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city name, e.g. Seoul or Tokyo."},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Temperature unit."},
                },
                "required": ["location"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "지역의 현재 현지 시간을 조회합니다. 도시 이름은 반드시 영어로 변환하여 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city name, e.g. Seoul or Tokyo."},
                },
                "required": ["location"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tax_tip_for_category",
            "description": "사용자가 질문한 연말정산 공제 항목(예: 보험료, 의료비, 교육비 등)에 대한 구체적인 절세 팁과 공제 요건을 조회합니다. 카테고리는 반드시 영어로 변환하여 사용해야 합니다.",
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

# 도구 이름과 실제 Python 함수를 매핑
available_functions = {
    "get_current_weather": get_current_weather,
    "get_current_time": get_current_time,
    "get_tax_tip_for_category": get_tax_tip_for_category
}

# 2. Azure OpenAI 클라이언트 설정
# (실제 값은 .env 파일이나 여기에 직접 입력하세요)
st.title("💰 연말정산 공제 팁 챗봇")

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OAI_KEY"),
    api_version="2024-05-01-preview",
    azure_endpoint=os.getenv("AZURE_OAI_ENDPOINT")
)

# 3. 대화기록(Session State) 초기화 - 이게 없으면 새로고침 때마다 대화가 날아갑니다!
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4. 화면에 기존 대화 내용 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

uploaded_file = st.file_uploader("연말정산 서류(PDF, PNG, JPG)를 여기에 첨부하세요.", type=["pdf", "png", "jpg", "jpeg"], key="tax_doc_uploader")

# 5. 사용자 입력 받기
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    # (1) 사용자 메시지 화면에 표시 & 저장
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # (2) AI 응답 생성 (스트리밍 방식 아님, 단순 호출 예시)
    with st.chat_message("assistant"):
        # 응답 영역 Placeholder
        placeholder = st.empty()
        # 'if prompt := st.chat_input("무엇을 도와드릴까요?"):` 블록 안
# 'with st.chat_message("assistant"):' 블록 안에 위치해야 합니다.

        # 응답 영역 Placeholder
        placeholder = st.empty()

        # Streamlit 세션 기록을 기반으로 메시지 리스트 생성 (시스템 지침 포함)
        # [수정] 시스템 메시지를 맨 앞에 추가하여 챗봇의 페르소나를 연말정산 전문가로 정의합니다.
        messages_for_completion = [{
            "role": "system",
            "content": """당신은 '연말정산 절세 코치'라는 이름의 챗봇입니다. 당신의 목표는 사용자가 합법적으로 세액 공제나 소득 공제를 최대한 많이 받을 수 있도록 구체적이고 실용적인 팁과 요건을 안내하는 것입니다.

1.  **역할:** 연말정산 항목(의료비, 보험료, 교육비, 주택자금 등)과 관련된 질문에 답변하고, 공제를 더 받을 수 있는 방법을 상세히 설명합니다.
2.  **태도:** 친절하고 전문적인 존댓말을 사용하며, 복잡한 세법 내용을 이해하기 쉽게 풀어서 설명합니다.
3.  **도구 사용:** 사용자가 특정 공제 항목에 대해 질문하면 'get_tax_tip_for_category' 도구를 호출하여 맞춤형 팁을 조회한 후, 이를 바탕으로 상세한 답변을 구성합니다.
4.  **제한:** 최종적인 세무 신고는 세무사 또는 국세청 자료를 통해 확인하도록 반드시 권고합니다.
"""
        }] + [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        response = client.chat.completions.create(
                model=deployment_name, 
                messages=messages_for_completion,
                tools=tools_definitions,
                tool_choice="auto",
            )

        response_message = response.choices[0].message
        messages_for_completion.append(response_message)

        assistant_reply = ""

            # 도구 호출이 필요한 경우
        if response_message.tool_calls:

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                # Python 함수 실행
                function_response = available_functions[function_name](**function_args)

                # 결과 메시지 추가 (이 결과가 2차 호출 시 모델에게 전달됨)
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

        # (3) AI 응답 화면에 출력 및 저장
        placeholder.markdown(assistant_reply)
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})









