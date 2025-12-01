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



OPENWEATHER_API_KEY = "8538da5f00be6a0906782d7ea86c56aa"
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
    """실제 API의 Timezone offset을 이용하여 현지 시간 계산"""
    data = get_location_data(location)
    if data and "error" not in data:
        timezone_offset = data["timezone"]
        utc_now = datetime.now(timezone.utc)
        local_time = utc_now + timedelta(seconds=timezone_offset)

        return json.dumps({
            "location": location,
            "current_time": local_time.strftime("%Y-%m-%d %I:%M %p")
        })
    return json.dumps({"location": location, "current_time": "unknown"})

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
    }
]

# 도구 이름과 실제 Python 함수를 매핑
available_functions = {
    "get_current_weather": get_current_weather,
    "get_current_time": get_current_time
}

# 2. Azure OpenAI 클라이언트 설정
# (실제 값은 .env 파일이나 여기에 직접 입력하세요)
st.title("🤖 실시간 날씨 & 시간 챗봇")

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

# 5. 사용자 입력 받기
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    # (1) 사용자 메시지 화면에 표시 & 저장
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # (2) AI 응답 생성 (스트리밍 방식 아님, 단순 호출 예시)
    with st.chat_message("assistant"):
        # 응답 영역 Placeholder
        placeholder = st.empty()

        # Streamlit 세션 기록을 기반으로 메시지 리스트 생성 (시스템 지침 포함)
        messages_for_completion = [
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
