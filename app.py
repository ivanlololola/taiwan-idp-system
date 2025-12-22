import streamlit as st
import google.generativeai as genai
import pdfplumber
import os
import json
from datetime import datetime, timedelta

# --- 1. 系統初始化與設定 ---
st.set_page_config(page_title="全球駕照 AI 智能 RAG 系統", layout="wide")

# 這裡建議在 Streamlit Cloud 的 Secrets 中設定 API_KEY
# 或者在側邊欄手動輸入
with st.sidebar:
    st.header("🔑 系統金鑰設定")
    api_key = st.text_input("請輸入 Gemini API Key", type="password")
    st.info("API Key 可至 Google AI Studio 免費申請")

# --- 2. 知識庫處理 (RAG 核心) ---
@st.cache_resource
def load_and_preprocess_pdfs(data_dir):
    """讀取所有 PDF 並建立文字索引，僅在啟動或清理快取時執行一次"""
    knowledge_base = {}
    if not os.path.exists(data_dir):
        return None
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.pdf')]
    for file in files:
        region = file.replace(".pdf", "")
        text_content = ""
        try:
            with pdfplumber.open(os.path.join(data_dir, file)) as pdf:
                for page in pdf.pages:
                    text_content += page.extract_text() + "\n"
            knowledge_base[region] = text_content
        except Exception as e:
            st.error(f"讀取 {file} 失敗: {e}")
    return knowledge_base

# --- 3. Gemini 串接邏輯 ---

def analyze_with_gemini(api_key, country, context):
    try:
        genai.configure(api_key=api_key)
        
        # 優先嘗試 1.5 Flash
        model_name = 'gemini-1.5-flash'
        model = genai.GenerativeModel(model_name)
        
        # 這裡建議加入一個回應測試，或直接執行
        prompt = f"請分析以下法規並回傳 JSON：{context}"
        response = model.generate_content(prompt)
        
        # 解析邏輯...
        return json.loads(response.text.replace('```json', '').replace('```', '').strip())
        
    except Exception as e:
        # 如果還是 404，嘗試加上 models/ 前綴
        if "404" in str(e):
            model = genai.GenerativeModel('models/gemini-1.5-flash')
            # 重新嘗試生成...
            
        return {"error": f"模型調用失敗，請確認套件已更新。原始錯誤：{str(e)}"}

# --- 4. 主程式介面 ---
st.title("📑 全球駕照互惠 AI 智能查詢系統 (RAG 版)")
st.caption("由 Gemini 1.5 Flash 提供動力，自動讀取監理所最新 PDF 備註")

data_folder = "data"
kb = load_and_preprocess_pdfs(data_folder)

if not kb:
    st.error(f"找不到 '{data_folder}' 資料夾或 PDF 檔案，請檢查 GitHub 目錄結構。")
    st.stop()

if api_key:
    # 搜尋區域
    col1, col2 = st.columns(2)
    with col1:
        region_choice = st.selectbox("1. 選擇州別 (PDF 來源)", list(kb.keys()))
    with col2:
        target_country = st.text_input("2. 輸入查詢國家 (例如：德國、千里達)")

    # 簽證日期輸入
    st.divider()
    c1, c2, c3 = st.columns(3)
    entry_date = c1.date_input("入境日期", datetime.now())
    idp_exp = c2.date_input("國際駕照到期日")
    legal_exp = c3.date_input("簽證/居留證截止日")

    if target_country:
        with st.spinner(f"正在從 {region_choice} PDF 中檢索並分析 {target_country}..."):
            # 檢索與該國相關的文本區塊 (RAG Retrieval)
            full_text = kb.get(region_choice, "")
            start_idx = full_text.find(target_country)
            
            if start_idx != -1:
                # 抓取關鍵字前後各 1000 字作為上下文
                context = full_text[max(0, start_idx-200) : start_idx+1200]
                
                # 呼叫 AI (RAG Generation)
                res = analyze_with_gemini(api_key, target_country, context)
                
                if "error" not in res:
                    st.success(f"✅ AI 解析完成：{target_country}")
                    
                    # 計算最終日期
                    law_days = res.get("limit_days", 365)
                    final_date = min(entry_date + timedelta(days=law_days), idp_exp, legal_exp)
                    
                    # 顯示數據指標
                    m1, m2, m3 = st.columns(3)
                    m1.metric("最終簽證截止日", str(final_date))
                    m2.metric("機車互惠資格", "✅ 有" if res['motorcycle_eligible'] else "❌ 無")
                    m3.metric("需備譯本", "是" if res['translation_required'] else "否")

                    # 風險警告
                    if not res['motorcycle_eligible']:
                        st.error(f"🚨 注意：{target_country} 的機車不具備互惠資格，不可核發。")
                    
                    st.info(f"📝 **判定依據：** {res['reason']}")
                    
                    with st.expander("🔍 查看 AI 檢索到的原始文字片段"):
                        st.code(context, language="text")
                else:
                    st.error(f"AI 解析失敗：{res['error']}")
            else:
                st.warning(f"在 {region_choice}.pdf 中找不到「{target_country}」，請確認名稱是否正確。")
else:
    st.warning("👈 請先在側邊欄輸入 Gemini API Key 才能啟動 AI 檢索。")
