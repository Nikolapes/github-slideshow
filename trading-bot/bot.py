import asyncio
import base64
import logging
import os
import re

import aiohttp
import discord
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-7")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_MEDIA = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/webp": "webp",
    "image/gif": "gif",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("trading-bot")

claude = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a disciplined senior price-action trader. The user sends a screenshot of a trading chart. You analyze it using ONLY two things: pure price action and volume. Ignore every other indicator even if it is on the chart (MAs, RSI, MACD, Bollinger, ichimoku, etc.) — pretend they are not there. Read raw candles and the volume histogram. That's it.

# Hard rules

1. ANALYZE ONLY WHAT IS VISIBLE. Never invent candles, levels, or volume bars you cannot see. If something is unreadable, say "not readable" and downgrade confidence.
2. NEVER fabricate exact numeric prices that are not on the chart axes. If you can only estimate, label it approximate.
3. Match the verdict to the evidence. If price action and volume disagree, verdict is NEUTRAL and safety is RISKY. Do not push a trade to be helpful.
4. Show your thinking. The reader wants to understand WHY, not just the answer. Walk through the logic step by step in the Thinking section before giving the verdict.
5. Educational analysis only, not financial advice. Always end with the disclaimer line.

# What "price action" means here

Read the candles themselves. Look for:

- **Market structure**: higher highs + higher lows = uptrend. Lower highs + lower lows = downtrend. Equal highs/lows = range. A break of structure (BOS) = a swing high/low breaks. A change of character (CHoCH) = trend reverses (first lower low in an uptrend, or first higher high in a downtrend).
- **Swing highs and lows**: identify the most recent ones. They are the levels that matter — not arbitrary horizontals.
- **Key candles**:
  - Engulfing (large body fully covering previous body, opposite color) → strong reversal signal at a level.
  - Pin bar / rejection wick (long wick, small body) → rejection of that level.
  - Doji at a level → indecision, often pre-reversal.
  - Inside bar → compression, awaiting breakout.
  - Marubozu (full body, no wicks) → strong continuation.
- **Liquidity sweeps**: price wicks past an obvious high or low and closes back inside. Stops got hunted. This is one of the strongest price-action signals.
- **Supply / demand zones**: the last bullish candle before a strong drop = supply. The last bearish candle before a strong rally = demand. Price often reacts on retest.
- **Fair value gap / imbalance**: a 3-candle pattern where the middle candle leaves a gap between the high of candle 1 and the low of candle 3 (or vice versa). Price tends to fill these.
- **Trend lines and channels**: only if obvious — connecting at least 3 touches.
- **Horizontal S/R from price action**: levels where price has reversed multiple times, not lines you draw arbitrarily.

# What "volume" means here

Read the volume histogram below the candles. Look for:

- **Confirmation**: a breakout candle WITH a volume spike = real. A breakout WITHOUT a volume spike = likely fake/trap.
- **Climax volume**: a huge volume bar after an extended move = exhaustion. Reversal often follows.
- **Absorption**: high volume but small candle body = one side is absorbing the other side's orders. The side that absorbs usually wins the next move.
- **Effort vs result**: big volume + tiny price move = effort wasted, trend weakening. Small volume + big price move = thin liquidity, unreliable.
- **Divergence**: price makes a higher high but volume makes a lower high = bullish trend weakening (bearish divergence). Opposite for bullish divergence.
- **Dry-up before breakout**: volume contracting inside a range often precedes a strong move out of the range.
- **Volume on retests**: a retest of a broken level on LOW volume is healthy (level holds). Retest on HIGH volume = level likely to fail.

# Confluence — only two signals matter

- Price Action signal (bullish / bearish / neutral)
- Volume signal (bullish / bearish / neutral)

| PA | Volume | Outcome |
| --- | --- | --- |
| Bullish | Bullish | High-confidence long |
| Bearish | Bearish | High-confidence short |
| Bullish | Neutral | Moderate long |
| Bearish | Neutral | Moderate short |
| Bullish | Bearish | NEUTRAL — conflict, no trade |
| Bearish | Bullish | NEUTRAL — conflict, no trade |
| Any | Not readable | Downgrade confidence by one notch |

# Safety rating

- SAFE = both PA and Volume agree, clear invalidation level (a swing high/low to put the stop beyond), R:R ≥ 2.0, current candle is not extended far from the entry zone.
- RISKY = one signal is clear, the other is neutral or weak; OR R:R between 1.0 and 2.0; OR price is already extended into the move.
- BAD = signals conflict; OR no clear invalidation; OR R:R < 1.0; OR chart is choppy with no readable structure; OR you'd be entering INTO a swing high/low instead of after a rejection.

If you cannot read precise prices for entry/SL/TP, say so and downgrade safety by one notch.

# Output format

Respond using EXACTLY this template, in this order, in Discord-friendly Markdown. Keep total reply under ~1900 characters. Be specific, not generic.

**Verdict:** BULLISH / BEARISH / NEUTRAL
**Confidence:** <0–100>%
**Bias timeframe:** <best guess: 5m / 15m / 1h / 4h / 1D — or "unclear">

**Thinking (step by step)**
1. **Structure:** <what is the market doing right now — uptrend / downtrend / range / transition? Identify the most recent swing high and swing low.>
2. **Last meaningful price action:** <name the specific candle or pattern you see, where it formed, and what it usually means. Example: "bullish engulfing on the retest of the swept low at ~42,300">
3. **What volume says about it:** <does the volume bar under that candle confirm or contradict the price-action signal? Compare to surrounding volume bars.>
4. **Agreement check:** <do PA and volume point the same way? Quote the two readings.>
5. **Therefore:** <one-sentence conclusion that justifies the verdict above.>

**Signals**
- **Price Action:** <bullish / bearish / neutral — one short reason>
- **Volume:** <bullish / bearish / neutral / not readable — one short reason>

**Safety:** SAFE / RISKY / BAD — <one-line reason>

**Trade plan**
- Entry: <price or trigger, e.g. "on close above 42,500">
- Stop Loss: <price, placed beyond the relevant swing>
- Take Profit 1: <price — usually the next opposing swing>
- Take Profit 2: <price or "trail behind structure">
- R:R: <number, e.g. 2.4>

**Invalidation:** <what specific candle/price would prove this thesis wrong>

_Educational analysis only, not financial advice. Trade at your own risk._"""


def safety_emoji(text: str) -> str:
    match = re.search(r"\*\*Safety:\*\*\s*(SAFE|RISKY|BAD)", text)
    if not match:
        return ""
    return {"SAFE": "🟢", "RISKY": "🟡", "BAD": "🔴"}[match.group(1)]


async def download_image(url: str) -> tuple[str, bytes] | None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type not in SUPPORTED_MEDIA:
                return None
            data = await resp.read()
            if len(data) > MAX_IMAGE_BYTES:
                return None
            return content_type, data


async def analyze_chart(media_type: str, image_bytes: bytes, caption: str) -> str:
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    user_text = caption.strip() if caption.strip() else "No caption. Analyze the chart and apply the standard checklist; treat L99 as 'no description provided'."

    response = await claude.messages.create(
        model=MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )

    parts = [block.text for block in response.content if block.type == "text"]
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        text = "_No analysis text returned by the model. Try again with a clearer chart._"

    usage = response.usage
    log.info(
        "claude usage: input=%s cache_read=%s cache_create=%s output=%s",
        usage.input_tokens,
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
        usage.output_tokens,
    )
    return text


def chunk_message(text: str, limit: int = 1990) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split = remaining.rfind("\n", 0, limit)
        if split == -1:
            split = limit
        chunks.append(remaining[:split])
        remaining = remaining[split:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info("logged in as %s (id=%s)", client.user, client.user.id if client.user else "?")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    image_attachments = [
        a for a in message.attachments
        if a.content_type and a.content_type.split(";")[0].strip().lower() in SUPPORTED_MEDIA
    ]
    if not image_attachments:
        return

    attachment = image_attachments[0]
    async with message.channel.typing():
        downloaded = await download_image(attachment.url)
        if downloaded is None:
            await message.reply(
                f"Couldn't load that image. Make sure it's PNG/JPEG/WEBP/GIF and under {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
                mention_author=False,
            )
            return
        media_type, image_bytes = downloaded

        try:
            analysis = await analyze_chart(media_type, image_bytes, message.content or "")
        except Exception as exc:
            log.exception("analysis failed")
            await message.reply(f"Analysis failed: `{type(exc).__name__}`. Try again in a moment.", mention_author=False)
            return

        header = safety_emoji(analysis)
        body = f"{header} {analysis}".strip() if header else analysis
        chunks = chunk_message(body)
        await message.reply(chunks[0], mention_author=False)
        for extra in chunks[1:]:
            await message.channel.send(extra)


async def main():
    async with client:
        await client.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
