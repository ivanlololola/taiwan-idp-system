import streamlit as st
import json
from datetime import datetime, timedelta

# --- 設定 ---
st.set_page_config(page_title="國際駕照簽證天數查詢", layout="wide", page_icon="📝")

# 讀取 JSON
@st.cache_data
def load_data():
    try:
        with open('countries.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("找不到 countries.json 檔案，請確保檔案已上傳。")
        return {}

data = load_data()

# --- 側邊欄設計 ---
with st.sidebar:
    st.header("🛂 身分與證件")
    id_mode = st.radio("入境證件類型", ["護照 (Passport)", "居留證 (ARC)"])
    
    st.divider()
    
    st.header("🌍 來源地區")
    region = st.selectbox("選擇區域", list(data.keys()))
    country_name = st.selectbox("選擇國家/地區", list(data[region].keys()))
    country_info = data[region][country_name]

    st.divider()
    
    st.header("📅 關鍵效期")
    entry_date = st.date_input("入境台灣日期", datetime.now())
    idp_exp = st.date_input("國際駕照(IDP)有效截止日")
    
    label = "護照簽證截止日" if id_mode == "護照 (Passport)" else "居留證(ARC)截止日"
    legal_exp = st.date_input(label)

# --- 主畫面顯示 ---
st.title("國際駕照在台可駕車天數查詢")
st.write(f"當前查詢對象：**{country_name}** ({region})")

# 選擇駕駛種類
drive_type = st.radio("申請駕駛種類", ["汽車 (Car)", "機車 (Motorcycle)"], horizontal=True)

# 邏輯判斷
eligible = country_info["car"] if drive_type == "汽車 (Car)" else country_info["moto"]

if not eligible:
    st.error(f"❌ 警告：{country_name} 的【{drive_type}】在台不具備互惠資格。")
else:
    # 計算日期
    # 1. 法理上限 (入境日 + 規定天數 - 1)
    law_limit = entry_date + timedelta(days=country_info["limit_days"] - 1)
    
    # 2. 孰短原則 (法規、證件、簽證)
    final_date = min(law_limit, idp_exp, legal_exp)
    
    # 3. 剩餘天數
    today = datetime.now().date()
    days_left = (final_date - today).days

    # 顯示結果卡片
    st.markdown("---")
    res_col1, res_col2 = st.columns(2)
    
    with res_col1:
        st.metric("最晚可駕車日期", str(final_date))
        if days_left <= 0:
            st.error("🚨 您的駕駛資格已過期！")
        elif days_left <= 30:
            st.warning(f"注意：您的駕駛資格僅剩 {days_left} 天。")
        else:
            st.success(f"您的駕駛資格尚有 {days_left} 天。")

    with res_col2:
        st.info(f"📌 **法規限制**：該國最長簽證天數為 {country_info['limit_days']} 天。")
        if country_info["note"]:
            st.info(f"💡 **特別註記**：{country_info['note']}")

    # 30天簽證提醒
    deadline_30 = entry_date + timedelta(days=30)
    st.divider()
    st.subheader("💡 重要法律提醒")
    if today <= deadline_30:
        st.warning(f"您目前在入境 30 天內，可直接駕駛。若預計駕駛超過 **{deadline_30}**，請務必在此日期前持件至監理站辦理簽證登記。")
    else:
        st.write(f"請確認您是否已在 **{deadline_30}** 前於監理站完成國際駕照登記，否則即便在效期內亦視為無效。")


