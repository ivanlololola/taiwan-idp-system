import streamlit as st
import pdfplumber
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 偵錯區：在網頁上直接看檔案在哪裡 ---
st.sidebar.header("🛠 系統偵錯資訊")
current_dir = os.path.dirname(os.path.abspath(__file__))
# 嘗試自動偵測 data 資料夾（不論大小寫）
target_folder = "data"
data_path = os.path.join(current_dir, target_folder)

if not os.path.exists(data_path):
    # 如果小寫找不到，試試看首字母大寫
    if os.path.exists(os.path.join(current_dir, "Data")):
        data_path = os.path.join(current_dir, "Data")
        st.sidebar.success("找到資料夾：Data")
    else:
        st.sidebar.error(f"找不到資料夾！路徑應為: {data_path}")
        # 列出目前目錄所有東西，幫你對照
        st.sidebar.write("目前根目錄內容：", os.listdir(current_dir))
else:
    st.sidebar.success(f"成功定位資料夾：{target_folder}")

# --- 2. 核心解析引擎 (修改後的自動掃描) ---
@st.cache_data
def load_all_pdfs(path):
    all_data = []
    if not os.path.exists(path):
        return pd.DataFrame()
        
    files = [f for f in os.listdir(path) if f.endswith('.pdf')]
    st.sidebar.write(f"偵測到 PDF 檔案：{files}")
    
    for file in files:
        full_path = os.path.join(path, file)
        try:
            with pdfplumber.open(full_path) as pdf:
                # ... (後續解析邏輯維持不變) ...
                # 確保這裡的解析邏輯能正確執行
                for page in pdf.pages:
                    table = page.extract_table()
                    if table:
                        # 這裡放我們之前的解析代碼
                        pass 
        except Exception as e:
            st.sidebar.error(f"讀取 {file} 出錯: {e}")
            
    return pd.DataFrame(all_data) # 這裡回傳你解析後的結果

# --- 2. 介面設定 ---
st.set_page_config(page_title="國際駕照法規查驗系統", layout="wide")
st.title("📑 全球國際駕照互惠法規查詢系統")
st.caption("系統自動解析監理所 PDF 檔案：北美、澳洲、歐洲、非洲、中南美、亞洲")

# 載入數據
data_dir = "data" # PDF 存放資料夾
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    st.error(f"請在專案中建立 '{data_dir}' 資料夾並上傳 PDF 檔案。")
    st.stop()

df = load_all_pdfs(data_dir)

if df.empty:
    st.warning("目前沒有可用的數據，請確認 PDF 檔案是否正確放置於 data 資料夾。")
else:
    # --- 3. 側邊欄查詢 ---
    with st.sidebar:
        st.header("🔍 檢索與輸入")
        selected_region = st.selectbox("1. 選擇州別", df["區域"].unique())
        region_df = df[df["區域"] == selected_region]
        
        selected_country = st.selectbox("2. 選擇國家/地區", region_df["國家"].unique())
        target = region_df[region_df["國家"] == selected_country].iloc[0]
        
        st.divider()
        id_type = st.radio("3. 入境身分", ["護照 (Passport)", "居留證 (ARC)"])
        entry_date = st.date_input("4. 入境日期", datetime.now())
        idp_exp = st.date_input("5. 國際駕照到期日")
        legal_exp = st.date_input("6. 簽證/居留證截止日")

    # --- 4. 主畫面邏輯與掃描結果 ---
    st.header(f"查詢結果：{selected_country}")
    
    drive_mode = st.radio("申請駕駛種類", ["汽車", "機車"], horizontal=True)
    
    # 關鍵字掃描器警示
    if drive_mode == "機車" and target["機車"] == "無互惠":
        st.error(f"🚨 系統掃描提示：該國【機車】目前在台不具備互惠資格，無法核發簽證。")
    
    # 計算簽證天數
    law_days = target["自動判定天數"]
    # 孰短原則計算
    final_date = min(entry_date + timedelta(days=law_days), idp_exp, legal_exp)
    days_remaining = (final_date - datetime.now().date()).days

    # 結果圖卡
    c1, c2, c3 = st.columns(3)
    c1.metric("最終可核發日期", str(final_date))
    c2.metric("法規限制天數", f"{law_days} 天")
    c3.metric("距離到期天數", f"{max(0, days_remaining)} 天")

    # 備註呈現與關鍵字標記
    st.subheader("📝 原始法規備註 (自動校驗)")
    note = target["原始備註"]
    
    # 簡單的高亮邏輯
    highlight_note = note.replace("機車", "**機車**").replace("不具", "**不具**").replace("90", "**90**")
    st.info(highlight_note)

    # 30天簽證提醒
    deadline_30 = entry_date + timedelta(days=30)
    st.divider()
    if datetime.now().date() <= deadline_30:
        st.warning(f"💡 **簽證提醒**：您目前在入境 30 天內。若要駕駛至 {final_date}，請務必於 {deadline_30} 前至監理站辦理簽證登記。")
