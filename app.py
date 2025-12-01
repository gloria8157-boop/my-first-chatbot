import streamlit as st
import os
import json
import requests
from openai import AzureOpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone 
import warnings
import base64 # 파일 처리(인코딩)를 위해 추가

# 1. 환경 변수 로드 (.env 파일이 같은 폴더에 있어야 함)
# .env 파일에 AZURE_OAI_KEY, AZURE_OAI_ENDPOINT 설정 필수
load_dotenv() 

# -------------------------------------------------------------
# 설정 값
# -------------------------------------------------------------
deployment_name = "gpt-4o-mini" # 사용하는 모델 배포명 (멀티모달 지원 모델)

# -------------------------------------------------------------
# 2. 연말정산 도구 함수 및 정의
# -------------------------------------------------------------

def get_tax_tip_for_category(category):
    """
    주요 연말정산 공제 항목에 대한 절세 팁을 제공하는 헬퍼 함수입니다.
    이 함수의 출력은 LLM이 답변을 구성하는 데 사용됩니다.
    """
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


tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "get_tax_tip_for_category",
            "description": "사용자가 질문한 연말정산 공제 항목(예: 보험료, 의료비,
