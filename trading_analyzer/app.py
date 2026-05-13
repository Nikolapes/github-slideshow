import streamlit as st
import anthropic
import base64
from pathlib import Path
from PIL import Image
import io

st.set_page_config(
    page_title="Trading Chart Analyzer",
    page_icon="📊",
    layout="wide",
)

SYSTEM_PROMPT = """You are an elite professional trading analyst with 20+ years of experience in technical analysis.
Your job is to analyze trading charts with extreme precision and provide a clear verdict.

When analyzing a chart image, you MUST evaluate these 4 key components and provide your analysis in exactly this structure:

## 1. SUPPORT & RESISTANCE
- Identify ALL visible support levels (price floors where buying pressure emerges)
- Identify ALL visible resistance levels (price ceilings where selling pressure emerges)
- Note if price is currently near a key S/R level
- State if S/R levels suggest a bullish or bearish bias

## 2. ORDER BOOK / PRICE ACTION
- Analyze visible bid/ask walls if order book data is shown
- Read the candlestick patterns (doji, hammer, engulfing, etc.)
- Identify any significant price clusters or gaps
- Note buying vs selling pressure from price action

## 3. VOLUME ANALYSIS
- Is volume increasing or decreasing?
- Does volume confirm the current trend direction?
- Are there any volume spikes that signal reversals or continuations?
- Is this high volume or low volume relative to recent bars?

## 4. MOVING AVERAGES (MA)
- Identify which MAs are visible (MA9, MA20, MA50, MA100, MA200, etc.)
- State clearly: is the trend BEARISH or BULLISH based on MA positioning?
- Are MAs acting as support or resistance?
- Any MA crossovers visible or imminent?

---

## MY THINKING ABOUT THIS TRADE

Provide 3-5 sentences of your honest professional assessment combining all 4 factors above.
Be direct. No sugarcoating. Tell them exactly what the chart is saying.

---

## VERDICT

State ONE of these two verdicts in large bold text:
**SAFE TO TRADE** - if the confluence of signals is favorable
**BAD ENTRY - AVOID** - if the signals are conflicting, risky, or clearly bearish

Then give a 1-2 sentence explanation of why.

---

IMPORTANT RULES:
- If you cannot clearly see a component (e.g., no order book data visible), say "Not visible in chart" for that section
- Never be vague. Give specific price levels when visible
- Always give a definitive SAFE or BAD verdict - never "maybe" or "it depends"
- Your analysis should take the perspective of a swing or day trader looking to enter a position now"""

def encode_image(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")

def get_image_media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return types.get(ext, "image/jpeg")

def analyze_chart(image_bytes: bytes, media_type: str, user_notes: str = "") -> str:
    client = anthropic.Anthropic()

    user_message = "Analyze this trading chart for me."
    if user_notes.strip():
        user_message = f"Analyze this trading chart for me. Additional context from trader: {user_notes.strip()}"

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": encode_image(image_bytes),
                        },
                    },
                    {
                        "type": "text",
                        "text": user_message,
                    },
                ],
            }
        ],
    ) as stream:
        return stream.get_final_message()


# ─── UI Layout ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00ff88, #00ccff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .verdict-safe {
        background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%);
        color: #000;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        font-size: 1.8rem;
        font-weight: 900;
        text-align: center;
        letter-spacing: 2px;
        box-shadow: 0 4px 20px rgba(0, 255, 136, 0.4);
        margin: 1rem 0;
    }
    .verdict-bad {
        background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
        color: #fff;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        font-size: 1.8rem;
        font-weight: 900;
        text-align: center;
        letter-spacing: 2px;
        box-shadow: 0 4px 20px rgba(255, 68, 68, 0.4);
        margin: 1rem 0;
    }
    .analysis-box {
        background: #1a1a2e;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 0.5rem 0;
    }
    .stButton button {
        background: linear-gradient(135deg, #00ff88, #00ccff);
        color: #000;
        font-weight: 800;
        font-size: 1.1rem;
        padding: 0.75rem 2rem;
        border: none;
        border-radius: 8px;
        width: 100%;
        letter-spacing: 1px;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 255, 136, 0.3);
    }
    .info-badge {
        display: inline-block;
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 0.3rem 0.7rem;
        font-size: 0.8rem;
        color: #8b949e;
        margin: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">Trading Chart Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Upload your chart → Get instant AI analysis: Safe or Bad entry</div>', unsafe_allow_html=True)

col_badges = st.columns(4)
with col_badges[0]:
    st.markdown('<span class="info-badge">Support & Resistance</span>', unsafe_allow_html=True)
with col_badges[1]:
    st.markdown('<span class="info-badge">Order Book Reading</span>', unsafe_allow_html=True)
with col_badges[2]:
    st.markdown('<span class="info-badge">Volume Analysis</span>', unsafe_allow_html=True)
with col_badges[3]:
    st.markdown('<span class="info-badge">MA Bearish/Bullish</span>', unsafe_allow_html=True)

st.divider()

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown("### Upload Chart")
    uploaded_file = st.file_uploader(
        "Drop your trading chart here",
        type=["jpg", "jpeg", "png", "webp", "gif"],
        help="Screenshots from any trading platform work: TradingView, Binance, MT4/MT5, etc.",
    )

    user_notes = st.text_area(
        "Any context you want to add? (optional)",
        placeholder="e.g., 'BTC/USDT 4H chart', 'Looking to long', 'Key news event today'...",
        height=80,
    )

    analyze_btn = st.button("ANALYZE THIS CHART", disabled=uploaded_file is None)

    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Your chart", use_container_width=True)

with col_right:
    st.markdown("### Analysis")

    if not uploaded_file:
        st.info("Upload a chart image on the left to begin analysis.")
        st.markdown("""
        **What this tool reads:**
        - **Support & Resistance** — Key price levels where reversals happen
        - **Order Book** — Bid/ask walls, buying vs selling pressure
        - **Volume** — Confirms or denies the current trend direction
        - **Moving Averages** — MA positioning to determine bullish/bearish bias

        **Verdict:**
        - **SAFE TO TRADE** — Confluence of signals is favorable
        - **BAD ENTRY - AVOID** — Signals are conflicting or bearish
        """)

    if analyze_btn and uploaded_file:
        uploaded_file.seek(0)
        image_bytes = uploaded_file.read()
        media_type = get_image_media_type(uploaded_file.name)

        with st.spinner("Analyzing your chart with AI..."):
            try:
                response = analyze_chart(image_bytes, media_type, user_notes)

                # Extract text content from response
                full_text = ""
                for block in response.content:
                    if block.type == "text":
                        full_text = block.text
                        break

                # Detect verdict to style accordingly
                text_upper = full_text.upper()
                if "SAFE TO TRADE" in text_upper:
                    st.markdown('<div class="verdict-safe">SAFE TO TRADE</div>', unsafe_allow_html=True)
                elif "BAD ENTRY" in text_upper or "AVOID" in text_upper:
                    st.markdown('<div class="verdict-bad">BAD ENTRY — AVOID</div>', unsafe_allow_html=True)

                # Display full analysis
                st.markdown("---")
                st.markdown(full_text)

                # Token usage in expander
                with st.expander("Analysis metadata"):
                    usage = response.usage
                    st.write(f"Input tokens: {usage.input_tokens}")
                    st.write(f"Output tokens: {usage.output_tokens}")
                    if hasattr(usage, 'cache_read_input_tokens'):
                        st.write(f"Cache read tokens: {usage.cache_read_input_tokens}")

            except anthropic.APIError as e:
                st.error(f"API Error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")
                raise
