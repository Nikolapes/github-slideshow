# Trading Chart Discord Bot

Drop a chart screenshot into a Discord channel where the bot is online. The bot analyzes it with Claude vision and replies with: verdict, per-indicator reasoning (S/R, order book, volume, MA, L99, bias), a SAFE / RISKY / BAD rating, and a trade plan (entry, SL, TP, R:R).

You describe the L99 setup in the message caption — the bot uses your description rather than guessing what L99 means.

## Setup

### 1. Create a Discord application and bot

1. Go to <https://discord.com/developers/applications> → **New Application**.
2. Open the **Bot** tab → **Reset Token** → copy the token.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**. Required, or the bot will not see attachments.
4. Under **OAuth2 → URL Generator**, pick scopes `bot` and `applications.commands`, then in **Bot Permissions** enable: `Read Messages/View Channels`, `Send Messages`, `Read Message History`, `Attach Files`. Open the generated URL to invite the bot to your server.

### 2. Get an Anthropic API key

Go to <https://console.anthropic.com/> → **API Keys** → create a key.

### 3. Install and run

```bash
cd trading-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in DISCORD_TOKEN and ANTHROPIC_API_KEY
python bot.py
```

The bot logs `logged in as <name>` when it is ready. Drop a chart image into any channel the bot can see.

## How to use

- Attach a chart screenshot (PNG, JPEG, WEBP, or GIF; ≤ 5 MB).
- In the message text, describe the L99 setup if it applies (e.g. *"L99: sweep of yesterday low + reclaim with bullish engulfing"*). If you do not describe L99, the bot will report `L99: no description provided` instead of inventing rules.
- Reply comes back in the same channel.

## Output format

```
🟢 **Verdict:** BULLISH
**Confidence:** 72%
**Bias timeframe:** 1h

**Reasoning**
- **S/R:** ...
- **Order book:** ...
- **Volume:** ...
- **MA:** ...
- **L99:** ...
- **Confluence:** 4 of 6 aligned → moderate-high

**Safety:** SAFE — clear invalidation, R:R 2.4

**Trade plan**
- Entry: ...
- Stop Loss: ...
- Take Profit 1: ...
- Take Profit 2: ...
- R:R: 2.4

**Notes:** ...

_Educational analysis only, not financial advice._
```

## Notes

- The bot only analyzes what is visible in the screenshot. If order-book data, volume, or MAs are not on the chart, it says "not visible" rather than guessing.
- The system prompt is sent with `cache_control: ephemeral` so repeat calls reuse the cached prefix (~0.1× input cost on hits). Check the logs — `cache_read=...` shows the cache hits.
- Adaptive thinking is enabled, so the model decides how much to reason per chart.
- This is not financial advice.
