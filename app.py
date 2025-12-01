import os
import json
import requests
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AzureOpenAI(
  azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT"),
  api_key= os.getenv("AZURE_OAI_KEY"),
  api_version="2024-05-01-preview"
)
# 로컬 파일을 임시 벡터 스토리지로 옮기는 거(실제 벡터 저장소에 하는것과 도우미 첨부파일 올리는 것과 다름 -> 도우미 첨부파일 올리는 건 단발성)->지금은 단발성으로 올리는 임시임

#1. 로컬에 있는 파일을 읽어와서 임시 벡터저장소로 보내는 코드
file_path = r"C:\Users\EL94\Downloads\이예진의 AI School 파일\25.11.25 (클라우드openAI)\openai\09 AzureOpenAI 2 챗봇-매개변수_v11.pdf"

message_file = client.files.create(
    file=open(file_path, 'rb'),
    purpose='assistants'
)

assistant = client.beta.assistants.create(
  model="gpt-4o-mini", # replace with model deployment name.
  instructions="",
  tools=[{"type":"file_search"}],
  temperature=1,
  top_p=1
)

# Create a thread
thread = client.beta.threads.create()

# Add a user question to the thread
message = client.beta.threads.messages.create(
  thread_id=thread.id,
  role="user",
  content="파일 내용 요약해줘", # Replace this with your prompt
  #2. 파일 첨부에 대한 설정 추가
  attachments=[
    {
        "file_id" :message_file.id,
        "tools": [{"type":"file_search"}]
    }
  ]
)



# Run the thread
run = client.beta.threads.runs.create(
  thread_id=thread.id,
  assistant_id=assistant.id
)

# Looping until the run completes or fails
while run.status in ['queued', 'in_progress', 'cancelling']:
  time.sleep(1)
  run = client.beta.threads.runs.retrieve(
    thread_id=thread.id,
    run_id=run.id
  )

if run.status == 'completed':
  messages = client.beta.threads.messages.list(
    thread_id=thread.id
  )
  print(messages.data[0].content[0].text.value)
elif run.status == 'requires_action':
  # the assistant requires calling some functions
  # and submit the tool outputs back to the run
  pass
else:
  print(run.status)
