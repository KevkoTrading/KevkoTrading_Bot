cat > /root/bot/gann_webhook_bot_dca.py << 'EOF'
# Gann Box Webhook Bot — Simple Edition
# Empfaengt TradingView Alerts, sendet nur SIGNAL an Telegram

import os, json, requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")

def send_telegram(text):
    for chat_id in [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception as e:
            print(f"Telegram error: {e}")

def rv(val):
    try:
        v = float(val)
        return f"{v:.2f}" if v > 100 else f"{v:.5f}".rstrip('0').rstrip('.')
    except:
        return str(val)

@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET and request.args.get("secret","") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json(force=True, silent=True) or json.loads(request.data.decode("utf-8","ignore"))
    except:
        return jsonify({"error": "parse error"}), 400

    if not data:
        return jsonify({"error": "empty"}), 400

    print(f"Webhook: {json.dumps(data)}")

    alert_type = data.get("type", "SIGNAL").upper()

    if alert_type != "SIGNAL":
        print(f"Ignoriert: {alert_type}")
        return jsonify({"status": "ignored"}), 200

    asset     = data.get("asset", "-")
    direction = data.get("direction", "-").upper()
    ema       = data.get("ema", "-").upper()
    entry50   = rv(data.get("entry50") or data.get("entry", "-"))
    entry25   = rv(data.get("entry25", ""))
    sl        = rv(data.get("sl", "-"))
    be        = rv(data.get("be", "-"))
    tp1       = rv(data.get("tp1", "-"))
    tp2       = rv(data.get("tp2", "-"))
    tp3       = rv(data.get("tp3", "-"))
    risk      = rv(data.get("risk", "-"))
    tf        = data.get("timeframe", "4H")
    now       = datetime.now().strftime("%d.%m.%Y %H:%M")

    arrow   = "LONG" if direction == "LONG" else "SHORT"
    ema_lbl = "With Trend" if ema == "MT" else "Against Trend"
    risk_pct = "1%" if ema == "MT" else "0.5%"

    has_dca = entry25 and entry25 != entry50
    if has_dca:
        entry_block = f"E 0.50 : <code>{entry50}</code>\nE 0.25 : <code>{entry25}</code>"
    else:
        entry_block = f"Entry  : <code>{entry50}</code>"

    msg = (
        f"<b>GANN BOX SIGNAL</b>\n"
        f"<b>{arrow} {asset}</b> | {tf}\n"
        f"<b>{ema_lbl} - Risk {risk_pct}</b>\n"
        f"---\n"
        f"{entry_block}\n"
        f"SL  : <code>{sl}</code>\n"
        f"BE  : <code>{be}</code>\n"
        f"TP1 : <code>{tp1}</code>\n"
        f"TP2 : <code>{tp2}</code>\n"
        f"TP3 : <code>{tp3}</code>\n"
        f"Risk: <code>{risk}</code>\n"
        f"---\n"
        f"{now}"
    )

    send_telegram(msg)
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "bot_ready": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
EOF
systemctl restart gann-bot
