"""VPA-Liquidity Sweep skener (long-only, ICT/VPA stil).

Detektira setup iz playbooka VPA-Liquidity-Sweep.md:
  1. HTF (1h/4h): očito dno — klaster swing lowova (equal lows) s više odbijanja
  2. Sweep: cijena probije ISPOD dna fitiljem pa se vrati unutar rangea
  3. LTF (15m): stopping-volume hammer — donji fitilj >= 2x tijela,
     close u gornjoj polovici, volumen >= 2x prosjeka 20 svijeća
  4. Brojke: SL ispod fitilja hammera, TP na prvim equal highs, R:R >= 2

NE TREBA TI RAČUN NI API KLJUČ ni na jednoj burzi za skeniranje:
čitaju se JAVNI podaci o cijenama — iste svijeće koje TradingView crta.
EXCHANGE env varijabla bira izvor podataka (default binance; radi i
bybit, okx, kraken, coinbase... bilo koja ccxt burza) — to je samo
izvor javnih podataka, ne mjesto gdje imaš račun.

Modovi:
  python ict_scanner.py scan  BTC/USDT           # jedan prolaz, ispiši signal
  python ict_scanner.py watch BTC/USDT ETH/USDT  # petlja: skenira svakih 60 s
  python ict_scanner.py backtest BTC/USDT        # test na povijesnim podacima

Za TradingView integraciju (alerti s tvojih chartova) vidi tv_webhook.py.

Paper trading je DEFAULT. Journal ide u paper_trades.json.
Pravo izvršenje postoji samo kao eksplicitni opt-in:
  LIVE_TRADING=YES_I_UNDERSTAND + EXCHANGE_API_KEY + EXCHANGE_SECRET
Bez toga se nikad ne šalje nalog na burzu.

Edukativni alat, nije financijski savjet.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import ccxt

EXCHANGE_ID = os.environ.get("EXCHANGE", "binance")
HTF = os.environ.get("HTF_TIMEFRAME", "1h")
LTF = os.environ.get("LTF_TIMEFRAME", "15m")

# Parametri setupa (iz playbooka — mijenjaj ovdje, ne u logici)
EQUAL_LOW_TOLERANCE = 0.0015   # 0.15% — koliko blizu moraju biti lowovi da budu "equal"
MIN_LEVEL_TOUCHES = 2          # min odbijanja da dno bude "očito"
SWING_LOOKBACK = 2             # svijeća lijevo/desno za swing point
HTF_CANDLES = 300
LTF_CANDLES = 100
VOLUME_MULT = 2.0              # stopping volume >= 2x prosjeka
VOLUME_AVG_WINDOW = 20
WICK_BODY_RATIO = 2.0          # donji fitilj >= 2x tijela
MIN_RR = 2.0                   # R:R >= 1:2 obavezno
RISK_PCT = 0.01                # 1% računa po tradeu (paper)
PAPER_BALANCE_START = 10_000.0
JOURNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")


@dataclass
class Signal:
    symbol: str
    time: str
    level: float          # probijeno dno (support)
    sweep_low: float      # najniža točka sweepa
    entry: float          # close hammer svijeće
    stop: float           # ispod fitilja hammera
    target: float         # prve equal highs iznad
    rr: float
    hammer_volume_mult: float
    note: str


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch(exchange, symbol: str, timeframe: str, limit: int):
    """OHLCV -> lista [ts, open, high, low, close, volume]."""
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def swing_lows(candles, lookback=SWING_LOOKBACK):
    """Indeksi svijeća čiji je low niži od `lookback` susjeda s obje strane."""
    out = []
    for i in range(lookback, len(candles) - lookback):
        low = candles[i][3]
        if all(low <= candles[j][3] for j in range(i - lookback, i + lookback + 1)):
            out.append(i)
    return out


def swing_highs(candles, lookback=SWING_LOOKBACK):
    out = []
    for i in range(lookback, len(candles) - lookback):
        high = candles[i][2]
        if all(high >= candles[j][2] for j in range(i - lookback, i + lookback + 1)):
            out.append(i)
    return out


def find_liquidity_level(candles):
    """Nađi 'očito dno': klaster swing lowova unutar tolerancije (equal lows).

    Vraća (razina, broj_dodira) najnižeg klastera s dovoljno dodira, ili None.
    """
    lows = [(i, candles[i][3]) for i in swing_lows(candles)]
    best = None
    for i, base in lows:
        cluster = [l for _, l in lows if abs(l - base) / base <= EQUAL_LOW_TOLERANCE]
        if len(cluster) >= MIN_LEVEL_TOUCHES:
            level = min(cluster)
            if best is None or level < best[0]:
                best = (level, len(cluster))
    return best


def detect_sweep(candles, level: float):
    """Sweep = neka od zadnjih ~10 svijeća probila ISPOD razine fitiljem,
    a trenutna cijena je NAZAD IZNAD razine. Vraća (indeks, sweep_low) ili None."""
    recent = candles[-10:]
    current_close = candles[-1][4]
    if current_close <= level:
        return None  # još smo ispod — breakdown, ne sweep (ili sweep u toku)
    for offset, c in enumerate(recent):
        if c[3] < level:
            return (len(candles) - 10 + offset, c[3])
    return None


def is_stopping_volume_hammer(candle, volumes_before):
    """Hammer + ekstremni volumen. candle = [ts,o,h,l,c,v]."""
    _, o, h, l, c, v = candle[:6]
    body = abs(c - o)
    lower_wick = min(o, c) - l
    rng = h - l
    if rng <= 0 or body <= 0:
        return (False, 0.0)
    avg = sum(volumes_before[-VOLUME_AVG_WINDOW:]) / max(len(volumes_before[-VOLUME_AVG_WINDOW:]), 1)
    vol_mult = v / avg if avg > 0 else 0.0
    hammer = (
        lower_wick >= WICK_BODY_RATIO * body      # dugi donji fitilj
        and c >= l + rng * 0.5                    # close u gornjoj polovici
        and c > o                                 # zelena (kupci pobijedili)
    )
    return (hammer and vol_mult >= VOLUME_MULT, vol_mult)


def find_target(candles, entry: float):
    """TP = najbliži swing high (buy-side liquidity) iznad entryja."""
    highs = [candles[i][2] for i in swing_highs(candles) if candles[i][2] > entry]
    return min(highs) if highs else None


def scan_symbol(exchange, symbol: str):
    """Jedan puni prolaz kroz setup. Vraća Signal ili None + razlog."""
    htf = fetch(exchange, symbol, HTF, HTF_CANDLES)
    level_info = find_liquidity_level(htf)
    if not level_info:
        return None, "nema očitog dna (equal lows) na HTF"
    level, touches = level_info

    sweep = detect_sweep(htf, level)
    if not sweep:
        return None, f"dno na {level:.6g} ({touches} dodira) još nije sweepano"
    _, sweep_low = sweep

    ltf = fetch(exchange, symbol, LTF, LTF_CANDLES)
    # tražimo stopping-volume hammer u zadnjih 5 LTF svijeća (svježa potvrda)
    hammer = None
    for i in range(len(ltf) - 5, len(ltf)):
        ok, vol_mult = is_stopping_volume_hammer(ltf[i], [c[5] for c in ltf[:i]])
        if ok and ltf[i][3] <= level * (1 + EQUAL_LOW_TOLERANCE):
            hammer = (ltf[i], vol_mult)
    if not hammer:
        return None, f"sweep dna {level:.6g} se dogodio, ali nema stopping-volume hammera na {LTF}"
    hammer_candle, vol_mult = hammer

    entry = hammer_candle[4]
    stop = hammer_candle[3] * 0.999  # odmah ispod fitilja
    target = find_target(htf, entry)
    if target is None:
        return None, "nema equal highs / swing higha iznad za TP"

    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return None, "nevaljan SL (iznad entryja)"
    rr = reward / risk
    if rr < MIN_RR:
        return None, f"R:R {rr:.2f} < {MIN_RR} → preskačem (playbook pravilo)"

    return Signal(
        symbol=symbol,
        time=utcnow(),
        level=round(level, 8),
        sweep_low=round(sweep_low, 8),
        entry=round(entry, 8),
        stop=round(stop, 8),
        target=round(target, 8),
        rr=round(rr, 2),
        hammer_volume_mult=round(vol_mult, 2),
        note=f"sweep dna ({touches} dodira) + stopping volume {vol_mult:.1f}x na {LTF}",
    ), None


# ---------------------------------------------------------------- journal


def load_journal():
    if os.path.exists(JOURNAL):
        with open(JOURNAL) as f:
            return json.load(f)
    return {"balance": PAPER_BALANCE_START, "open": [], "closed": []}


def save_journal(j):
    with open(JOURNAL, "w") as f:
        json.dump(j, f, indent=2)


def paper_enter(journal, sig: Signal):
    """Upiši paper trade: size po formuli (račun × rizik%) / udaljenost stopa."""
    already = any(t["symbol"] == sig.symbol for t in journal["open"])
    if already:
        return False
    risk_amount = journal["balance"] * RISK_PCT
    stop_dist = (sig.entry - sig.stop) / sig.entry
    size_quote = risk_amount / stop_dist if stop_dist > 0 else 0
    journal["open"].append({**asdict(sig), "size_quote": round(size_quote, 2)})
    return True


def paper_update(journal, exchange):
    """Provjeri otvorene paper tradeove: SL ili TP pogođen?"""
    still_open = []
    for t in journal["open"]:
        ticker = exchange.fetch_ticker(t["symbol"])
        px = ticker["last"]
        result = None
        if px <= t["stop"]:
            result = ("SL", -journal["balance"] * RISK_PCT)
        elif px >= t["target"]:
            result = ("TP", journal["balance"] * RISK_PCT * t["rr"])
        if result:
            outcome, pnl = result
            journal["balance"] = round(journal["balance"] + pnl, 2)
            journal["closed"].append({**t, "outcome": outcome, "pnl": round(pnl, 2),
                                      "closed_at": utcnow()})
            print(f"[{utcnow()}] {t['symbol']} {outcome} pnl={pnl:+.2f} "
                  f"balance={journal['balance']:.2f}")
        else:
            still_open.append(t)
    journal["open"] = still_open


# ---------------------------------------------------------------- live guard


def live_execution_allowed() -> bool:
    return (
        os.environ.get("LIVE_TRADING") == "YES_I_UNDERSTAND"
        and os.environ.get("EXCHANGE_API_KEY")
        and os.environ.get("EXCHANGE_SECRET")
    )


def maybe_execute_live(exchange, sig: Signal):
    """Pravi nalog SAMO uz eksplicitni opt-in. Inače ništa."""
    if not live_execution_allowed():
        return
    print(f"[LIVE] šaljem limit buy {sig.symbol} @ {sig.entry} (SL {sig.stop} / TP {sig.target})")
    # Namjerno minimalno: limit entry; SL/TP nalozi ovise o burzi (OCO itd.)
    # pa ih postavi ručno ili proširi ovdje za svoju burzu.
    balance = exchange.fetch_balance()
    quote = sig.symbol.split("/")[1]
    free = balance.get(quote, {}).get("free", 0)
    risk_amount = free * RISK_PCT
    stop_dist = (sig.entry - sig.stop) / sig.entry
    amount = (risk_amount / stop_dist) / sig.entry if stop_dist > 0 else 0
    if amount <= 0:
        print("[LIVE] nema salda ili nevaljan sizing — preskačem")
        return
    exchange.create_order(sig.symbol, "limit", "buy", amount, sig.entry)
    print(f"[LIVE] nalog poslan: {amount:.6f} {sig.symbol} @ {sig.entry}. "
          f"POSTAVI SL/TP RUČNO na burzi!")


# ---------------------------------------------------------------- modovi


def make_exchange():
    cls = getattr(ccxt, EXCHANGE_ID)
    cfg = {"enableRateLimit": True}
    if live_execution_allowed():
        cfg["apiKey"] = os.environ["EXCHANGE_API_KEY"]
        cfg["secret"] = os.environ["EXCHANGE_SECRET"]
    return cls(cfg)


def cmd_scan(symbols):
    ex = make_exchange()
    journal = load_journal()
    for sym in symbols:
        sig, reason = scan_symbol(ex, sym)
        if sig:
            print(f"\n🟢 SIGNAL {sym}\n{json.dumps(asdict(sig), indent=2)}")
            if paper_enter(journal, sig):
                print(f"→ paper trade upisan (journal: {JOURNAL})")
            maybe_execute_live(ex, sig)
        else:
            print(f"— {sym}: {reason}")
    paper_update(journal, ex)
    save_journal(journal)


def cmd_watch(symbols, interval=60):
    ex = make_exchange()
    mode = "LIVE" if live_execution_allowed() else "PAPER"
    print(f"[{utcnow()}] watch mode ({mode}) — {', '.join(symbols)} svakih {interval}s. Ctrl+C za stop.")
    while True:
        journal = load_journal()
        for sym in symbols:
            try:
                sig, reason = scan_symbol(ex, sym)
                if sig:
                    print(f"\n🟢 [{utcnow()}] SIGNAL {sym}: entry {sig.entry} SL {sig.stop} "
                          f"TP {sig.target} R:R {sig.rr} ({sig.note})")
                    if paper_enter(journal, sig):
                        print("→ paper trade upisan")
                    maybe_execute_live(ex, sig)
            except ccxt.BaseError as e:
                print(f"[{utcnow()}] {sym}: greška burze: {e}")
        try:
            paper_update(journal, ex)
        except ccxt.BaseError as e:
            print(f"[{utcnow()}] update greška: {e}")
        save_journal(journal)
        time.sleep(interval)


def cmd_backtest(symbol):
    """Grubi walk-forward test setupa na HTF povijesti (bez LTF preciznosti).

    Aproksimacija: hammer tražimo na HTF svijećama umjesto na LTF (nemamo
    poravnatu LTF povijest u jednom fetchu) — rezultati su konzervativna
    donja granica, služe za osjećaj hit-ratea, ne za preciznu statistiku.
    """
    ex = make_exchange()
    candles = fetch(ex, symbol, HTF, 1000)
    wins = losses = 0
    balance = PAPER_BALANCE_START
    i = 100
    while i < len(candles) - 50:
        window = candles[:i]
        level_info = find_liquidity_level(window[-HTF_CANDLES:])
        if not level_info:
            i += 1
            continue
        level, _ = level_info
        sweep = detect_sweep(window[-HTF_CANDLES:], level)
        if not sweep:
            i += 1
            continue
        ok, vol_mult = is_stopping_volume_hammer(window[-1], [c[5] for c in window[:-1]])
        if not (ok and window[-1][3] <= level * (1 + EQUAL_LOW_TOLERANCE)):
            i += 1
            continue
        entry = window[-1][4]
        stop = window[-1][3] * 0.999
        target = find_target(window[-HTF_CANDLES:], entry)
        if not target or (target - entry) / (entry - stop) < MIN_RR:
            i += 1
            continue
        # odigraj naprijed
        rr = (target - entry) / (entry - stop)
        outcome = None
        for j in range(i, min(i + 200, len(candles))):
            if candles[j][3] <= stop:
                outcome = "SL"
                break
            if candles[j][2] >= target:
                outcome = "TP"
                break
        if outcome == "TP":
            wins += 1
            balance *= 1 + RISK_PCT * rr
        elif outcome == "SL":
            losses += 1
            balance *= 1 - RISK_PCT
        i += 10  # ne broji isti setup više puta
    total = wins + losses
    wr = wins / total * 100 if total else 0
    print(f"\nBacktest {symbol} ({HTF}, ~{len(candles)} svijeća)")
    print(f"tradeova: {total}  win: {wins}  loss: {losses}  win-rate: {wr:.1f}%")
    print(f"balans: {PAPER_BALANCE_START:.0f} → {balance:.2f} "
          f"({(balance / PAPER_BALANCE_START - 1) * 100:+.1f}%)")
    print("Napomena: HTF aproksimacija hammera — konzervativna donja granica.")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode, symbols = sys.argv[1], sys.argv[2:]
    if mode == "scan":
        cmd_scan(symbols)
    elif mode == "watch":
        cmd_watch(symbols)
    elif mode == "backtest":
        cmd_backtest(symbols[0])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
