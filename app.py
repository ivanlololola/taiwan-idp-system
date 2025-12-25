import streamlit as st
import pdfplumber
import os
import json
from datetime import datetime, timedelta
import re

# 優先嘗試導入可用的 AI 套件
AI_BACKENDS = {}

try:
    from openai import OpenAI
    AI_BACKENDS['OpenAI'] = True
except ImportError:
    AI_BACKENDS['OpenAI'] = False

try:
    import google.generativeai as genai
    AI_BACKENDS['Gemini'] = True
except ImportError:
    AI_BACKENDS['Gemini'] = False

try:
    import anthropic
    AI_BACKENDS['Claude'] = True
except ImportError:
    AI_BACKENDS['Claude'] = False

# --- 系統設定 ---
st.set_page_config(
    page_title="全球駕照 AI 智能 RAG 系統",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 知識庫處理 ---
@st.cache_resource
def load_and_preprocess_pdfs(data_dir):
    """讀取所有 PDF 並建立文字索引"""
    knowledge_base = {}
    errors = []
    
    if not os.path.exists(data_dir):
        return None, f"找不到資料夾: {data_dir}"
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.pdf')]
    if not files:
        return None, f"'{data_dir}' 資料夾中沒有 PDF 檔案"
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, file in enumerate(files):
        status_text.text(f"載入中: {file}")
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
        
        progress_bar.progress((idx + 1) / len(files))
    
    progress_bar.empty()
    status_text.empty()
    
    error_msg = "\n".join(errors) if errors else None
    return knowledge_base, error_msg

# --- 輸入驗證 ---
def validate_dates(entry_date, idp_exp, legal_exp):
    """驗證日期邏輯"""
    errors = []
    today = datetime.now().date()
    
    if entry_date > today:
        errors.append("入境日期不可晚於今天")
    if idp_exp < entry_date:
        errors.append("國際駕照到期日不可早於入境日")
    if legal_exp < entry_date:
        errors.append("簽證到期日不可早於入境日")
    
    return errors

def sanitize_input(text):
    """清理使用者輸入"""
    if not text:
        return ""
    return re.sub(r'[^\w\s\u4e00-\u9fff-]', '', text).strip()

# --- 智能檢索 ---
def smart_retrieve_context(full_text, target_country, context_window=1500):
    """智能檢索相關文本片段"""
    aliases = {
        "美國": ["USA", "United States", "U.S.A", "America"],
        "英國": ["UK", "United Kingdom", "Britain", "England"],
        "日本": ["Japan", "日本国"],
        "韓國": ["Korea", "South Korea", "대한민국", "南韓"],
        "德國": ["Germany", "Deutschland"],
        "法國": ["France", "Francia"],
        "澳洲": ["Australia", "澳大利亞"],
        "加拿大": ["Canada"],
        "新加坡": ["Singapore"],
    }
    
    country_variants = [target_country]
    for key, values in aliases.items():
        if target_country in [key] + values:
            country_variants.extend([key] + values)
            break
    
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
    
    start_idx, found_variant = positions[0]
    context_start = max(0, start_idx - 300)
    context_end = min(len(full_text), start_idx + context_window)
    context = full_text[context_start:context_end]
    
    return context, found_variant

# --- AI 分析函數 ---
def analyze_with_openai(api_key, country, context):
    """使用 OpenAI GPT 分析"""
    try:
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "你是駕照法規分析專家。請分析法規並以 JSON 格式回傳結果。"
                },
                {
                    "role": "user",
                    "content": f"""請分析以下駕照互惠法規：

國家: {country}
法規內容:
{context}

請以 JSON 格式回傳：
{{
    "motorcycle_eligible": true/false,
    "translation_required": true/false,
    "limit_days": 數字,
    "reason": "判定依據"
}}"""
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        required = ['motorcycle_eligible', 'translation_required', 'limit_days', 'reason']
        if not all(field in result for field in required):
            return {"error": "回應缺少必要欄位"}
        
        return result
        
    except Exception as e:
        return {"error": f"OpenAI API 錯誤: {str(e)}"}

def analyze_with_gemini(api_key, country, context):
    """使用 Google Gemini 分析（改進版）"""
    try:
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            generation_config={
                "temperature": 0.3,
                "top_p": 0.95,
                "max_output_tokens": 1024,
            }
        )
        
        prompt = f"""請分析以下駕照互惠法規，以 JSON 格式回傳：

國家: {country}
法規內容:
{context}

請嚴格按照以下格式回傳，只要 JSON 不要其他文字：
{{
    "motorcycle_eligible": true,
    "translation_required": false,
    "limit_days": 365,
    "reason": "判定依據說明"
}}"""

        response = model.generate_content(prompt)
        
        if not response or not response.text:
            return {"error": "Gemini 未返回內容"}
        
        text = response.text.strip()
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        
        # 嘗試提取 JSON
        json_match = re.search(r'\{[^}]*"motorcycle_eligible"[^}]*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
        
        result = json.loads(text)
        
        required = ['motorcycle_eligible', 'translation_required', 'limit_days', 'reason']
        if not all(field in result for field in required):
            return {"error": f"回應缺少必要欄位: {[f for f in required if f not in result]}"}
        
        return result
        
    except json.JSONDecodeError as e:
        return {"error": f"JSON 解析錯誤。原始回應: {text[:200] if 'text' in locals() else 'N/A'}"}
    except Exception as e:
        return {"error": f"Gemini API 錯誤: {str(e)}"}

def analyze_with_claude(api_key, country, context):
    """使用 Anthropic Claude 分析"""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            temperature=0.3,
            messages=[{
                "role": "user",
                "content": f"""請分析以下駕照互惠法規：

國家: {country}
法規內容:
{context}

請以 JSON 格式回傳：
{{
    "motorcycle_eligible": true/false,
    "translation_required": true/false,
    "limit_days": 數字,
    "reason": "判定依據"
}}"""
            }]
        )
        
        result = json.loads(message.content[0].text)
        
        required = ['motorcycle_eligible', 'translation_required', 'limit_days', 'reason']
        if not all(field in result for field in required):
            return {"error": "回應缺少必要欄位"}
        
        return result
        
    except Exception as e:
        return {"error": f"Claude API 錯誤: {str(e)}"}

# --- 主介面 ---
st.title("📑 全球駕照互惠 AI 智能查詢系統")
st.caption("智能 RAG 系統 | 支援多種 AI 模型")

# 檢查可用的 AI 後端
available_backends = [k for k, v in AI_BACKENDS.items() if v]

if not available_backends:
    st.error("❌ 未安裝任何 AI 套件")
    st.info("""
    請在您的 `requirements.txt` 中添加至少一個套件：
    ```
    openai
    google-generativeai
    anthropic
    ```
    """)
    st.stop()

# 側邊欄
with st.sidebar:
    st.header("🔧 系統設定")
    
    # 選擇 AI 後端
    st.subheader("AI 模型選擇")
    
    # 為每個後端添加推薦標籤
    backend_options = []
    for backend in available_backends:
        if backend == "OpenAI":
            backend_options.append("OpenAI GPT ⭐ 推薦")
        elif backend == "Gemini":
            backend_options.append("Google Gemini 🆓 免費")
        elif backend == "Claude":
            backend_options.append("Anthropic Claude")
    
    selected_option = st.selectbox("選擇 AI 模型", backend_options)
    
    # 解析選擇
    if "OpenAI" in selected_option:
        ai_backend = "OpenAI"
    elif "Gemini" in selected_option:
        ai_backend = "Gemini"
    else:
        ai_backend = "Claude"
    
    # API Key 輸入
    st.subheader("API Key")
    
    # 嘗試從 Streamlit Secrets 讀取
    api_key_from_secrets = None
    try:
        if ai_backend == "OpenAI" and "OPENAI_API_KEY" in st.secrets:
            api_key_from_secrets = st.secrets["OPENAI_API_KEY"]
        elif ai_backend == "Gemini" and "GEMINI_API_KEY" in st.secrets:
            api_key_from_secrets = st.secrets["GEMINI_API_KEY"]
        elif ai_backend == "Claude" and "CLAUDE_API_KEY" in st.secrets:
            api_key_from_secrets = st.secrets["CLAUDE_API_KEY"]
    except:
        pass
    
    if api_key_from_secrets:
        st.success("✅ 已從 Secrets 載入 API Key")
        api_key = api_key_from_secrets
        show_input = st.checkbox("手動輸入其他 API Key")
        if show_input:
            api_key = st.text_input(f"{ai_backend} API Key", type="password")
    else:
        api_key = st.text_input(f"{ai_backend} API Key", type="password")
        
        if ai_backend == "OpenAI":
            st.caption("🔗 [取得 API Key](https://platform.openai.com/api-keys)")
        elif ai_backend == "Gemini":
            st.caption("🔗 [取得 API Key (免費)](https://aistudio.google.com/app/apikey)")
        else:
            st.caption("🔗 [取得 API Key](https://console.anthropic.com/)")
    
    st.divider()
    
    # 使用說明
    with st.expander("📖 使用說明"):
        st.markdown("""
        ### 🚀 快速開始
        1. 選擇 AI 模型
        2. 輸入 API Key（或設定 Secrets）
        3. 選擇州別
        4. 輸入國家名稱
        5. 填寫日期資訊
        6. 點擊「開始分析」
        
        ### 💡 推薦設定
        - **OpenAI**: 最穩定，JSON 格式可靠
        - **Gemini**: 完全免費，適合測試
        - **Claude**: 高品質回應
        
        ### 🔐 Secrets 設定（推薦）
        在 Streamlit Cloud 的 Settings → Secrets 中添加：
        ```toml
        OPENAI_API_KEY = "sk-..."
        GEMINI_API_KEY = "AI..."
        CLAUDE_API_KEY = "sk-ant-..."
        ```
        """)
    
    if st.button("🔄 重新載入 PDF"):
        st.cache_resource.clear()
        st.rerun()

# 載入知識庫
data_folder = "data"

with st.spinner("📚 載入知識庫..."):
    kb, load_error = load_and_preprocess_pdfs(data_folder)

if not kb:
    st.error("❌ 無法載入知識庫")
    if load_error:
        st.error(load_error)
    st.info("請確認 GitHub 專案中的 `data/` 資料夾包含 PDF 檔案")
    st.stop()
else:
    st.success(f"✅ 已載入 {len(kb)} 個州別的資料")
    if load_error:
        with st.expander("⚠️ 部分檔案載入問題"):
            st.warning(load_error)

if not api_key:
    st.warning("👈 請在側邊欄輸入 API Key")
    st.info(f"""
    💡 **提示**: 使用 {ai_backend} 需要 API Key
    
    **方法 1**: 在側邊欄手動輸入
    **方法 2**: 在 Streamlit Cloud Secrets 中設定（推薦）
    """)
    st.stop()

# 查詢介面
st.divider()
col1, col2 = st.columns(2)

with col1:
    region_choice = st.selectbox("📍 選擇州別", list(kb.keys()))

with col2:
    target_country_raw = st.text_input(
        "🌏 輸入查詢國家",
        placeholder="例如: 德國、日本、USA"
    )
    target_country = sanitize_input(target_country_raw)

# 日期輸入
st.divider()
st.subheader("📅 日期資訊")
c1, c2, c3 = st.columns(3)

with c1:
    entry_date = st.date_input("入境日期", datetime.now())
with c2:
    idp_exp = st.date_input("國際駕照到期日", datetime.now() + timedelta(days=365))
with c3:
    legal_exp = st.date_input("簽證/居留證到期日", datetime.now() + timedelta(days=180))

# 驗證日期
date_errors = validate_dates(entry_date, idp_exp, legal_exp)
if date_errors:
    for error in date_errors:
        st.error(f"❌ {error}")

# 執行查詢
if target_country and not date_errors:
    if st.button("🔍 開始分析", type="primary", use_container_width=True):
        
        # 檢索
        full_text = kb.get(region_choice, "")
        context, found_variant = smart_retrieve_context(full_text, target_country)
        
        if context is None:
            st.warning(f"⚠️ 在 {region_choice} 中找不到「{target_country}」")
            st.info("💡 建議:\n- 檢查國家名稱拼寫\n- 嘗試使用英文\n- 選擇其他州別")
            st.stop()
        
        st.info(f"📝 找到匹配: {found_variant}")
        
        # 選擇對應的分析函數
        with st.spinner(f"🤖 使用 {ai_backend} 分析中..."):
            if ai_backend == "OpenAI":
                res = analyze_with_openai(api_key, target_country, context)
            elif ai_backend == "Gemini":
                res = analyze_with_gemini(api_key, target_country, context)
            else:
                res = analyze_with_claude(api_key, target_country, context)
        
        if "error" in res:
            st.error(f"❌ 分析失敗: {res['error']}")
            
            with st.expander("💡 除錯建議"):
                st.markdown(f"""
                **常見問題排查：**
                
                1. **API Key 錯誤**
                   - 確認 API Key 是否正確
                   - 檢查是否有多餘空格
                   - 確認帳戶是否有額度
                
                2. **模型回應格式問題**
                   - 建議切換到 OpenAI（最穩定）
                   - OpenAI 有內建 JSON mode
                
                3. **網路問題**
                   - Streamlit Cloud 的網路通常穩定
                   - 檢查 API 服務狀態
                
                4. **切換模型**
                   - 在側邊欄嘗試其他 AI 模型
                """)
            st.stop()
        
        # 顯示結果
        st.success(f"✅ 分析完成 (使用 {ai_backend})")
        
        # 計算最終日期
        law_days = res.get("limit_days", 365)
        calculated_end = entry_date + timedelta(days=law_days)
        final_date = min(calculated_end, idp_exp, legal_exp)
        
        # 指標顯示
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        
        m1.metric("📅 最終可使用日", str(final_date))
        m2.metric("⚖️ 法定天數", f"{law_days} 天")
        
        motorcycle = "✅ 有資格" if res['motorcycle_eligible'] else "❌ 無資格"
        m3.metric("🏍️ 機車互惠", motorcycle)
        
        translation = "✅ 需要" if res['translation_required'] else "❌ 不需要"
        m4.metric("📄 中文譯本", translation)
        
        # 警告
        st.divider()
        if not res['motorcycle_eligible']:
            st.error(f"🚨 {target_country} 的機車駕照不具互惠資格")
        else:
            st.success(f"✅ {target_country} 的機車駕照具備互惠資格")
        
        st.info(f"**📋 判定依據**\n\n{res['reason']}")
        
        # 剩餘天數
        remaining = (final_date - datetime.now().date()).days
        if remaining > 0:
            st.success(f"✅ 還可使用 **{remaining}** 天")
        else:
            st.error(f"❌ 已超過期限 {abs(remaining)} 天")
        
        # 詳細資訊
        with st.expander("🔍 原始文字片段"):
            st.code(context, language="text")
        
        with st.expander("🤖 AI 完整回應"):
            st.json(res)

elif target_country and date_errors:
    st.warning("⚠️ 請先修正日期錯誤")

# 頁尾
st.divider()
st.caption("⚠️ 本系統僅供參考，實際規定以監理所為準")
st.caption(f"🤖 當前模型: {ai_backend} | 🔐 部署於 Streamlit Cloud")
