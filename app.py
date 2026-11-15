import json
import os
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from google import genai
from google.genai import types
st.set_page_config(page_title="BolPay - Voice UPI & Expense Tracker", page_icon=" ",
layout="wide")
st.title(" BolPay: Voice-First UPI & Expense Tracker")
st.caption("Speak your expenses in Hinglish, Hindi, or English (e.g., 'Auto ke 150 rupaye aur lunch ke 220')")
with st.sidebar:
 st.header(" API Configuration")
 gnani_key = st.text_input("Gnani.ai API Key", type="password")
 gemini_key = st.text_input("Gemini API Key (Free AI Studio)", type="password")
 upi_id = st.text_input("Your Default UPI ID (Optional)", value="merchant@upi")
 voice_lang = st.selectbox("Confirmation Voice Language", ["hi-IN", "en-IN"])
if "expenses" not in st.session_state:
 st.session_state.expenses = [
 {"Date": "2026-11-13", "Item": "Chai & Snacks", "Category": "Food", "Amount (₹)": 60,
"Mode": "UPI"},
 {"Date": "2026-11-13", "Item": "Metro Card Recharge", "Category": "Transport",
"Amount (₹)": 200, "Mode": "UPI"},
 ]
def transcribe_audio(audio_bytes, api_key):
 url = "https://api.vachana.ai/stt/v3"
 headers = {"X-API-Key-ID": api_key}
 files = {"audio_file": ("recording.wav", audio_bytes, "audio/wav")}
 data = {"model": "prisma-v3.0", "language_code": "indic-auto"}
 res = requests.post(url, headers=headers, files=files, data=data, timeout=30)
 res.raise_for_status()
 result = res.json()
 return result.get("transcript") or result.get("text") or str(result)
def extract_expenses(transcript, api_key):
 client = genai.Client(api_key=api_key)
 prompt = f"""
 Extract all expenses from this Indian spoken transcript: "{transcript}".
 Return ONLY a valid JSON array of objects. Each object must have:
 - "item": string (short English name of item/service)
 - "category": string (choose one: "Food", "Transport", "Groceries", "Bills", "Shopping",
"Other")
 - "amount": number (numeric value in INR)
 - "mode": string (default "UPI" unless "Cash" is explicitly mentioned)
 """
 response = client.models.generate_content(
 model="gemini-2.5-flash",
 contents=prompt,
 config=types.GenerateContentConfig(response_mime_type="application/json"),
 )
 return json.loads(response.text)
def generate_voice_reply(text, lang, api_key):
 url = "https://api.vachana.ai/tts/v2"
 headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
 voice_name = "Nalini" if lang == "hi-IN" else "Rhea"
 payload = {"text": text, "voice": voice_name, "model": "timbre-v2.5", "language": lang}
 res = requests.post(url, headers=headers, json=payload, timeout=30)
 res.raise_for_status()
 return res.content
audio_value = st.audio_input("Tap the microphone and speak your expense")
if audio_value is not None:
 if not gnani_key or not gemini_key:
 st.error("Please enter both your Gnani.ai API Key and Gemini API Key in the sidebar.");
 else:
 with st.spinner("Transcribing with Gnani Prisma & parsing expenses..."):
   try:
    transcript = transcribe_audio(audio_value.getvalue(), gnani_key)
 st.info(f" **Heard:** {transcript}")
 items = extract_expenses(transcript, gemini_key)
 today_str = datetime.now().strftime("%Y-%m-%d")
 total_added = 0
 for entry in items: 
  amt = float(entry.get("amount", 0))
 total_added += amt
 st.session_state.expenses.append({
 "Date": today_str,
 "Item": entry.get("item", "Expense"),
 "Category": entry.get("category", "Other"),
 "Amount (₹)": amt,
 "Mode": entry.get("mode", "UPI"),
 })
 reply = ("f"Aapke {len(items)} kharche", kul {int(total_added)} rupaye, add kar
diye gaye hain.")
 if voice_lang == "hi-IN"
 else f"Logged {len(items)} expenses totaling {int(total_added)}
rupees.")
 audio_reply = generate_voice_reply(reply, voice_lang, gnani_key)
 st.audio(audio_reply, format="audio/wav", autoplay=True)
 st.success(reply)
 except Exception as e:
 st.error(f"Error processing audio: {e}")
df = pd.DataFrame(st.session_state.expenses)
col1, col2, col3 = st.columns(3)
col1.metric("Total Spent", f"₹{df['Amount (₹)'].sum():,.0f}")
col2.metric("Transactions Logged", len(df))
top_cat = df.groupby("Category")["Amount (₹)"].sum().idxmax() if not df.empty else "N/A"
col3.metric("Top Category", top_cat)
left, right = st.columns([1.4, 1])
with left:
 st.subheader(" Recent Expenses")
 st.dataframe(df.iloc[::-1], use_container_width=True, hide_index=True)
with right:
 st.subheader(" Spend by Category")
 st.bar_chart(df.groupby("Category")["Amount (₹)"].sum())
if not df.empty:
 last_amt = df.iloc[-1]["Amount (₹)"]
 last_item = df.iloc[-1]["Item"]
 upi_link = f"upi://pay?pa={upi_id}&pn=Merchant&am={last_amt}&cu=INR&tn={last_item}"
 st.markdown("f" **Quick Pay Last Item ({last_item} - ₹{int(last_amt)}):** [Open UPI App])
 ({upi_link})")