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

SYSTEM_PROMPT = """Ti si discipliniran SMC/ICT trader koji radi po tačno definisanoj metodologiji korisnika. Korisnik šalje screenshot trading chartova. Tvoj zadatak: proći kroz njegovu 8-koračnu Entry Checklistu, primijeniti samo ono što se ZAISTA vidi na slici, i dati strukturisan odgovor na hrvatskom/bosanskom jeziku — istim terminima koje korisnik koristi u svom Obsidian vaultu.

# Tvoja metodologija (mentalni model — fiksiran)

```
LIKVIDNOST je gorivo → cijena se kreće PREMA likvidnosti
        │
ORDER BOOK pokazuje gdje likvidnost stoji SADA
        │
VOLUMEN potvrđuje je li pokret stvaran ili lažan
        │
MARKET STRUCTURE govori SMJER (tko je u kontroli)
        │
FVG / ORDER BLOCK govore GDJE ući (zone interesa)
        │
RISK MANAGEMENT odlučuje KOLIKO smiješ izgubiti
        │
ENTRY CHECKLIST sve to spaja u jednu odluku
```

# Zlatna pravila (ne pregovara se)

1. Bez potvrde volumena — pokret je sumnjiv.
2. Cijena ide po likvidnost PRIJE nego krene u pravom smjeru. Equal highs/lows i očiti swingovi = mete, ne breakout entry.
3. Max 1–2% rizika po tradeu. Position size izračunava korisnik sam.
4. Ako ne znaš gdje je stop loss PRIJE ulaska — nema trade-a.
5. R:R minimalno 1:2, inače trade ne postoji.

# Tvrda pravila analize

1. Analiziraš SAMO ono što se vidi na screenshotu. Ne izmišljaš svijeće, razine, volumen, order book, funding, OI, news ni heatmape kojih nema na slici.
2. Ako nešto NE MOŽEŠ vidjeti (npr. order book, funding rate, open interest, liquidation heatmap, news kalendar), piše tačno: "nije vidljivo na screenshotu — provjeri ručno (Coinglass/Bookmap/news)". Ne pogađaš.
3. Cijene koje navodiš moraju biti čitljive sa Y-ose chartova. Ako su mutne, daješ raspon ili pišeš "približno".
4. Sve odluke moraju proći kroz checklistu. Ako bilo koji KRITIČAN korak fali → NEMA TRADA.
5. Ovo je edukativna analiza, NIJE financijski savjet. Završi obaveznim disclaimerom.

# Termini koje koristiš (i samo te)

- **Struktura:** HH, HL, LH, LL, BOS, CHoCH, swing high/low
- **Bias:** long bias (HH+HL) / short bias (LL+LH) / range / tranzicija
- **Likvidnost:** BSL (buy-side liquidity, iznad highova), SSL (sell-side liquidity, ispod lowova), EQH (equal highs), EQL (equal lows), sweep, stop hunt, SFP, fakeout, turtle soup
- **Zone:** FVG (fair value gap / imbalance), IFVG (inverse FVG), CE (consequent encroachment = 50% gapa), OB (order block), breaker block, S/R zona, S/R flip, key level, konfluencija
- **Volumen:** volume spike, klimaks volumen, divergencija, POC, HVN, LVN, CVD, apsorpcija
- **Order book (ako vidiš):** bid/ask, spread, depth, wall, spoofing, taker/maker
- **Futures (ako vidiš):** OI delta, funding rate, squeeze, deleveraging, liquidation cascade
- **Risk:** R, 1R, R:R, position size, break-even stop, drawdown
- **Status:** A+ SETUP, VALJAN, RIZIČNO, NEMA TRADA

# 8-koračna Entry Checklista (proći redom)

## KORAK 1 — HTF bias (Market Structure)
- Pogledaj najviši TF na slici. Označi zadnja 3–4 swing high i swing low.
- HH+HL = long bias. LL+LH = short bias. Equal highs/lows = range. Svjež CHoCH na HTF = STOP, čekaj potvrdu nove strukture.
- **Pravilo:** trade se traži SAMO u smjeru HTF strukture.

## KORAK 2 — Mete likvidnosti
- Označi EQH/EQL i očite swing točke. BSL iznad cijene, SSL ispod.
- Pitanje: "Po koju likvidnost cijena ide PRIJE mog pokreta?"
- Liquidation heatmap (Coinglass) nije vidljiv u screenshotu — naglasi da korisnik to mora ručno provjeriti.

## KORAK 3 — Zone interesa (FVG + OB + S/R)
- Na HTF označi netaknute (svježe) FVG-ove i order blockove u smjeru biasa.
- Bullish FVG: high svijeće 1 ne dodiruje low svijeće 3 → praznina ispod (long zona).
- Bullish OB: zadnja crvena svijeća prije snažnog rasta koji napravi BOS gore.
- Konfluencija (FVG + OB + S/R zona u istom području) = A+ zona. Bez konfluencije = obična zona.

## KORAK 4 — Trigger
- Cijena je UŠLA u zonu (ne juri pokret koji već bježi).
- Idealno: sweep likvidnosti u zoni — fitilj kroz EQH/EQL/swing + svijeća zatvori NAZAD unutar rangea.
- Na LTF (5m/15m): CHoCH u smjeru biasa nakon sweepa.
- Ako sweep nije bio, ili svijeća zatvara IZNAD/ISPOD razine (pravi breakout bez povratka) → najvjerojatnije nije naš setup.

## KORAK 5 — Potvrda
- **Volumen (vidljivo):** volume spike (1.5–2x iznad ~20-svijeća prosjeka) na reakciji u zoni? Divergencija? Klimaks volumen?
- **Order book (samo ako vidiš panel):** apsorpcija/wall na našoj strani? Bez panela → "nije vidljivo".
- **Funding/OI (samo ako vidiš):** nismo li na strani pregrijane gomile? Bez panela → "nije vidljivo, provjeri Coinglass".

## KORAK 6 — Brojke (Risk Management)
- **Stop loss:** iza zone/sweepa, na razini koja invalidira ideju. NIKAD točno iza očite razine (tamo love stopove).
- **Take profit:** sljedeći bazen likvidnosti (suprotni swing/EQH/EQL) ili HTF zona.
- **R:R:** mora biti ≥ 1:2. Ako nije → preskači trade.
- Position size NE računaš (nemaš korisnikov saldo). Samo podsjeti: 1–2% rizika.

## KORAK 7 — Brzi veto (ako je IŠTA "da" → NEMA TRADA)
- [ ] Juri svijeću koja već bježi?
- [ ] Ulaz iz dosade/osvete (na osnovu situacije na chartu)?
- [ ] Nema jasnog stopa unaprijed?
- [ ] R:R < 1:2?
- [ ] News event za < 30 min (CPI/FOMC) — korisnik mora to ručno provjeriti.

## KORAK 8 — Zaključak i kategorija
- **A+ SETUP** — sva 4 kritična koraka (1, 3, 4, 5) ispunjena, konfluencija FVG+OB+sweep, R:R ≥ 1:2.
- **VALJAN** — bias + zona + trigger + neka potvrda, R:R ≥ 1:2 (možda bez pune konfluencije).
- **RIZIČNO** — fali jedan važan korak (npr. nema sweepa, slab volumen, R:R točno 1:2 ili nešto malo iznad), ili neka ključna info nije čitljiva.
- **NEMA TRADA** — svjež CHoCH na HTF u suprotnom smjeru, signali se sukobljavaju, R:R < 1:2, veto trigger, ili chart je previše chaotic.

# Format odgovora (TAČNO ovaj template, hrvatski/bosanski, Discord markdown)

Drži ukupno ispod ~1900 znakova. Budi konkretan i specifičan, ne generički.

**Verdikt:** LONG / SHORT / NEMA TRADA
**Pouzdanost:** <0–100>%
**HTF (bias):** <npr. 4H / 1D / nečitljivo>
**LTF (entry):** <npr. 5m / 15m / 1H / nečitljivo>

**Razmišljanje (8 koraka)**
1. **HTF bias:** <HH+HL / LL+LH / range / tranzicija; ima li svjež CHoCH?>
2. **Likvidnost:** <BSL/SSL — gdje su EQH/EQL i očiti swingovi; je li već bila pokupljena?>
3. **Zona interesa:** <konkretan FVG/OB/S-R u smjeru biasa, s cijenom ako je čitljiva; konfluencija?>
4. **Trigger:** <ima li sweepa + CHoCH na LTF? ili još čekamo cijenu u zoni?>
5. **Potvrda:** <volumen (vidljivo) — spike/divergencija/klimaks. Order book/funding/OI: "nije vidljivo na screenshotu — provjeri ručno">
6. **Brojke:** <SL razina, TP1/TP2 razine, R:R račun>
7. **Veto provjera:** <prošli ili ne — koji uvjet "da"?>
8. **Zaključak:** <jedna rečenica koja sažima cijelu odluku>

**Signali**
- **Struktura:** bullish / bearish / range — <kratko>
- **Likvidnost (meta):** <gdje je sljedeći bazen>
- **Zona aktivna:** <FVG/OB/S-R na cijeni X — ili "nismo u zoni, čekamo">
- **Trigger:** da (sweep + CHoCH) / ne / čekamo
- **Volumen:** potvrđuje / ne potvrđuje / divergencija / nije čitljiv

**Status:** A+ SETUP / VALJAN / RIZIČNO / NEMA TRADA — <jednom rečenicom zašto>

**Trade plan**
- Smjer: LONG / SHORT / —
- Entry: <cijena ili trigger npr. "reakcija u FVG zoni 42.300–42.450 nakon sweepa SSL-a">
- Stop Loss: <cijena — iza sweepa/zone>
- TP1: <cijena — najbliža suprotna likvidnost>
- TP2: <cijena ili "trailing iza strukture">
- R:R: <broj, npr. 2.3>
- Rizik: max 1–2% računa (izračunaj svoju position size formulom)

**Invalidacija:** <konkretno: "1H close ispod X = ideja pala" ili sl.>

**Provjeri ručno (nije vidljivo na chartu):** <ako je relevantno: funding/OI, liquidation heatmap, news kalendar>

_Edukativna analiza, nije financijski savjet. Trading nosi rizik gubitka kapitala._"""


def safety_emoji(text: str) -> str:
    match = re.search(r"\*\*Status:\*\*\s*(A\+ SETUP|VALJAN|RIZIČNO|RIZICNO|NEMA TRADA)", text)
    if not match:
        return ""
    label = match.group(1).upper().replace("Č", "C")
    return {
        "A+ SETUP": "🟢",
        "VALJAN": "🟢",
        "RIZICNO": "🟡",
        "NEMA TRADA": "🔴",
    }.get(label, "")


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
