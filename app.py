import streamlit as st
import os
import json
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. 환경 변수 로드 (.env 파일이 같은 폴더에 있어야 함)
load_dotenv() 

# -------------------------------------------------------------
# 0. UI 설정 및 CSS 주입 (디자인 코드)
# -------------------------------------------------------------
st.set_page_config(layout="wide") 

st.markdown("""
<style>
/* 폰트 및 앱 배경색 설정 */
.stApp {
    background-color: #f7f9fd; /* 연한 아이보리/하늘색 배경 */
    color: #1f1f1f;
    font-family: 'Malgun Gothic', 'Nanum Gothic', sans-serif; 
}

/* 제목 (h1) 스타일 */
h1 {
    color: #0078d4; /* 강조 파란색 */
    border-bottom: 3px solid #e0e0e0;
    padding-bottom: 10px;
    margin-bottom: 30px; /* 제목 아래 여백 추가 */
}

/* 사용자 입력창 스타일 (선택적) */
.st-emotion-cache-nahz7x {
    padding-top: 10px;
}

/* 챗봇 대화 영역 (AI 메시지) */
.st-emotion-cache-1c7c943 {
    background-color: #e6f7ff; /* 연한 파란색 배경 */
    border-radius: 10px;
    padding: 10px;
}
/* 사용자 메시지 */
.st-emotion-cache-1r65hfr {
    background-color: #ffffff; /* 흰색 배경 */
    border-radius: 10px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 1. 설정 및 도구 함수 정의
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


# 모델이 사용할 수 있는 도구 정의
tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "get_tax_tip_for_category",
            "description": "
