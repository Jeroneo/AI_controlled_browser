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

# --- PAGE CONFIG & CSS ---
st.set_page_config(page_title="DeepSeek Browser Agent", layout="wide")

st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

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
            # 4:3 Aspect Ratio based on the 1080p Full HD vertical height (1440x1080)
            chrome_options.add_argument("--window-size=1440,1080") 
            
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
    code_pattern = r"```python\n(.*?)```"
    match = re.search(code_pattern, code_str, re.DOTALL)
    clean_code = match.group(1).strip() if match else code_str.strip()
    clean_code = clean_code.replace("```python", "").replace("```", "")
    
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

# --- UI LAYOUT (Side-by-Side 70/30) ---
col_view, col_chat = st.columns([7, 3])

with col_view:
    st.markdown("### 📺 Live View")

    # Height adjusted to 550
    view_container = st.container(height=550)

    with view_container:
        image_placeholder = st.empty()
        caption_placeholder = st.empty()

        if st.session_state.browser_started:
            @st.fragment(run_every="2s")
            def render_live_view():
                try:
                    if len(st.session_state.driver.window_handles) > 1:
                        st.session_state.driver.switch_to.window(st.session_state.driver.window_handles[-1])

                    screenshot = st.session_state.driver.get_screenshot_as_png()
                    image_placeholder.image(screenshot, use_container_width=True) 
                    caption_placeholder.caption(f"📍 {st.session_state.driver.current_url}")
                except Exception as e:
                    image_placeholder.error("Waiting for browser state to stabilize...")
                    
            render_live_view()
        else:
            st.info("Launch the browser to see the live view.")

with col_chat:
    st.markdown("### 💬 Chat")

    # Height adjusted to 550
    chat_container = st.container(height=550) 

    for message in st.session_state.messages[-10:]:
        with chat_container.chat_message(message["role"]):
            st.markdown(message["content"])

# --- FULL WIDTH CHAT INPUT ---
# This remains at the root level, meaning Streamlit will pin it to the bottom of the viewport
if prompt := st.chat_input("Ex: 'Search for NVIDIA stock'"):
    if not api_key:
        st.error("API Key required.")
    elif not st.session_state.browser_started:
        st.error("Launch browser first.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Inject the user message into the chat container above
        with chat_container.chat_message("user"):
            st.markdown(prompt)

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        context = get_page_context(st.session_state.driver)
        
        # Inject the assistant status and response into the chat container above
        with chat_container.chat_message("assistant"):
            with st.status("Executing task...") as status:
                sys_prompt = (
                    "You are a Selenium engine. Output ONLY Python code. "
                    "The following are already imported and available: "
                    "'driver', 'By', 'Keys', 'WebDriverWait', 'EC', and 'time'."
                )
                
                task_messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nTask: {prompt}"}
                ]
                
                max_attempts = 3
                success = False
                
                for attempt in range(1, max_attempts + 1):
                    status.update(label=f"Executing task... (Attempt {attempt}/{max_attempts})")
                    
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=task_messages
                    )
                    ai_code = response.choices[0].message.content
                    
                    success, error_msg = execute_code(ai_code)
                    
                    if success:
                        time.sleep(1.5) 
                        status.update(label=f"✅ Action completed on attempt {attempt}.", state="complete")
                        display_msg = "✅ Action completed."
                        st.markdown(display_msg)
                        if show_code:
                            st.code(ai_code, language="python")
                        st.session_state.messages.append({"role": "assistant", "content": display_msg})
                        break  
                    else:
                        st.write(f"❌ Attempt {attempt} failed: `{error_msg}`. Asking AI to fix...")
                        task_messages.append({"role": "assistant", "content": ai_code})
                        task_messages.append({
                            "role": "user", 
                            "content": f"The code failed with this error:\n{error_msg}\n\nPlease fix the code and try again. Output ONLY the corrected Python code."
                        })
                
                if not success:
                    status.update(label="❌ Task failed after maximum attempts.", state="error")
                    st.error(f"Execution completely failed. Last error: {error_msg}")
                    if show_code:
                        st.code(ai_code, language="python")
                    st.session_state.messages.append({"role": "assistant", "content": "❌ Action failed."})

        st.rerun()
