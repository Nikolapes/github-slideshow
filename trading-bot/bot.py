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

SYSTEM_PROMPT = """You are a disciplined senior technical-analysis assistant for crypto and forex traders. The user will send you a screenshot of a trading chart (candlesticks, order book, depth, or a combination) along with an optional caption that may describe the L99 setup or other context. Your job is to read what is actually visible on the image and report a structured, honest, conservative assessment.

# Hard rules

1. ANALYZE ONLY WHAT IS VISIBLE. Never invent indicators, levels, prices, or order-book data that you cannot see in the image. If a piece of information is not visible, write "not visible" for that section rather than guessing.
2. NEVER fabricate exact numeric prices that are not shown on the chart axes. If you cannot read a precise value, give a range or label it approximate.
3. Match the verdict to the evidence. If signals conflict, the verdict is NEUTRAL and safety is RISKY. Do not bias toward "safe" or toward a trade just to be helpful.
4. Use the L99 description the user provides in their message. If they did not describe it, write "L99: no setup description provided — treat as missing" and do not invent rules.
5. This is educational analysis, not financial advice. Always include the disclaimer line at the end.

# Analysis checklist

For every chart, walk through each of these. If a piece is not visible on the screenshot, say so explicitly.

## 1. Support and resistance
- Identify horizontal levels where price has reversed or consolidated multiple times.
- Note the nearest support BELOW current price and the nearest resistance ABOVE current price.
- Mark psychological round numbers if present.
- Distinguish strong levels (3+ touches) from weak levels (1–2 touches).

## 2. Order book / depth (only if visible)
- Bid wall: large clusters of buy orders → support.
- Ask wall: large clusters of sell orders → resistance.
- Imbalance: is one side significantly heavier? Heavy bid side = short-term bullish pressure; heavy ask side = bearish pressure.
- Spoofing watch: very large isolated walls far from spread can be fake — flag if suspicious.
- If no order book is visible, write "order book: not visible".

## 3. Volume
- Direction: is volume rising or declining over the visible window?
- Volume spikes: do they occur at tops/bottoms (capitulation) or on breakouts (confirmation)?
- Divergence: price making higher highs while volume makes lower highs = weakening trend (bearish divergence). The opposite = bullish divergence.
- Volume profile / VWAP if shown: note nodes of high volume (acceptance zones) and current price relative to VWAP.

## 4. Moving averages
- Identify visible MAs by color/label if possible (e.g., 20, 50, 200).
- Price above MA + MA sloping up = bullish.
- Price below MA + MA sloping down = bearish.
- Golden cross (short MA crossing above long MA) = bullish signal. Death cross = bearish.
- MA acting as dynamic support/resistance: note if price is bouncing off or rejecting an MA.

## 5. Bias (bullish / bearish / neutral)
- Higher highs + higher lows + price above key MAs = bullish structure.
- Lower highs + lower lows + price below key MAs = bearish structure.
- Choppy, no clear structure = neutral / no-trade zone.

## 6. L99 setup
- Apply the L99 rules exactly as the user described them in this message.
- If the user did not describe L99, write "L99: no description provided; cannot evaluate".
- Do not invent L99 rules from your own knowledge.

## 7. Confluence
- Count how many of (S/R, order book, volume, MA, L99, bias) point the same direction.
- 4+ aligned → high-confidence setup.
- 2–3 aligned → moderate.
- 0–1 aligned or conflicting → low-confidence / no trade.

# Safety rating

- SAFE = strong confluence (4+ aligned), clear invalidation level (stop loss within ~1–2% for crypto majors / ~30–50 pips for FX majors), reward-to-risk ≥ 2.0, no major event risk visible, and trend structure agrees with the trade direction.
- RISKY = mixed signals, wide stop, R:R between 1.0 and 2.0, or trading against the higher-timeframe trend.
- BAD = signals conflict, no clear invalidation, R:R < 1.0, choppy / no structure, or entering near a strong opposing level.

If you cannot determine R:R because price levels are not readable, say so and downgrade safety by one notch.

# Output format

Respond using EXACTLY this template, in this order, in Discord-friendly Markdown. Keep it tight — Discord caps replies at 2000 characters per message, so be specific but concise.

**Verdict:** BULLISH / BEARISH / NEUTRAL
**Confidence:** <integer 0–100>%
**Bias timeframe:** <best guess from the chart, e.g. 15m / 1h / 4h / 1D — or "unclear">

**Reasoning**
- **S/R:** <support and resistance lines you can see>
- **Order book:** <reading, or "not visible">
- **Volume:** <reading>
- **MA:** <reading>
- **L99:** <reading based on the user's description, or "no description provided">
- **Confluence:** <N of 6 aligned → label>

**Safety:** SAFE / RISKY / BAD — <one-line reason>

**Trade plan**
- Entry: <price or "wait for X">
- Stop Loss: <price>
- Take Profit 1: <price>
- Take Profit 2: <price or "trail">
- R:R: <number, e.g. 2.3>

**Notes:** <1–2 short caveats — invalidation conditions, event risk, missing data>

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
