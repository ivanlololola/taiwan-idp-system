import streamlit as st
import pdfplumber
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 核心解析引擎：欄位自動偵測與關鍵字掃描 ---
@st.cache_data
def load_all_pdfs(data_folder):
    all_data = []
    files = [f for f in os.listdir(data_folder) if f.endswith('.pdf')]
    
    for file in files:
        path = os.path.join(data_folder, file)
        region_name = file.replace(".pdf", "")
        
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2: continue
                    
                    # --- 欄位自動偵測功能 ---
                    headers = [str(h).replace("\n", "") for h in table[0]]
                    col_map = {
                        "country": -1, "car": -1, "moto": -1, "note": -1
                    }
                    
                    for i, h in enumerate(headers):
                        if "國家" in h: col_map["country"] = i
                        elif "汽" in h: col_map["car"] = i
                        elif "機" in h or "摩" in h: col_map["moto"] = i
                        elif "備註" in h or "說明" in h: col_map["note"] = i
                    
                    # 開始解析每一行
                    for row in table[1:]:
                        if col_map["country"] != -1 and row[col_map["country"]]:
                            country = row[col_map["country"]].replace("\n", "")
                            note = row[col_map["note"]].replace("\n", " ") if col_map["note"] != -1 else ""
                            
                            # --- 關鍵字掃描器 ---
                            # 1. 掃描簽證天數 (從備註中提取數字)
                            scan_days = 365 # 預設一年
                            if "90" in note: scan_days = 90
                            elif "180" in note: scan_days = 180
                            
                            # 2. 掃描機車互惠狀態
                            # 如果機車欄位寫無，或是備註提到不具機車互惠
                            moto_raw = str(row[col_map["moto"]]) if col_map["moto"] != -1 else ""
                            scan_moto = True
                            if "無" in moto_raw or "不" in moto_raw or "不" in note and "機車" in note:
                                scan_moto = False
                            
                            all_data.append({
                                "區域": region_name,
                                "國家": country,
                                "汽車": "可" if "可" in str(row[col_map["car"]]) else "查閱備註",
                                "機車": "可" if scan_moto else "無互惠",
                                "自動判定天數": scan_days,
                                "原始備註": note
                            })
    return pd.DataFrame(all_data)

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
