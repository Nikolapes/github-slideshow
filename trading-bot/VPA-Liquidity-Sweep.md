# 🎯 VPA-Liquidity Sweep — Glavni setup (playbook)

> Ovo je izvršni playbook za JEDAN setup. Sve iz vaulta (struktura, likvidnost, VPA, risk) spaja se ovdje u jednu odluku. Long-only.

## Mentalni model (mikrostruktura)

```
TRADING = igra s nultom sumom
  informirani (Smart Money) zarađuju od neinformiranih
        │
TRŽIŠTE = problem potrage za likvidnošću
  kupci traže prodavače; veliki igrač NE MOŽE kupiti bez bazena naloga
        │
LIKVIDNOST LEŽI na očitim razinama
  equal lows / equal highs / očiti swingovi = stop-loss bazeni
        │
CIJENA IDE PO LIKVIDNOST prije pravog pokreta
  sweep = insajderi kupuju po "veleprodajnoj cijeni"
        │
VOLUMEN = detektor laži (Wyckoff: napor vs rezultat)
  pokret bez volumena = zamka; sweep + stopping volume = akumulacija
```

## Zakoni (Wyckoff + VPA)

1. **Napor vs rezultat:** veliki pokret cijene MORA biti potvrđen visokim volumenom. Veliki volumen + mali pomak = apsorpcija (jedna strana upija drugu).
2. **Proboj bez volumena = fakeout.** Insajderska zamka, ne breakout.
3. **Stopping volume:** dugi donji fitilj (hammer) + ekstremni volumen na dnu = insajderi zaustavljaju pad i akumuliraju. "Mopping up" završava.
4. Grafikon nije niz svijeća — **borba za likvidnost** između Smart Money i javnosti.

## Setup: VPA-Liquidity Sweep (long)

### Korak 1 — Narativ (HTF: 1D/1W → zone na 1h/4h)
- Na Daily/Weekly odredi kamo tržište "želi" ići (gdje leži novac: EQH/EQL).
- Na 1h/4h označi **očito dno (support)** gdje se cijena odbila više puta → ispod njega sjede stop-lossovi kupaca = **sell-side liquidity**.

### Korak 2 — Sweep (inducement)
- Čekaj da cijena **agresivno padne ISPOD** tog dna.
- To NIJE signal za short — to je insajderska kupovina po veleprodajnoj cijeni (aktivirani stopovi = njihova likvidnost).
- Bez sweepa nema setupa. Ne ulazi na "približavanje zoni".

### Korak 3 — VPA potvrda (LTF: 5m/15m)
- Prebaci na 5m/15m i traži **Stopping Volume svijeću**:
  - dugi donji fitilj (fitilj ≥ 2× tijelo), close u gornjoj polovici raspona (hammer/čekić)
  - volumen ≥ **2×** prosjeka zadnjih 20 svijeća
- To je X-ray dokaz da insajderi apsorbiraju prodajni pritisak.
- Bez volumena, proboj dna je samo nastavak pada. S volumenom + fitiljem = akumulacija.

### Korak 4 — Brojke
- **Entry:** close hammer svijeće (ili retest njenog tijela).
- **Stop-Loss:** odmah ISPOD fitilja hammer svijeće — to je "prirodni pod" branjen insajderskim volumenom.
- **Take-Profit:** suprotna strana — prva razina neprobijenih **Equal Highs** (buy-side liquidity).
- **R:R ≥ 1:2 obavezno.** Ako TP nije bar 2× dalji od SL-a → nema trada.
- Rizik: max 1–2% računa.

### Zašto radi
Ne predviđaš smjer — **pratiš tragove novca**. Tržište prvo uzme novac slabim igračima (sweep), volumen potvrdi da su insajderi ušli, ti se voziš s njima do sljedećeg bazena likvidnosti.

## Invalidacija
- LTF svijeća **zatvori ispod** low-a hammer svijeće → ideja pala, izlaz bez rasprave.
- Sweep pa slab volumen na odbijanju → nije naš setup, čekaj sljedeći.
- HTF struktura LL+LH bez znaka preokreta → sweep može biti nastavak distribucije, preskoči.

## Checklist (kopiraj u journal)
- [ ] HTF narativ: gdje leži likvidnost (EQH iznad kao meta)?
- [ ] Očito dno na 1h/4h s višestrukim odbijanjima označeno?
- [ ] Sweep ISPOD dna se dogodio (ne samo dodir)?
- [ ] 5m/15m hammer: fitilj ≥ 2× tijela, close u gornjoj polovici?
- [ ] Volumen hammer svijeće ≥ 2× prosjeka 20 svijeća?
- [ ] SL ispod fitilja, TP na prvim EQH, R:R ≥ 1:2?
- [ ] Veto: news < 30 min? jurim? nemam stop unaprijed?

Povezano: 00 - TRADING MOC, Liquidity Sweep (Stop Hunt), Volumen, Market Structure (BOS i CHoCH), Risk Management

> ⚠️ Edukativni materijal, ne financijski savjet. Trading nosi rizik gubitka kapitala.
