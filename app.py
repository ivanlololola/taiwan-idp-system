# 根據交通部公路局 2024-2025 最新互惠表整理
# 註：'car' 代表汽車，'moto' 代表機車，'needs_translation' 代表是否需特定譯本(如日本)
COUNTRY_DATA = {
    "亞洲地區": {
        "日本 (Japan)": {"car": True, "moto": True, "note": "需持「日文譯本」及原照，不適用一般IDP", "needs_translation": True},
        "韓國 (South Korea)": {"car": True, "moto": True, "note": "互惠開放國際駕照"},
        "泰國 (Thailand)": {"car": True, "moto": True, "note": "國際駕照簽證有效"},
        "菲律賓 (Philippines)": {"car": True, "moto": True, "note": ""},
        "馬來西亞 (Malaysia)": {"car": True, "moto": True, "note": "90天內免簽，超過需換照"},
        "新加坡 (Singapore)": {"car": True, "moto": False, "note": "機車不具互惠"},
        "香港 (Hong Kong)": {"car": True, "moto": True, "note": ""},
        "澳門 (Macau)": {"car": True, "moto": True, "note": ""},
    },
    "北美洲地區": {
        "美國 (USA)": {"car": True, "moto": False, "note": "機車多不具互惠；各州規定不同，建議查閱各州專則"},
        "加拿大 (Canada)": {"car": True, "moto": True, "note": "各省多具備汽車互惠"},
    },
    "歐洲地區": {
        "法國 (France)": {"car": True, "moto": True, "note": ""},
        "德國 (Germany)": {"car": True, "moto": True, "note": ""},
        "英國 (UK)": {"car": True, "moto": True, "note": ""},
        "義大利 (Italy)": {"car": True, "moto": True, "note": ""},
        "荷蘭 (Netherlands)": {"car": True, "moto": True, "note": ""},
        "比利時 (Belgium)": {"car": True, "moto": True, "note": ""},
        "瑞士 (Switzerland)": {"car": True, "moto": True, "note": ""},
    },
    "大洋洲地區": {
        "澳洲 (Australia)": {"car": True, "moto": True, "note": "包含昆士蘭、維多利亞等各州"},
        "紐西蘭 (New Zealand)": {"car": True, "moto": True, "note": ""},
    }
}


import streamlit as st
from datetime import datetime, timedelta

# 引入上方資料 (簡化起見直接放這)
DATA = COUNTRY_DATA 

st.set_page_config(page_title="國際駕照簽證天數查詢", page_icon="🌐")

st.title("🚗 國際駕照在台可駕天數查詢")
st.markdown("---")

# --- UI 分區 ---
with st.sidebar:
    st.header("1️⃣ 選擇來源")
    region = st.selectbox("選擇區域", options=list(DATA.keys()))
    country_list = list(DATA[region].keys())
    selected_country = st.selectbox("選擇國家/地區", options=country_list)
    
    drive_type = st.radio("預計駕駛種類", ["汽車", "機車"])
    
    st.header("2️⃣ 重要日期輸入")
    entry_date = st.date_input("入境台灣日期", value=datetime.now())
    idp_expiry = st.date_input("國際駕照 (IDP) 截止日")
    visa_expiry = st.date_input("簽證/居留證 (ARC) 截止日")

# --- 邏輯判斷 ---
country_info = DATA[region][selected_country]
can_drive = True

# 判斷互惠資格
if drive_type == "機車" and not country_info["moto"]:
    st.error(f"❌ 抱歉，{selected_country} 的機車駕照在台灣不具備互惠資格。")
    can_drive = False
elif drive_type == "汽車" and not country_info["car"]:
    st.error(f"❌ 抱歉，{selected_country} 的汽車駕照在台灣不具備互惠資格。")
    can_drive = False

if can_drive:
    # 三者取其早原則
    max_legal_stay = entry_date + timedelta(days=364) # 入境一年
    final_date = min(max_legal_stay, idp_expiry, visa_expiry)
    
    # 計算剩餘天數
    today = datetime.now().date()
    days_left = (final_date - today).days

    # 顯示主結果
    st.success(f"### ✅ 您可以合法駕駛至：{final_date}")
    
    c1, c2 = st.columns(2)
    c1.metric("截止日期", str(final_date))
    c2.metric("剩餘有效天數", f"{max(0, days_left)} 天")

    # 30天關鍵提醒
    visa_deadline = entry_date + timedelta(days=30)
    if today <= visa_deadline:
        st.warning(f"⚠️ **重要提醒**：您目前處於免辦登記期（入境30天內）。若要在台灣駕駛超過 {visa_deadline}，請務必在此日期前持件至監理站辦理『簽證(登記)』。")
    
    if country_info["note"]:
        st.info(f"📌 **國家備註**：{country_info['note']}")

st.markdown("---")
st.caption("資料來源：交通部公路局主要國家駕照互惠情形一覽表。請注意，美國各州及加拿大各省規定有細微差異，建議同時諮詢當地監理所。")

