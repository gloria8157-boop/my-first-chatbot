import streamlit as st
import os
import json
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. 환경 변수 로드 (.env 파일이 같은 폴더에 있어야 함)
load_dotenv() 

# -------------------------------------------------------------
# 0. UI 설정 및 CSS 주입 (디자인 및 버튼 스타일)
# -------------------------------------------------------------
st.set_page_config

st.markdown("""
<style>
/* 폰트 및 앱 배경색 설정 */
.stApp {
    background-color: #f7f9fd;
    color: #1f1f1f;
    font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif; 
}

/* 제목 (h1) 스타일 */
h1 {
    color: #0078d4;
    border-bottom: 3px solid #e0e0e0;
    padding-bottom: 10px;
    margin-bottom: 30px; 
}

/* 챗봇 대화 영역 (AI 메시지) */
.st-emotion-cache-1c7c943 {
    background-color: #e6f7ff;
    border-radius: 10px;
    padding: 10px;
}
/* 사용자 메시지 */
.st-emotion-cache-1r65hfr {
    background-color: #ffffff;
    border-radius: 10px;
    padding: 10px;
}

/* 퀵팁 버튼 커스터마이징 */
.quick-tip-container {
    padding: 10px 0 20px 0;
    border-bottom: 1px dashed #ccc;
    margin-bottom: 20px;
}
.stButton>button {
    background-color: #f0f0f5; 
    color: #333333;
    border: 1px solid #dcdcdc;
    border-radius: 20px;
    padding: 5px 15px;
    margin: 5px;
    font-weight: 500;
    transition: background-color 0.2s, transform 0.1s;
}
.stButton>button:hover {
    background-color: #e2e8f0;
    transform: translateY(-1px);
}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 설정 및 도구 함수 정의
# -------------------------------------------------------------
deployment_name = "gpt-4o-mini" # 사용하는 모델 배포명

def get_tax_tip_for_category(category):
    """주요 연말정산 공제 항목에 대한 절세 팁을 제공하는 헬퍼 함수"""
    tips = {
        "insurance": "보장성 보험료는 연 100만 원 한도로 12% 세액 공제됩니다. 맞벌이 부부의 경우, 급여가 적은 배우자 명의로 계약하는 것이 유리할 수 있습니다.",
        "medical": "총 급여액의 3%를 초과하는 금액에 대해 공제됩니다. 특히 산후조리원 비용(200만 원 한도)과 난임 시술비는 공제율이 높으니 관련 영수증을 잘 챙기세요.",
        "education": "본인 교육비는 전액 공제되며, 자녀 교육비는 1인당 한도가 있습니다. 취학 전 아동의 학원비는 공제가능하나, 초/중/고교 학원비는 공제 대상이 아닙니다.",
        "housing": "주택 마련 저축(청약 저축 등)은 연 240만 원 한도로 공제됩니다. 무주택 세대주 여부를 반드시 확인해야 합니다.",
        "pension": "연금저축 및 퇴직연금은 세액 공제율이 높습니다. 총 급여액에 따라 공제 한도와 공제율이 달라지니 최대한 활용하는 것이 좋습니다.",
        "donation": "기부금은 소득금액의 일정 비율을 한도로 공제됩니다. 특히 고액 기부금(1천만 원 초과분)은 공제율이 높으니, 관련 서류를 잘 보관해야 합니다."
    }
    selected_tip = tips.get(category.lower(), "해당 공제 항목에 대한 일반적인 절세 팁을 찾을 수 없습니다. (카테고리: " + category + ")")
    return json.dumps({"category": category, "tip": selected_tip})


def check_eligibility(deduction_type, annual_income_krw):
    """
    특정 공제 항목에 대한 소득 기준 충족 여부를 판단하는 함수.
    이 함수는 모델에게 공제 가능/불가능에 대한 판단 근거를 제공합니다.
    (실제 세법은 복잡하나, 단순화된 기준을 사용합니다.)
    """
    income = float(annual_income_krw) / 10000000 # 억 단위로 변환
    
    if deduction_type.lower() == "주택자금" or deduction_type.lower() == "housing":
        # 주택자금 관련 공제는 보통 총 급여액 7천만 원 (7억 원) 이하를 기준으로 함
        if income <= 7.0:
            return json.dumps({"status": "가능", "reason": "총 급여액 기준 7천만 원 이하로 주택자금 공제의 기본 소득 요건을 충족합니다. (단, 무주택 세대주 요건 등 추가 확인 필요)"})
        else:
            return json.dumps({"status": "불가", "reason": "총 급여액이 7천만 원을 초과하여 일부 주택자금 관련 공제(예: 주택청약종합저축)는 제한될 수 있습니다."})
    
    elif deduction_type.lower() == "신용카드" or deduction_type.lower() == "creditcard":
        # 신용카드 공제는 소득 제한은 없으나, 총 급여액의 25% 초과분에 대해서만 공제됩니다.
        return json.dumps({"status": "정보필요", "reason": "신용카드 공제는 소득 제한이 아닌, 총 급여액의 25% 초과 지출액에 대해 적용됩니다. 초과 지출액 정보를 알려주세요."})

    else:
        return json.dumps({"status": "알 수 없음", "reason": "해당 공제 항목에 대한 명확한 소득 기준 정보를 찾을 수 없습니다. 일반적인 공제 팁을 확인해 보세요."})


# 모델이 사용할 수 있는 도구 정의
tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "get_tax_tip_for_category",
            "description": "사용자가 질문한 연말정산 공제 항목(예: 보험료, 의료비, 교육비 등)에 대한 구체적인 절세 팁과 공제 요건을 조회합니다. 카테고리는 반드시 영어로 변환하여 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "The tax deduction category (e.g., 'insurance', 'medical', 'education', 'housing', 'pension', 'donation')."},
                },
                "required": ["category"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_eligibility",
            "description": "특정 공제 항목(예: 주택자금, 신용카드)의 기본 소득 기준 충족 여부를 판단합니다. 공제 유형(한글 또는 영어)과 연간 소득(KRW)을 입력받아 결과를 제공합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deduction_type": {"type": "string", "description": "The type of deduction (e.g., '주택자금', '신용카드', 'housing')."},
                    "annual_income_krw": {"type": "number", "description": "User's annual income in Korean Won (KRW)."},
                },
                "required": ["deduction_type", "annual_income_krw"],
            },
        }
    }
]

# 실제 Python 함수와 도구 이름을 매핑
available_functions = {
    "get_tax_tip_for_category": get_tax_tip_for_category,
    "check_eligibility": check_eligibility, # 새 함수 추가
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

# 대화기록(Session State) 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
    # 챗봇 시작 시 초기 메시지 추가 (UX 개선)
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "안녕하세요, 저는 **연말정산 절세 코치**입니다. 궁금한 공제 항목을 질문해 주시면, 소득공제 및 세액공제 팁을 자세히 안내해 드리겠습니다! 하단의 팁 버튼을 이용하거나, '제 연봉이 5000만원인데 주택자금 공제가 가능한가요?'처럼 구체적으로 질문해 보세요."
    })


# 화면에 기존 대화 내용 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 시스템 프롬프트 정의
SYSTEM_PROMPT = """당신은 '연말정산 절세 코치'입니다. 당신의 목표는 사용자가 합법적으로 세액 공제나 소득 공제를 최대한 많이 받을 수 있도록 구체적이고 실용적인 팁과 요건을 안내하는 것입니다.

1.  **역할:** 연말정산 항목(의료비, 보험료, 주택자금 등)과 관련된 질문에 답변하고, 공제를 더 받을 수 있는 방법을 상세히 설명합니다.
2.  **도구 사용:** 질문에 명확한 공제 항목이나 소득 정보가 포함된 경우(예: '주택자금 공제 팁 알려줘', '연봉이 6천만원인데 주택자금 공제가 되나요?'), 적절한 도구(get_tax_tip_for_category 또는 check_eligibility)를 호출하여 답변을 보강합니다.
3.  **태도:** 친절하고 전문적인 존댓말을 사용하며, 복잡한 세법 내용을 이해하기 쉽게 풀어서 설명합니다.
4.  **제한:** 최종적인 세무 신고는 세무사 또는 국세청 자료를 통해 확인하도록 반드시 권고합니다."""


# -------------------------------------------------------------
# 4. 퀵팁 버튼 UI 생성 및 처리 로직
# -------------------------------------------------------------

QUICK_TIPS = {
    "의료비 공제 팁": "의료비 공제를 최대한 많이 받는 방법이 궁금해",
    "소득 기준 확인": "제 연봉이 7500만원인데 주택자금 공제가 가능한가요?",
    "연금저축 팁": "연금저축 공제 한도와 팁을 알려줘",
    "신용카드 공제 기준": "신용카드 공제 소득 기준이 궁금합니다."
}

st.markdown('<div class="quick-tip-container">', unsafe_allow_html=True)
st.markdown("##### 💡 자주 찾는 공제 팁")

cols = st.columns(len(QUICK_TIPS))

for i, (label, query) in enumerate(QUICK_TIPS.items()):
    with cols[i]:
        if st.button(label, key=f"tip_button_{i}"):
            st.session_state.button_prompt = query
            st.rerun() 

st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------------------
# 5. 사용자 입력 처리 및 API 호출 (로딩 스피너 적용)
# -------------------------------------------------------------

chat_input_val = st.chat_input("무엇을 도와드릴까요? (예: 의료비 공제 팁 알려줘)")

final_prompt = None

if "button_prompt" in st.session_state and st.session_state.button_prompt:
    final_prompt = st.session_state.button_prompt
    st.session_state.button_prompt = ""
elif chat_input_val:
    final_prompt = chat_input_val

# 3. 최종 prompt가 있을 때만 API 호출 로직 실행
if final_prompt:
    prompt = final_prompt
    
    # 1. 사용자 메시지 화면 표시 및 세션 저장
    with st.chat_message("user"):
        st.markdown(prompt)
        
    st.session_state.messages.append({"role": "user", "content": prompt})


    # 2. API 요청 메시지 리스트 구성
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        # --- 로딩 스피너 추가 ---
        with st.spinner("전문가 AI가 답변을 분석하고 있습니다..."):
            
            messages_for_completion = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages_for_completion.extend(st.session_state.messages)
            
            # -------------------------------------------------------------------
            # 3. API 호출 및 도구 사용 로직
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
                
                messages_for_completion.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    # 실제 Python 함수 실행
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


