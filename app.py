import streamlit as st
import google.generativeai as genai
import pdfplumber
import os
import json
from datetime import datetime, timedelta
import re

# --- 1. 系統初始化與設定 ---
st.set_page_config(page_title="全球駕照 AI 智能 RAG 系統", layout="wide")

# --- 2. 知識庫處理 (RAG 核心) ---
@st.cache_resource
def load_and_preprocess_pdfs(data_dir):
    """讀取所有 PDF 並建立文字索引，僅在啟動或清理快取時執行一次"""
    knowledge_base = {}
    if not os.path.exists(data_dir):
        return None, f"找不到資料夾: {data_dir}"
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.pdf')]
    if not files:
        return None, f"'{data_dir}' 資料夾中沒有 PDF 檔案"
    
    errors = []
    for file in files:
        region = file.replace(".pdf", "")
        text_content = ""
        try:
            with pdfplumber.open(os.path.join(data_dir, file)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
            
            if text_content.strip():
                knowledge_base[region] = text_content
            else:
                errors.append(f"{file}: PDF 無法提取文字內容")
        except Exception as e:
            errors.append(f"{file}: {str(e)}")
    
    error_msg = "\n".join(errors) if errors else None
    return knowledge_base, error_msg

# --- 3. 輸入驗證函數 ---
def validate_api_key(api_key):
    """驗證 API Key 格式"""
    if not api_key:
        return False, "API Key 不可為空"
    if len(api_key) < 20:
        return False, "API Key 長度過短，請確認是否完整"
    return True, ""

def validate_dates(entry_date, idp_exp, legal_exp):
    """驗證日期邏輯"""
    errors = []
    today = datetime.now().date()
    
    if entry_date > today:
        errors.append("入境日期不可晚於今天")
    if idp_exp < today:
        errors.append("國際駕照已過期")
    if legal_exp < today:
        errors.append("簽證/居留證已過期")
    if idp_exp < entry_date:
        errors.append("國際駕照到期日不可早於入境日")
    if legal_exp < entry_date:
        errors.append("簽證/居留證到期日不可早於入境日")
    
    return errors

def sanitize_country_name(country):
    """清理國家名稱輸入"""
    if not country:
        return ""
    # 移除特殊字元，只保留中英文、數字、空格
    return re.sub(r'[^\w\s\u4e00-\u9fff-]', '', country).strip()

# --- 4. 智能檢索函數 (改進版) ---
def smart_retrieve_context(full_text, target_country, context_window=1500):
    """
    智能檢索與目標國家相關的文本片段
    支援多種國家名稱變體
    """
    # 建立國家名稱變體列表
    country_variants = [target_country]
    
    # 常見的國家別名對應
    aliases = {
        "美國": ["USA", "United States", "U.S.A", "America"],
        "英國": ["UK", "United Kingdom", "Britain", "England"],
        "中國": ["China", "PRC", "中華人民共和國"],
        # 可以根據需要擴充...
    }
    
    for key, values in aliases.items():
        if target_country in [key] + values:
            country_variants.extend([key] + values)
            break
    
    # 搜尋所有可能的出現位置
    positions = []
    for variant in set(country_variants):
        idx = 0
        while True:
            idx = full_text.find(variant, idx)
            if idx == -1:
                break
            positions.append((idx, variant))
            idx += 1
    
    if not positions:
        return None, None
    
    # 選擇第一個出現的位置（可改進為選擇最相關的）
    start_idx, found_variant = positions[0]
    
    # 動態調整擷取範圍
    context_start = max(0, start_idx - 300)
    context_end = min(len(full_text), start_idx + context_window)
    context = full_text[context_start:context_end]
    
    return context, found_variant

# --- 5. Gemini 串接邏輯 (改進版) ---
def analyze_with_gemini(api_key, country, context, max_retries=2):
    """
    使用 Gemini 分析駕照互惠法規
    包含完整的錯誤處理和重試機制
    """
    # 驗證 API Key
    is_valid, error_msg = validate_api_key(api_key)
    if not is_valid:
        return {"error": error_msg}
    
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return {"error": f"API Key 設定失敗: {str(e)}"}
    
    # 構建明確的 Prompt
    prompt = f"""請仔細分析以下駕照互惠法規，並以 JSON 格式回傳分析結果。

國家: {country}

法規內容:
{context}

請嚴格按照以下 JSON 格式回傳，不要包含任何其他文字或註解:
{{
    "motorcycle_eligible": true 或 false (該國機車是否具備互惠資格),
    "translation_required": true 或 false (是否需要中文譯本),
    "limit_days": 數字 (法定可使用天數，預設 365),
    "reason": "簡短的判定依據說明"
}}
"""
    
    for attempt in range(max_retries):
        try:
            # 使用正確的模型名稱
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            if not response or not response.text:
                if attempt < max_retries - 1:
                    continue
                return {"error": "AI 未返回任何內容"}
            
            # 清理回應文字
            text = response.text.strip()
            # 移除可能的 Markdown 程式碼區塊標記
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            # 嘗試解析 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # 嘗試修復常見的 JSON 錯誤
                text = text.replace("'", '"')  # 單引號改雙引號
                text = re.sub(r',\s*}', '}', text)  # 移除結尾多餘逗號
                text = re.sub(r',\s*]', ']', text)
                result = json.loads(text)
            
            # 驗證必要欄位
            required_fields = ['motorcycle_eligible', 'translation_required', 'limit_days', 'reason']
            missing_fields = [f for f in required_fields if f not in result]
            
            if missing_fields:
                if attempt < max_retries - 1:
                    continue
                return {"error": f"AI 回應缺少必要欄位: {', '.join(missing_fields)}"}
            
            # 驗證資料型別
            if not isinstance(result['motorcycle_eligible'], bool):
                result['motorcycle_eligible'] = str(result['motorcycle_eligible']).lower() in ['true', '1', 'yes']
            if not isinstance(result['translation_required'], bool):
                result['translation_required'] = str(result['translation_required']).lower() in ['true', '1', 'yes']
            if not isinstance(result['limit_days'], (int, float)):
                try:
                    result['limit_days'] = int(result['limit_days'])
                except:
                    result['limit_days'] = 365
            
            return result
            
        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                return {"error": f"AI 回傳的 JSON 格式錯誤: {str(e)}\n原始回應: {text[:200]}"}
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": f"API 呼叫失敗: {str(e)}"}
    
    return {"error": "超過最大重試次數，請稍後再試"}

# --- 6. 主程式介面 ---
st.title("📑 全球駕照互惠 AI 智能查詢系統 (RAG 版)")
st.caption("由 Gemini 1.5 Flash 提供動力，自動讀取監理所最新 PDF 備註")

# 側邊欄設定
with st.sidebar:
    st.header("🔑 系統設定")
    api_key = st.text_input("Gemini API Key", type="password", help="請至 Google AI Studio 申請")
    
    if api_key:
        is_valid, msg = validate_api_key(api_key)
        if is_valid:
            st.success("✅ API Key 格式正確")
        else:
            st.error(f"❌ {msg}")
    
    st.divider()
    st.info("💡 **使用說明**\n1. 輸入 API Key\n2. 選擇州別\n3. 輸入國家名稱\n4. 填寫相關日期")
    
    if st.button("🔄 重新載入 PDF"):
        st.cache_resource.clear()
        st.rerun()

# 載入知識庫
data_folder = "data"
with st.spinner("正在載入 PDF 知識庫..."):
    kb, load_error = load_and_preprocess_pdfs(data_folder)

if not kb:
    st.error(f"❌ 無法載入知識庫")
    if load_error:
        st.error(load_error)
    st.info(f"請確認 '{data_folder}' 資料夾存在且包含 PDF 檔案")
    st.stop()
else:
    st.success(f"✅ 已載入 {len(kb)} 個州別的資料")
    if load_error:
        with st.expander("⚠️ 部分檔案載入時出現問題"):
            st.warning(load_error)

# 檢查 API Key
if not api_key:
    st.warning("👈 請先在側邊欄輸入 Gemini API Key 才能啟動 AI 檢索")
    st.stop()

# 主要查詢介面
st.divider()
col1, col2 = st.columns(2)

with col1:
    region_choice = st.selectbox(
        "📍 選擇州別 (PDF 來源)", 
        list(kb.keys()),
        help="選擇要查詢的州別法規資料"
    )

with col2:
    target_country_raw = st.text_input(
        "🌏 輸入查詢國家", 
        placeholder="例如: 德國、日本、USA",
        help="輸入國家名稱，支援中英文"
    )
    target_country = sanitize_country_name(target_country_raw)

# 日期輸入區
st.divider()
st.subheader("📅 日期資訊")
c1, c2, c3 = st.columns(3)

with c1:
    entry_date = st.date_input(
        "入境日期", 
        datetime.now(),
        help="持國際駕照入境的日期"
    )

with c2:
    idp_exp = st.date_input(
        "國際駕照到期日",
        datetime.now() + timedelta(days=365),
        help="國際駕照的有效期限"
    )

with c3:
    legal_exp = st.date_input(
        "簽證/居留證到期日",
        datetime.now() + timedelta(days=180),
        help="合法停留的最後日期"
    )

# 驗證日期
date_errors = validate_dates(entry_date, idp_exp, legal_exp)
if date_errors:
    for error in date_errors:
        st.error(f"❌ {error}")

# 執行查詢
if target_country and not date_errors:
    if st.button("🔍 開始分析", type="primary", use_container_width=True):
        with st.spinner(f"正在從 {region_choice} PDF 中檢索並分析 {target_country}..."):
            
            # RAG 檢索階段
            full_text = kb.get(region_choice, "")
            context, found_variant = smart_retrieve_context(full_text, target_country)
            
            if context is None:
                st.warning(f"⚠️ 在 {region_choice}.pdf 中找不到「{target_country}」相關資訊")
                st.info("💡 建議:\n- 檢查國家名稱拼寫\n- 嘗試使用英文名稱\n- 選擇其他州別")
                st.stop()
            
            st.info(f"📝 找到匹配關鍵字: {found_variant}")
            
            # RAG 生成階段
            res = analyze_with_gemini(api_key, target_country, context)
            
            if "error" in res:
                st.error(f"❌ AI 分析失敗: {res['error']}")
                st.stop()
            
            # 成功解析
            st.success(f"✅ AI 解析完成: {target_country}")
            
            # 計算最終使用期限
            law_days = res.get("limit_days", 365)
            calculated_end = entry_date + timedelta(days=law_days)
            final_date = min(calculated_end, idp_exp, legal_exp)
            
            # 顯示關鍵指標
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            
            m1.metric("📅 最終可使用日", str(final_date))
            m2.metric("⚖️ 法定天數", f"{law_days} 天")
            
            motorcycle_status = "✅ 有資格" if res['motorcycle_eligible'] else "❌ 無資格"
            m3.metric("🏍️ 機車互惠", motorcycle_status)
            
            translation_status = "✅ 需要" if res['translation_required'] else "❌ 不需要"
            m4.metric("📄 中文譯本", translation_status)
            
            # 風險警示
            st.divider()
            if not res['motorcycle_eligible']:
                st.error(f"🚨 **重要警告**: {target_country} 的機車駕照不具備互惠資格，不可核發臨時駕照！")
            else:
                st.success(f"✅ {target_country} 的機車駕照具備互惠資格")
            
            # 判定依據
            st.info(f"**📋 判定依據**\n\n{res['reason']}")
            
            # 限制說明
            remaining_days = (final_date - datetime.now().date()).days
            if remaining_days > 0:
                st.success(f"✅ 還可使用 **{remaining_days}** 天")
            else:
                st.error(f"❌ 已超過使用期限 {abs(remaining_days)} 天")
            
            # 詳細資訊展開區
            with st.expander("🔍 查看 AI 檢索到的原始文字片段"):
                st.code(context, language="text")
            
            with st.expander("🤖 查看 AI 完整回應"):
                st.json(res)

elif target_country and date_errors:
    st.warning("⚠️ 請先修正日期錯誤後再進行查詢")

# 頁尾
st.divider()
st.caption("⚠️ 本系統僅供參考，實際核發規定以各地監理所為準")
st.caption("📧 如有問題請洽各地監理機關 | 🔧 系統維護: AI RAG Team")
