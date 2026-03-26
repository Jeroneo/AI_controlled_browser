import streamlit as st
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="DeepSeek Browser Agent", layout="wide")

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "browser_started" not in st.session_state:
    st.session_state.browser_started = False

# --- SIDEBAR & CONTROLS ---
with st.sidebar:
    st.title("🤖 Browser Control")
    api_key = st.text_input("DeepSeek API Key", type="password")
    show_code = st.checkbox("Show generated code (Debug)", value=False)
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        if st.button("🚀 Start", use_container_width=True):
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1280,720")
            
            st.session_state.driver = webdriver.Chrome(options=chrome_options)
            st.session_state.driver.get("https://www.google.com")
            st.session_state.browser_started = True
            st.success("Started!")

    with col_b:
        if st.button("🛑 Stop", type="primary", use_container_width=True):
            if "driver" in st.session_state:
                try:
                    st.session_state.driver.quit()
                except:
                    pass
            st.session_state.browser_started = False
            st.session_state.messages = []
            st.warning("Browser Session Terminated.")
            st.rerun()

# --- CORE LOGIC ---
def get_page_context(driver):
    elements = driver.find_elements(By.XPATH, "//button | //input | //a | //select | //textarea")
    context = []
    for i, el in enumerate(elements):
        try:
            if el.is_displayed():
                tag = el.tag_name
                text = (el.text or el.get_attribute("placeholder") or el.get_attribute("name") or "")
                context.append(f"Index {i}: <{tag}> '{text}'")
        except: continue
    return "\n".join(context[:50])

def execute_code(code_str):
    # Regex to clean DeepSeek's code output
    code_pattern = r"```python\n(.*?)```"
    match = re.search(code_pattern, code_str, re.DOTALL)
    clean_code = match.group(1).strip() if match else code_str.strip()
    clean_code = clean_code.replace("```python", "").replace("```", "")
    
    # Inject driver and essential Selenium tools into the execution context
    locs = {
        "driver": st.session_state.driver, 
        "By": By,
        "Keys": Keys,
        "WebDriverWait": WebDriverWait,
        "EC": EC,
        "time": time
    }
    
    try:
        exec(clean_code, globals(), locs)
        return True, "Success"
    except Exception as e:
        return False, str(e)

# --- UI LAYOUT (Stacked Vertically) ---

st.subheader("Live View")
if st.session_state.browser_started:
    
    # This fragment runs continuously in the background every 2 seconds
    @st.fragment(run_every="2s")
    def render_live_view():
        try:
            # Update screenshot
            screenshot = st.session_state.driver.get_screenshot_as_png()
            st.image(screenshot, use_container_width=True) 
            st.caption(f"📍 {st.session_state.driver.current_url}")
        except Exception as e:
            st.error("Browser session lost. Please click 'Stop' then 'Start' again.")
            
    render_live_view()
    
else:
    st.info("Launch the browser to see the live view.")

st.divider()

st.subheader("Chat")
# Reduced height slightly so the input box stays visible when the image is large above it
chat_container = st.container(height=400) 

for message in st.session_state.messages:
    with chat_container.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ex: 'Search for NVIDIA stock'"):
    if not api_key:
        st.error("API Key required.")
    elif not st.session_state.browser_started:
        st.error("Launch browser first.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container.chat_message("user"):
            st.markdown(prompt)

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        context = get_page_context(st.session_state.driver)
        
        with chat_container.chat_message("assistant"):
            with st.spinner("Executing..."):
                sys_prompt = (
                    "You are a Selenium engine. Output ONLY Python code. "
                    "The following are already imported and available: "
                    "'driver', 'By', 'Keys', 'WebDriverWait', 'EC', and 'time'."
                )
                
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"Context:\n{context}\n\nTask: {prompt}"}
                    ]
                )
                ai_code = response.choices[0].message.content
                
                success, error_msg = execute_code(ai_code)
                
                if success:
                    display_msg = "✅ Action completed."
                    if show_code:
                        st.code(ai_code, language="python")
                    st.markdown(display_msg)
                    st.session_state.messages.append({"role": "assistant", "content": display_msg})
                else:
                    st.error(f"❌ Execution failed: {error_msg}")
                    st.code(ai_code, language="python")
