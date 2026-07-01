"""TradingView alert webhook prijemnik.

TradingView nema javni API za čitanje podataka — ali može SLATI webhook
kad se tvoj alert okine. Ovaj server prima te alerte, upisuje ih u
tv_alerts.json i (opcionalno) prosljeđuje u Discord kanal.

Postavka na TradingView strani (treba plaćeni plan — Essential ili viši):
  1. Otvori chart → Alert (zvonce) → uvjet po želji (npr. cijena probije dno).
  2. U "Notifications" uključi "Webhook URL" i upiši:
       http://TVOJA-JAVNA-ADRESA:8080/webhook
  3. U "Message" polje zalijepi JSON (TradingView sam popuni {{...}}):
       {"secret": "TVOJ_SECRET", "symbol": "{{ticker}}",
        "price": "{{close}}", "timeframe": "{{interval}}",
        "message": "sweep dna — provjeri stopping volume"}

Server mora biti javno dostupan: VPS, port-forward na routeru, ili
Cloudflare Tunnel / ngrok ako si doma iza NAT-a.

Pokretanje:
  WEBHOOK_SECRET=nesto-tajno python tv_webhook.py
  # opcionalno: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
  # opcionalno: PORT=8080

Edukativni alat, nije financijski savjet.
"""

import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

PORT = int(os.environ.get("PORT", "8080"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
ALERTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tv_alerts.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("tv-webhook")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def append_alert(alert: dict):
    alerts = []
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE) as f:
            alerts = json.load(f)
    alerts.append(alert)
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)


async def forward_to_discord(alert: dict):
    if not DISCORD_WEBHOOK_URL:
        return
    content = (
        f"📡 **TradingView alert** — {alert.get('symbol', '?')} "
        f"({alert.get('timeframe', '?')})\n"
        f"Cijena: `{alert.get('price', '?')}`\n"
        f"{alert.get('message', '')}\n"
        f"_{alert['received_at']}_"
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(DISCORD_WEBHOOK_URL, json={"content": content}) as resp:
            if resp.status >= 300:
                log.warning("Discord forward failed: %s", resp.status)


async def handle_webhook(request: web.Request) -> web.Response:
    try:
        # TradingView šalje body kao text — probaj JSON, fallback na plain text
        raw = await request.text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"message": raw}

        # secret iz JSON-a ili query stringa (TradingView ne može slati headere)
        supplied = data.get("secret") or request.query.get("secret") or ""
        if not SECRET or supplied != SECRET:
            log.warning("odbijen alert — pogrešan ili nedostajući secret")
            return web.Response(status=403, text="forbidden")

        data.pop("secret", None)
        alert = {**data, "received_at": utcnow()}
        append_alert(alert)
        log.info("alert: %s @ %s — %s",
                 alert.get("symbol", "?"), alert.get("price", "?"),
                 alert.get("message", ""))
        await forward_to_discord(alert)
        return web.Response(text="ok")
    except Exception:
        log.exception("greška u obradi alerta")
        return web.Response(status=500, text="error")


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="tv-webhook up")


def main():
    if not SECRET:
        raise SystemExit("Postavi WEBHOOK_SECRET env varijablu (bilo koji tajni string) pa pokreni ponovo.")
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", handle_health)
    log.info("slušam na 0.0.0.0:%s /webhook (alerti → %s%s)",
             PORT, ALERTS_FILE, ", + Discord" if DISCORD_WEBHOOK_URL else "")
    web.run_app(app, port=PORT)


if __name__ == "__main__":
    main()
