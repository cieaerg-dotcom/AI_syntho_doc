import streamlit as st
import google.generativeai as genai
import os
import time
from docx import Document
from pypdf import PdfReader
from PIL import Image
import tempfile # 【新增】用於處理安全且不重複的暫存檔案

##### 2. 側邊欄：設定與金鑰輸入 [1]
with st.sidebar:
    st.header("設定")
    
    # 讓使用者自備金鑰
    api_key = st.text_input("輸入金鑰", type="password")
    
    # 新增：取得 API 金鑰的連結按鈕
    st.link_button("🔑 取得 Google API 金鑰", "https://aistudio.google.com/app/apikey")
    
    # 模型設定
    model_choice = st.selectbox(
        "選擇模型 (Gemini 3 系列)",
        [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-3-flash-lite-preview",
            "gemini-3-flash-preview",
        ]
    )
    use_thinking = st.checkbox("啟用思考模式")

# 檢查金鑰是否存在
if not api_key:
    st.warning("請輸入金鑰以啟用 AI 功能")
    st.stop()

# 若已輸入金鑰，則進行設定
genai.configure(api_key=api_key)

# --- 3. 文件提取函數 ---
def extract_text(file):
    fname = file.name.lower()
    try:
        if fname.endswith(('.txt', '.md')):
            return file.read().decode("utf-8")
        elif fname.endswith('.docx'):
            doc = Document(file)
            return "\n".join([para.text for para in doc.paragraphs])
        elif fname.endswith('.pdf'):
            reader = PdfReader(file)
            return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception as e:
        return f"\n[讀取檔案 {file.name} 失敗: {e}]\n"
    return ""

# --- 4. 檔案上傳區 ---
uploaded_files = st.file_uploader(
    "上傳資料 (錄音, 文件, 影像)",
    type=['mp3', 'wav', 'm4a', 'txt', 'md', 'docx', 'pdf', 'jpg', 'jpeg', 'png'],
    accept_multiple_files=True
)

# 處理上傳檔案並存入 Context
if uploaded_files:
    if st.button("🔄 點擊以解析/更新上傳檔案內容"):
        with st.status("正在讀取檔案內容至 AI 記憶中...", expanded=True):
            st.session_state.file_context = []
            st.session_state.text_context = ""
            
            for file in uploaded_files:
                fname = file.name.lower()
                if fname.endswith(('.txt', '.md', '.docx', '.pdf')):
                    st.session_state.text_context += f"\n\n[來源: {fname}]\n{extract_text(file)}"
                elif fname.endswith(('.jpg', '.jpeg', '.png')):
                    st.session_state.file_context.append(Image.open(file))
                elif fname.endswith(('.mp3', '.wav', '.m4a')):
                    # 【修改2：修復音訊暫存檔覆寫與殘留問題】
                    # 使用 tempfile 生成唯一的暫存檔案，處理完畢後刪除
                    file_extension = os.path.splitext(fname)[1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                        tmp_file.write(file.getbuffer())
                        tmp_file_path = tmp_file.name
                    
                    try:
                        audio_file = genai.upload_file(path=tmp_file_path)
                        while audio_file.state.name == "PROCESSING":
                            time.sleep(1)
                            audio_file = genai.get_file(audio_file.name)
                        st.session_state.file_context.append(audio_file)
                    finally:
                        # 確保上傳到 API 後，不管成功失敗都會刪除本地暫存檔釋放空間
                        if os.path.exists(tmp_file_path):
                            os.remove(tmp_file_path)
                            
            st.success("檔案解析完成！現在可以開始對話或生成摘要。")

### --- 5. 對話介面區 ---
st.divider()
st.subheader("💬 與你的檔案對話")

# 加入以下這兩行來初始化，確保變數存在：
if "messages" not in st.session_state:
    st.session_state.messages = []

### 顯示歷史訊息
for message in st.session_state.messages: # [1]
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 接收使用者指令
if prompt := st.chat_input("想針對這些檔案問什麼？(例如：幫我總結、找出特定日期...)"):
    # 顯示使用者訊息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 【修改3 & 4：補上 AI 生成邏輯，並套用側邊欄設定】
    with st.chat_message("assistant"):
        with st.spinner("AI 正在思考中..."):
            try:
                # 應用側邊欄的「選擇模型」
                model = genai.GenerativeModel(model_name=model_choice)
                
                # 準備系統提示與文件上下文
                system_instruction = "你是一個專業且樂於助人的 AI 助手，請根據使用者提供的所有檔案內容來詳細回答問題。"
                
                # 應用側邊欄的「深度思考模式」
                if use_thinking:
                    system_instruction += "請開啟深度思考，確保回答邏輯清晰、結構完整且具備深度洞察力。"
                
                if st.session_state.text_context:
                    system_instruction += f"\n\n以下為參考的文字檔內容：\n{st.session_state.text_context}"
                
                # 將系統提示、影像/音訊檔案物件、以及使用者的提問打包為內容列表
                contents = [system_instruction] + st.session_state.file_context + [prompt]
                
                # 呼叫 Gemini API
                response = model.generate_content(contents)
                
                # 顯示並儲存 AI 回覆
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
            except Exception as e:
                st.error(f"與 AI 溝通時發生錯誤: {e}")
