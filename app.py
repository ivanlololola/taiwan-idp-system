import streamlit as st
import google.generativeai as genai
import pdfplumber
import os
import json
import re
from datetime import datetime, timedelta

# --- 1. 初始化與模型路徑修正 ---
st.set_page_config(page_title="監理站 AI RAG 系統", layout="wide")

def analyze_with_gemini(api_key, country, context):
    try:
        genai.configure(api_key=api_key)
        # 修正點：使用完整的模型名稱路徑，避免 404 錯誤
        model = genai.GenerativeModel('models/gemini-1.5-flash')
        
        prompt = f"""
        你現在是台灣監理站法規專家。請根據法規內容，分析『{country}』規定。
        【法規內容】: {context}
        【要求】: 僅輸出 JSON 格式，欄位：can_drive(bool), limit_days(int), motorcycle_eligible(bool), reason(str)。
        """
        
        response = model.generate_content(prompt)
        # 強大解析：過濾掉 AI 可能回傳的 Markdown 標籤
        clean_text = re.sub(r'```json|```', '', response.text).strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"error": str(e)}

# --- 2. 核心 RAG 讀取邏輯 ---
@st.cache_resource
def load_data(folder):
    all_text = ""
    if not os.path.exists(folder): return None
    for f in os.listdir(folder):
        if f.endswith(".pdf"):
            with pdfplumber.open(os.path.join(folder, f)) as pdf:
                for page in pdf.pages:
                    all_text += (page.extract_text() or "") + "\n"
    return all_text

# --- 3. 介面與檢索 ---
st.title("🛡️ 監理站國際駕照 AI 審核助手")
api_key = st.sidebar.text_input("Gemini API Key", type="password")
full_docs = load_data("data")

if api_key and full_docs:
    query = st.text_input("輸入查詢國家")
    if query:
        # RAG 檢索：尋找關鍵字
        # 這裡改用 re.IGNORECASE 增加容錯
        match = re.search(rf".{{0,500}}{query}.{{0,1500}}", full_docs, re.DOTALL | re.IGNORECASE)
        
        if match:
            context_snippet = match.group(0)
            with st.spinner("AI 正在閱讀條文..."):
                res = analyze_with_gemini(api_key, query, context_snippet)
                
                if "error" not in res:
                    # 顯示結果指標
                    c1, c2, c3 = st.columns(3)
                    c1.metric("建議核發天數", f"{res['limit_days']} 天")
                    c2.metric("機車互惠", "✅ 有" if res['motorcycle_eligible'] else "❌ 無")
                    c3.success("法規檢索成功")
                    
                    st.warning(f"💡 **AI 專家判定依據：** {res['reason']}")
                    with st.expander("查看檢索到的法規片段"):
                        st.text(context_snippet)
                else:
                    st.error(f"API 呼叫失敗：{res['error']}")
        else:
            st.error("❌ 知識庫中找不到該國家的相關法規。")
else:
    st.info("請確保 'data' 資料夾內有 PDF 檔案，並在側邊欄輸入 API Key。")
