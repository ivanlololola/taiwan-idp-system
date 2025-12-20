import streamlit as st
import json
from datetime import datetime, timedelta

# --- 1. 讀取資料庫 ---
def load_data():
    with open('countries.json', 'r', encoding='utf-8') as f:
        return json.load(f)

data = load_data()

# --- 2. 頁面設定 ---
st.set_page_config(page_title="國際駕照簽證天數查詢", layout="wide")
st.title("🚗 國際駕照在台駕駛簽證天數查詢系統")

# --- 3. 側邊欄輸入 ---
with st.sidebar:
    st.header("📌 身份與國籍")
    
    # 新增身份欄位
    id_mode = st.radio("入境證件類型", ["護照 (Passport)", "居留證 (ARC)"])
    
    # 區域與國家連動
    region = st.selectbox("選擇區域", list(data.keys()))
    country_name = st.selectbox("選擇國家/地區", list(data[region].keys()))
    country_info = data[region][country_name]
    
    st.divider()
    
    st.header("📅 日期資訊")
    entry_date = st.date_input("入境日期", datetime.now())
    idp_exp = st.date_input("國際駕照(IDP)到期日")
    
    # 根據身份動態顯示欄位
    if id_mode == "護照 (Passport)":
        visa_label = "護照簽證停留截止日"
    else:
        visa_label = "居留證(ARC)有效截止日"
    visa_exp = st.date_input(visa_label)

# --- 4. 主畫面邏輯 ---
st.subheader(f"當前選擇：{country_name}")

col1, col2 = st.columns(2)

with col1:
    drive_type = st.radio("預計駕駛種類", ["汽車 (Car)", "機車 (Motorcycle)"])

# 檢查互惠資格
is_eligible = True
if drive_type == "汽車 (Car)" and not country_info["car"]:
    is_eligible = False
elif drive_type == "機車 (Motorcycle)" and not country_info["moto"]:
    is_eligible = False

if not is_eligible:
    st.error(f"⚠️ 該國家/地區之【{drive_type}】在台灣目前不具備互惠資格，無法直接使用國際駕照。")
else:
    # 核心計算邏輯
    # 1. 法律最長天數 (從入境隔天算起，通常為一年)
    law_limit_date = entry_date + timedelta(days=country_info["limit_days"])
    
    # 2. 孰短原則 (法規、IDP效期、簽證效期)
    final_date = min(law_limit_date, idp_exp, visa_exp)
    
    # 3. 顯示結果
    today = datetime.now().date()
    days_left = (final_date - today).days
    
    st.success("### ✅ 查詢成功")
    
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("最終合法駕駛日", str(final_date))
    res_col2.metric("剩餘天數", f"{max(0, days_left)} 天")
    res_col3.metric("法規上限日期", str(law_limit_date))

    # 4. 提醒事項
    st.info(f"📌 **備註**：{country_info['note'] if country_info['note'] else '無特殊備註'}")
    
    # 30天規則提醒
    deadline_30 = entry_date + timedelta(days=30)
    if today <= deadline_30:
        st.warning(f"💡 **重要提示**：您目前在入境30天內，可直接駕駛。若要駕駛至 {final_date}，請務必於 {deadline_30} 前至監理站辦理簽證登記。")
    else:
        st.write("🔔 請確認您是否已於入境 30 天內完成監理站簽證登記，否則視為無效駕駛。")

# --- 5. 說明頁尾 ---
st.divider()
st.caption("資料來源：交通部公路局主要國家駕照互惠情形一覽表。")

