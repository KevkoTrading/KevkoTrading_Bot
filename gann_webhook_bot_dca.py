# Gann Box — TradingView Webhook → Telegram Bot v2 (DCA Edition)
# Neu: DCA Entries, BE/TP/DCA Hit Nachrichten, Durchstreichen bei Expiry/SL

import os, json, threading, requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")

# ─── STATE: offene Signale mit Message IDs ─────────────────────────────────────
STATE_FILE = "/tmp/gann_signals.json"

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def signal_key(asset, direction):
    return f"{asset}_{direction}"

# ─── TELEGRAM HELPERS ─────────────────────────────────────────────────────────
def get_chat_ids():
    return [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]

def send_telegram(text: str) -> list:
    msg_ids = []
    for chat_id in get_chat_ids():
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=data, timeout=10)
            if r.status_code == 200:
                msg_ids.append({"chat_id": chat_id, "msg_id": r.json()["result"]["message_id"]})
            else:
                print(f"Send error {chat_id}: {r.text}")
        except Exception as e:
            print(f"Send error: {e}")
    return msg_ids

def edit_telegram(chat_id, message_id, text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Edit error: {e}")
        return False

def strikethrough(text: str) -> str:
    lines = text.split("\n")
    struck = []
    for line in lines:
        if line.strip():
            struck.append(f"<s>{line}</s>")
        else:
            struck.append(line)
    return "\n".join(struck)

def strike_messages(msg_ids: list, original_text: str, suffix: str = ""):
    struck = strikethrough(original_text)
    if suffix:
        struck += f"\n{suffix}"
    for entry in msg_ids:
        edit_telegram(entry["chat_id"], entry["msg_id"], struck)

# ─── FORMATTER ────────────────────────────────────────────────────────────────
def rv(val, prec=5):
    try:
        v = float(val)
        if v > 100:
            return f"{v:.2f}"
        return f"{v:.{prec}f}".rstrip('0').rstrip('.')
    except:
        return str(val)

def format_signal(data: dict):
    t         = data.get("type", "SIGNAL").upper()
    asset     = data.get("asset", "-")
    direction = data.get("direction", "-").upper()
    ema       = data.get("ema", "-").upper()
    entry50   = rv(data.get("entry50") or data.get("entry", "-"))
    entry25   = rv(data.get("entry25", "-"))
    sl        = rv(data.get("sl", "-"))
    be        = rv(data.get("be", "-"))
    tp1       = rv(data.get("tp1", "-"))
    tp2       = rv(data.get("tp2", "-"))
    tp3       = rv(data.get("tp3", "-"))
    risk      = rv(data.get("risk", "-"))
    tf        = data.get("timeframe", "4H")
    now       = datetime.now().strftime("%d.%m.%Y %H:%M")

    arrow     = "▲ LONG" if direction == "LONG" else "▼ SHORT"
    ema_lbl   = "With Trend" if ema == "MT" else "Against Trend"
    risk_pct  = "1%" if ema == "MT" else "0.5%"

    CRYPTO_ASSETS = {"BTCUSD","BTCUSDT","ETHUSD","ETHUSDT","BNBUSD","BNBUSDT",
                     "SOLUSD","SOLUSDT","XRPUSD","XRPUSDT","ADAUSD","ADAUSDT",
                     "AVAXUSD","AVAXUSDT","LTCUSD","LTCUSDT"}

    def calc_expiry(asset_ticker, tf_str):
        hours_per_candle = {"1":1,"3":3,"4H":4,"4":4,"D":24,"1D":24,"W":168}.get(tf_str, 4)
        candles = 4
        is_crypto = asset_ticker.upper() in CRYPTO_ASSETS

        if is_crypto:
            return datetime.now() + timedelta(hours=hours_per_candle * candles)

        dt = datetime.now()
        closes = [2, 6, 10, 14, 18, 22]
        for close_hour in closes:
            if dt.hour < close_hour:
                dt = dt.replace(hour=close_hour, minute=0, second=0, microsecond=0)
                break
        else:
            dt = (dt + timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)

        counted = 0
        while counted < candles:
            dt += timedelta(hours=hours_per_candle)
            if dt.weekday() < 5:
                counted += 1

        return dt

    if t == "SIGNAL":
        expiry  = calc_expiry(asset, tf)
        exp_str = expiry.strftime("%d.%m.%Y %H:%M")

        has_dca = data.get("entry25") and data.get("entry25") != data.get("entry50")
        if has_dca:
            entry_block = (
                f"E 0.50 : <code>{entry50}</code>  ← ½ Size\n"
                f"E 0.25 : <code>{entry25}</code>  ← ½ Size"
            )
        else:
            entry_block = f"Entry  : <code>{entry50}</code>"

        text = (
            f"<b>🐴 GANN BOX SIGNAL</b>\n"
            f"<b>{arrow} {asset}</b>  |  {tf}\n"
            f"<b>{ema_lbl} — Risk {risk_pct}</b>\n"
            f"───────────────\n"
            f"{entry_block}\n"
            f"SL     : <code>{sl}</code>\n"
            f"BE     : <code>{be}</code>\n"
            f"TP1    : <code>{tp1}</code>\n"
            f"TP2    : <code>{tp2}</code>\n"
            f"TP3    : <code>{tp3}</code>\n"
            f"Risk Δ : <code>{risk}</code>\n"
            f"───────────────\n"
            f"Valid until: <b>{exp_str}</b>\n"
            f"Size auf 0.50 kalkulieren ÷ 2\n"
            f"───────────────\n"
            f"🕐 {now}"
        )
        return text, expiry

    elif t == "SL":
        text = (
            f"<b>❌ STOP LOSS — {asset}</b>\n"
            f"───────────────\n"
            f"SL: <code>{sl}</code> getriggert\n"
            f"Verlust < 1R (DCA Vorteil ✓)\n"
            f"───────────────\n"
            f"🕐 {now}"
        )
        return text, None

    elif t == "NEWS":
        event  = data.get("event", "-")
        impact = data.get("impact", "HIGH")
        time_  = data.get("time", "-")
        note   = data.get("note", "")
        text = (
            f"<b>📰 FOREX NEWS WARNUNG — {asset}</b>\n"
            f"───────────────\n"
            f"Event  : <b>{event}</b>\n"
            f"Impact : <b>{impact}</b>\n"
            f"Zeit   : <code>{time_}</code>\n"
            f"───────────────\n"
            f"⚠️ Kein neuer Trade auf betroffene Paare!\n"
            + (f"{note}\n" if note else "")
            + f"───────────────\n"
            f"🕐 {now}"
        )
        return text, None

    else:
        # BE, DCA, TP1, TP2, TP3 — kein Telegram, nur intern verarbeiten
        return None, None

# ─── EXPIRY CHECKER ───────────────────────────────────────────────────────────
def expiry_checker():
    import time
    while True:
        time.sleep(60)
        try:
            state = load_state()
            changed = False
            for key, sig in state.items():
                if sig.get("struck"):
                    continue
                exp = sig.get("expiry")
                if not exp:
                    continue
                if datetime.now() > datetime.fromisoformat(exp):
                    strike_messages(
                        sig["msg_ids"],
                        sig["original_text"],
                        "⏰ EXPIRED — Order löschen!"
                    )
                    sig["struck"] = True
                    changed = True
            if changed:
                save_state(state)
        except Exception as e:
            print(f"Expiry checker error: {e}")

threading.Thread(target=expiry_checker, daemon=True).start()

# ─── WEBHOOK ──────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        if request.args.get("secret", "") != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    try:
        raw = request.data.decode("utf-8")
        print(f"Raw body: {raw[:300]}")
        data = request.get_json(force=True)
        if not data:
            data = json.loads(raw)
        if not data:
            return jsonify({"error": "Empty body"}), 400
    except Exception as e:
        return jsonify({"error": f"JSON parse error: {e}"}), 400

    print(f"Webhook: {json.dumps(data)}")

    alert_type = data.get("type", "SIGNAL").upper()
    asset      = data.get("asset", "-")
    direction  = data.get("direction", "-").upper()
    key        = signal_key(asset, direction)

    text, expiry = format_signal(data)
    state = load_state()

    if alert_type == "SIGNAL":
        msg_ids = send_telegram(text)
        state[key] = {
            "msg_ids":       msg_ids,
            "expiry":        expiry.isoformat() if expiry else None,
            "original_text": text,
            "struck":        False,
            "data":          data
        }
        save_state(state)

    elif alert_type == "TP3":
        # Strike-Through ohne Telegram-Nachricht
        if key in state and not state[key].get("struck"):
            strike_messages(state[key]["msg_ids"], state[key]["original_text"], "✅ TRADE GESCHLOSSEN — TP3")
            state[key]["struck"] = True
            save_state(state)

    elif alert_type == "SL":
        send_telegram(text)
        if key in state and not state[key].get("struck"):
            strike_messages(state[key]["msg_ids"], state[key]["original_text"], "❌ STOP LOSS")
            state[key]["struck"] = True
            save_state(state)

    elif alert_type == "NEWS":
        send_telegram(text)

    else:
        # BE, DCA, TP1, TP2 — ignoriert, kein Telegram
        print(f"Ignoriert: {alert_type} — kein Telegram")

    return jsonify({"status": "ok", "type": alert_type}), 200

# ─── HEALTH ───────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    state = load_state()
    open_signals = sum(1 for s in state.values() if not s.get("struck"))
    return jsonify({
        "status":       "running",
        "bot_ready":    bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "open_signals": open_signals,
        "time":         datetime.now().isoformat()
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Server startet auf Port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
