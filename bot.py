#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram → VLESS  (TCP + HTTP header)  
• فایل‌های JSON در /root/vless_configs ذخیره می‌شوند؛ هیچ‌وقت حذف نمی‌شوند.  
• نام کانتینر، فایل و تگ لینک یکسان است: vless1، vless2، …  
• لینک خروجی:  
  vless://UUID@IP:PORT?security=&encryption=none&host=telewebion.com&headerType=http&type=tcp#vlessN
"""

from pathlib import Path
import os, subprocess, uuid, socket, json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler

# ─────────────── ثابت‌ها
TOKEN           = "7654851929:AAFgrDaS5JNiaXxIaQnWoQQB8hpeX4uhjNM"
ADMIN_USER_ID   = 71228850

SERVER_IP       = "185.110.188.25"
BASE_PORT       = 20002
IMAGE           = "v2fly/v2fly-core"

CONFIG_DIR      = Path("/root/vless_configs")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

HOST_HEADER     = "telewebion.com"
HEADER_TYPE     = "http"
SECURITY        = ""          # TLS خاموش
ENCRYPTION      = "none"
NETWORK_TYPE    = "tcp"

def log(msg: str) -> None:
    print(f"[DEBUG] {msg}")

# ─────────────── ابزارها
def free_port(start: int) -> int:
    p = start
    while p < 65535:
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                p += 1
    raise RuntimeError("پورت آزاد پیدا نشد!")

def make_json(name: str, port: int) -> tuple[str, Path]:
    """ایجاد فایل JSON با هدر HTTP طبق نیاز کلاینت."""
    uid = str(uuid.uuid4())
    cfg = {
        "inbounds": [{
            "port": port,
            "listen": "0.0.0.0",
            "protocol": "vless",
            "settings": {
                "clients": [
                    {
                        "id": uid,
                        "level": 0,
                        "email": f"{name}@example.com"
                    }
                ],
                "decryption": "none"
            },
            "streamSettings": {
                "network": "tcp",
                "tcpSettings": {
                    "acceptProxyProtocol": False,
                    "header": {
                        "type": "http",
                        "request": {
                            "version": "1.1",
                            "method": "GET",
                            "path": ["/"],
                            "headers": {
                                "Host": [HOST_HEADER],
                                "User-Agent": ["Mozilla/5.0 (compatible; V2Ray)"],
                                "Accept-Encoding": ["gzip, deflate"],
                                "Connection": ["keep-alive"],
                                "Pragma": ["no-cache"]
                            }
                        }
                    }
                }
            }
        }],
        "outbounds": [
            {
                "protocol": "freedom",
                "settings": {}
            }
        ]
    }
    path = CONFIG_DIR / f"{name}.json"
    path.write_text(json.dumps(cfg, indent=2))
    log(f"JSON → {path}")
    return uid, path

def run_container(name: str, cfg_path: Path, port: int) -> None:
    """اجرای کانتینر با bind-mount کانفیگ."""
    subprocess.run(f"docker rm -f {name}", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = [
        "docker", "run", "-d", "--name", name,
        "-v", f"{cfg_path}:/etc/v2ray/config.json",
        "-p", f"{port}:{port}",
        IMAGE, "run", "-config=/etc/v2ray/config.json"
    ]
    res = subprocess.run(cmd, text=True, capture_output=True)
    log(f"docker run → {res.stdout.strip()} {res.stderr.strip()}")

def vless_link(uid: str, port: int, tag: str) -> str:
    return (f"vless://{uid}@{SERVER_IP}:{port}"
            f"?security={SECURITY}&encryption={ENCRYPTION}"
            f"&host={HOST_HEADER}&headerType={HEADER_TYPE}&type={NETWORK_TYPE}#{tag}")

# ─────────────── هندلر تلگرام
async def start_cmd(upd: Update, ctx: CallbackContext) -> None:
    uid_tg = upd.effective_user.id
    log(f"/start by {uid_tg}")

    status_path = Path("containers_status.txt")
    lines = status_path.read_text().splitlines() if status_path.exists() else []
    if uid_tg != ADMIN_USER_ID and any(l.startswith(str(uid_tg)) for l in lines):
        await upd.message.reply_text("قبلاً یک کانفیگ دریافت کرده‌اید.")
        return

    idx   = len(lines) + 1
    name  = f"vless{idx}"
    port  = free_port(BASE_PORT + idx)

    uid, cfg_path = make_json(name, port)
    run_container(name, cfg_path, port)

    with status_path.open("a") as f:
        f.write(f"{uid_tg},{name},{port}\n")

    link = vless_link(uid, port, name)
    kb   = InlineKeyboardMarkup([[InlineKeyboardButton("کپی کردم ✅", callback_data="ok")]])

    await upd.message.reply_text("🔗 لینک کانفیگ شما:", reply_markup=kb)
    await upd.message.reply_text(f"```\n{link}\n```", parse_mode="Markdown")

async def ack(upd: Update, ctx: CallbackContext) -> None:
    await upd.callback_query.answer("موفق باشید! 🚀", show_alert=False)

# ─────────────── اجرا
def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(ack))
    log("Bot polling …")
    app.run_polling()

if __name__ == "__main__":
    main()
