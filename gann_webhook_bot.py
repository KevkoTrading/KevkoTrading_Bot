# Gann Box — TradingView Webhook → Telegram Bot
# Deploy auf Railway.app oder Render.com (kostenlos)
# Benötigt: Python 3.9+, flask, requests

import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ─── KONFIGURATION ────────────────────────────────────────────────────────────
# Diese Werte als Environment Variables setzen (nicht hier hardcoden!)
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")   # Bot Token von BotFather
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "") # Deine Chat ID
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")   # Eigenes Passwort als Schutz

# ─── TELEGRAM NACHRICHT SENDEN ────────────────────────────────────────────────
def round_val(val):
    """Rundet einen Wert auf 3 Dezimalstellen"""
    try:
        return str(round(float(val), 3))
    except:
        return str(val)

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("FEHLER: TELEGRAM_TOKEN oder TELEGRAM_CHAT_ID nicht gesetzt")
        return False

    # Mehrere Chat IDs per Komma trennen: "123456,789012"
    chat_ids = [c.strip() for c in TELEGRAM_CHAT_ID.split(",")]
    success = True

    for chat_id in chat_ids:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(url, json=data, timeout=10)
            if r.status_code != 200:
                print(f"Telegram Fehler fuer {chat_id}: {r.text}")
                success = False
        except Exception as e:
            print(f"Telegram Fehler: {e}")
            success = False

    return success

# ─── NACHRICHT FORMATIEREN ────────────────────────────────────────────────────
def format_signal(data: dict) -> str:
    alert_type = data.get("type", "SIGNAL").upper()
    asset      = data.get("asset", "-")
    direction  = data.get("direction", "-").upper()
    ema_status = data.get("ema", "-").upper()
    entry      = round_val(data.get("entry", "-"))
    sl         = round_val(data.get("sl", "-"))
    be         = round_val(data.get("be", "-"))
    tp1        = round_val(data.get("tp1", "-"))
    tp2        = round_val(data.get("tp2", "-"))
    tp3        = round_val(data.get("tp3", "-"))
    risk       = round_val(data.get("risk", "-"))
    timeframe  = data.get("timeframe", "4H")
    now        = datetime.now().strftime("%d.%m.%Y %H:%M")

    dir_arrow  = "LONG" if direction == "LONG" else "SHORT"
    ema_label  = "Mit Trend" if ema_status == "MT" else "Gegen Trend"

    if alert_type == "SIGNAL":
        # Signal Ablauf berechnen — 4 Kerzen ab jetzt
        tf_hours = {"1": 1, "3": 3, "4H": 4, "4": 4, "D": 24, "1D": 24, "W": 168}
        hours = tf_hours.get(timeframe, 4)
        from datetime import timedelta
        expiry_dt = datetime.now() + timedelta(hours=hours * 4)
        expiry = expiry_dt.strftime("%d.%m.%Y %H:%M")
        risk_pct = "2%" if ema_status == "MT" else "1%"

        return (
            f"<b>GANN BOX SIGNAL</b>\n"
            f"<b>{dir_arrow} {asset}</b>  |  {timeframe}\n"
            f"<b>{ema_label} — Risiko {risk_pct}</b>\n"
            f"---\n"
            f"Entry : <code>{entry}</code>\n"
            f"SL    : <code>{sl}</code>\n"
            f"BE    : <code>{be}</code>\n"
            f"TP1   : <code>{tp1}</code>\n"
            f"TP2   : <code>{tp2}</code>\n"
            f"TP3   : <code>{tp3}</code>\n"
            f"Risk  : <code>{risk}</code>\n"
            f"---\n"
            f"Signal gueltig bis: <b>{expiry}</b>\n"
            f"Danach Order loeschen!\n"
            f"---\n"
            f"{now}"
        )

    elif alert_type == "BE":
        return (
            f"<b>BE TRIGGER - {asset}</b>\n"
            f"---\n"
            f"50% Position schliessen!\n"
            f"SL auf Entry: <code>{entry}</code>\n"
            f"Trade ist RISIKOLOS\n"
            f"{now}"
        )

    elif alert_type == "TP1":
        return (
            f"<b>TP1 ERREICHT - {asset}</b>\n"
            f"---\n"
            f"Rest laeuft auf TP2: <code>{tp2}</code>\n"
            f"SL bleibt auf Entry: <code>{entry}</code>\n"
            f"{now}"
        )

    elif alert_type == "TP2":
        return (
            f"<b>TP2 ERREICHT - {asset}</b>\n"
            f"---\n"
            f"SL auf TP1 ziehen: <code>{tp1}</code>\n"
            f"Rest laeuft auf TP3: <code>{tp3}</code>\n"
            f"{now}"
        )

    elif alert_type == "SL":
        return (
            f"<b>STOP LOSS - {asset}</b>\n"
            f"---\n"
            f"Trade geschlossen bei: <code>{sl}</code>\n"
            f"Ergebnis: -1R\n"
            f"{now}"
        )

    else:
        return f"<b>{asset}</b>\n{json.dumps(data, indent=2)}\n{now}"

# ─── WEBHOOK ENDPOINT ─────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    # Secret prüfen
    if WEBHOOK_SECRET:
        secret = request.args.get("secret", "")
        if secret != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    # JSON parsen
    try:
        data = request.get_json(force=True)
        if not data:
            data = json.loads(request.data.decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"JSON parse error: {e}"}), 400

    print(f"Webhook empfangen: {json.dumps(data)}")

    # Nachricht formatieren und senden
    message = format_signal(data)
    success = send_telegram(message)

    return jsonify({
        "status":  "ok" if success else "telegram_error",
        "message": message
    }), 200 if success else 500

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status":    "running",
        "bot_ready": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "time":      datetime.now().isoformat()
    })

# ─── START ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Server startet auf Port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
