import hashlib
import json
import os
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import requests
import streamlit as st
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STT_URL = "https://api.vachana.ai/stt/v3"  # Gnani speech-to-text (REST, short clips)
TTS_URL = "https://api.vachana.ai/tts/v2"  # Gnani text-to-speech: verify at docs.gnani.ai
GEMINI_MODEL = "gemini-2.5-flash"
CATEGORIES = ["Food", "Transport", "Groceries", "Bills", "Shopping", "Other"]
AMOUNT_COL = "Amount (₹)"

st.set_page_config(page_title="BolPay - Voice UPI & Expense Tracker", page_icon="🎙️", layout="wide")


def get_secret(name):
    value = os.getenv(name, "")
    if not value:
        try:
            value = st.secrets.get(name, "")
        except Exception:
            value = ""
    return value


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔑 API Configuration")
    gnani_key = st.text_input("Gnani.ai API Key", type="password", value=get_secret("GNANI_KEY"))
    gemini_key = st.text_input("Gemini API Key", type="password", value=get_secret("GEMINI_KEY"))
    upi_id = st.text_input("Your UPI ID", value="merchant@upi")
    speech_lang = st.selectbox("Speaking language", ["hi-IN", "en-IN"])
    voice_lang = st.selectbox("Voice reply language", ["hi-IN", "en-IN"])
    speak_reply = st.checkbox("Speak a voice confirmation", value=True)
    st.caption("Keys stay in your browser session and are never saved in the code.")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
if "expenses" not in st.session_state:
    st.session_state.expenses = [
        {"Date": "2026-11-13", "Item": "Chai & Snacks", "Category": "Food", AMOUNT_COL: 60.0, "Mode": "UPI"},
        {"Date": "2026-11-13", "Item": "Metro Card Recharge", "Category": "Transport", AMOUNT_COL: 200.0, "Mode": "UPI"},
    ]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def transcribe_audio(audio_bytes, api_key, lang):
    headers = {"X-API-Key-ID": api_key}
    files = {"audio_file": ("recording.wav", audio_bytes, "audio/wav")}
    data = {"language_code": lang, "format": "transcribe"}
    res = requests.post(STT_URL, headers=headers, files=files, data=data, timeout=60)
    res.raise_for_status()
    result = res.json()
    return result.get("transcript") or result.get("text") or str(result)


def extract_expenses(text, api_key):
    client = genai.Client(api_key=api_key)
    prompt = (
        "Extract every expense from this Indian spoken text (Hindi, Hinglish or English): "
        f'"{text}". '
        "Return ONLY a JSON array. Each element must have: "
        '"item" (short English name), '
        '"category" (one of Food, Transport, Groceries, Bills, Shopping, Other), '
        '"amount" (number in INR), '
        '"mode" (UPI by default, Cash only if clearly said).'
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    raw = (response.text or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        parsed = parsed.get("expenses", [parsed])
    return parsed


def generate_voice_reply(text, lang, api_key):
    headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
    voice_name = "Nalini" if lang == "hi-IN" else "Rhea"
    payload = {"text": text, "voice": voice_name, "model": "timbre-v2.5", "language": lang}
    res = requests.post(TTS_URL, headers=headers, json=payload, timeout=60)
    res.raise_for_status()
    return res.content


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------
def add_expenses(items):
    today = datetime.now().strftime("%Y-%m-%d")
    count, total = 0, 0.0
    for entry in items:
        try:
            amount = float(entry.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        category = entry.get("category", "Other")
        if category not in CATEGORIES:
            category = "Other"
        st.session_state.expenses.append(
            {
                "Date": today,
                "Item": str(entry.get("item", "Expense")),
                "Category": category,
                AMOUNT_COL: amount,
                "Mode": str(entry.get("mode", "UPI")),
            }
        )
        count += 1
        total += amount
    return count, total


def build_reply(count, total, lang):
    if lang == "hi-IN":
        return f"Aapke {count} kharche, kul {int(total)} rupaye, add kar diye gaye hain."
    return f"Logged {count} expenses totaling {int(total)} rupees."


def handle_text(text):
    items = extract_expenses(text, gemini_key)
    count, total = add_expenses(items)
    if count == 0:
        st.warning("No expenses found in that text. Try again, for example: Auto 150 aur lunch 220.")
        return
    reply = build_reply(count, total, voice_lang)
    st.success(reply)
    if speak_reply and gnani_key:
        try:
            st.audio(generate_voice_reply(reply, voice_lang, gnani_key), format="audio/wav", autoplay=True)
        except Exception as err:
            st.warning(f"Voice reply skipped: {err}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("🎙️ BolPay: Voice-First UPI & Expense Tracker")
st.caption("Speak your expenses in Hinglish, Hindi or English, for example: Auto ke 150 rupaye aur lunch ke 220")

tab_voice, tab_text, tab_manual = st.tabs(["🎤 Voice", "⌨️ Type", "✍️ Manual"])

with tab_voice:
    audio_value = st.audio_input("Tap the microphone and speak your expense")
    if audio_value is not None:
        audio_bytes = audio_value.getvalue()
        audio_hash = hashlib.md5(audio_bytes).hexdigest()
        if st.session_state.get("last_audio") != audio_hash:
            if not gnani_key or not gemini_key:
                st.error("Please enter both the Gnani.ai and Gemini API keys in the sidebar.")
            else:
                st.session_state.last_audio = audio_hash
                with st.spinner("Listening and understanding..."):
                    try:
                        transcript = transcribe_audio(audio_bytes, gnani_key, speech_lang)
                        st.info(f"🗣️ Heard: {transcript}")
                        handle_text(transcript)
                    except Exception as err:
                        st.error(f"Error processing audio: {err}")

with tab_text:
    typed = st.text_input("Type what you spent", placeholder="Auto ke 150 rupaye aur lunch ke 220")
    if st.button("Add from text"):
        if not gemini_key:
            st.error("Please enter the Gemini API key in the sidebar.")
        elif not typed.strip():
            st.warning("Type something first.")
        else:
            with st.spinner("Understanding..."):
                try:
                    handle_text(typed.strip())
                except Exception as err:
                    st.error(f"Error: {err}")

with tab_manual:
    c1, c2, c3, c4 = st.columns(4)
    m_item = c1.text_input("Item")
    m_cat = c2.selectbox("Category", CATEGORIES)
    m_amt = c3.number_input("Amount (₹)", min_value=0.0, step=10.0)
    m_mode = c4.selectbox("Mode", ["UPI", "Cash"])
    if st.button("Add expense"):
        if m_item.strip() and m_amt > 0:
            st.session_state.expenses.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Item": m_item.strip(),
                    "Category": m_cat,
                    AMOUNT_COL: float(m_amt),
                    "Mode": m_mode,
                }
            )
            st.success("Expense added.")
        else:
            st.warning("Enter an item and an amount above 0.")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
df = pd.DataFrame(st.session_state.expenses)

m1, m2, m3 = st.columns(3)
m1.metric("Total Spent", f"₹{df[AMOUNT_COL].sum():,.0f}")
m2.metric("Transactions Logged", len(df))
top_cat = df.groupby("Category")[AMOUNT_COL].sum().idxmax() if not df.empty else "N/A"
m3.metric("Top Category", top_cat)

left, right = st.columns([1.4, 1])
with left:
    st.subheader("📋 Recent Expenses")
    st.dataframe(df.iloc[::-1], hide_index=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="bolpay_expenses.csv",
        mime="text/csv",
    )
with right:
    st.subheader("📊 Spend by Category")
    if not df.empty:
        st.bar_chart(df.groupby("Category")[AMOUNT_COL].sum())

if not df.empty:
    last = df.iloc[-1]
    upi_link = (
        f"upi://pay?pa={quote(upi_id)}&pn=Merchant&am={float(last[AMOUNT_COL])}"
        f"&cu=INR&tn={quote(str(last['Item']))}"
    )
    st.markdown(
        f"💳 **Quick Pay Last Item ({last['Item']} - ₹{int(last[AMOUNT_COL])}):** [Open UPI App]({upi_link})"
    )

if st.button("Clear all expenses"):
    st.session_state.expenses = []
    st.rerun()