#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import json, uuid, socket, shlex, subprocess, telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackContext, CallbackQueryHandler
)

TOKEN, ADMIN_ID = "7654851929:AAFgrDaS5JNiaXxIaQnWoQQB8hpeX4uhjNM", 71228850
SERVER_IP, BASE_PORT, DOCKER_IMG = "185.110.188.25", 20002, "v2fly/v2fly-core"
CONFIG_DIR = Path("/root/vless_configs"); CONFIG_DIR.mkdir(exist_ok=True)
HOST_HEADER, HEADER_TYPE, SECURITY, ENCRYPTION, NETWORK = "telewebion.com", "http", "", "none", "tcp"

def sh(cmd: str) -> str:
    return subprocess.run(shlex.split(cmd), text=True, capture_output=True).stdout.strip()

def container_exists(name): return bool(sh(f"docker ps -a -q -f name={name}"))
def free_port(start):
    p = start
    while p < 65535:
        with socket.socket() as s:
            try: s.bind(("0.0.0.0", p)); return p
            except OSError: p += 1
    raise RuntimeError("پورت آزاد پیدا نشد!")

def make_json(name, port):
    uid = str(uuid.uuid4())
    cfg = {
        "inbounds":[{ "port":port,"listen":"0.0.0.0","protocol":"vless",
        "settings":{"clients":[{"id":uid,"level":0,"email":f"{name}@example.com"}],"decryption":"none"},
        "streamSettings":{"network":"tcp","tcpSettings":{"acceptProxyProtocol":False,"header":{
          "type":"http","request":{"version":"1.1","method":"GET","path":["/"],"headers":{
             "Host":[HOST_HEADER],"User-Agent":["Mozilla/5.0 (compatible; V2Ray)"],
             "Accept-Encoding":["gzip, deflate"],"Connection":["keep-alive"],"Pragma":["no-cache"]}}}}}}],
        "outbounds":[{"protocol":"freedom","settings":{}}]
    }
    path = CONFIG_DIR/f"{name}.json"; path.write_text(json.dumps(cfg,indent=2))
    return uid, path

def run_container(name, cfg, port):
    sh(f"docker rm -f {name}")
    sh(f"docker run -d --name {name} -v {cfg}:/etc/v2ray/config.json -p {port}:{port} "
       f"{DOCKER_IMG} run -config=/etc/v2ray/config.json")

def vless_link(uid, port, tag):
    return (f"vless://{uid}@{SERVER_IP}:{port}"
            f"?security={SECURITY}&encryption={ENCRYPTION}"
            f"&host={HOST_HEADER}&headerType={HEADER_TYPE}&type={NETWORK}#{tag}")

def list_containers():
    raw=sh("docker ps -a --filter 'name=vless' --format '{{.Names}}\t{{.Ports}}\t{{.Status}}'")
    out=[]
    for ln in raw.splitlines():
        name,ports,stat=ln.split("\t")
        port=ports.split('->')[0].split(':')[-1] if '->' in ports else '?'
        state="Up" if stat.lower().startswith("up") else "Exited"
        out.append({"name":name,"port":port,"state":state})
    return out

def kb_list(conts):
    rows=[[InlineKeyboardButton(f"▶ {c['name']}",callback_data=f"act|start|{c['name']}"),
           InlineKeyboardButton(f"⏸ {c['name']}",callback_data=f"act|stop|{c['name']}"),
           InlineKeyboardButton(f"🗑 {c['name']}",callback_data=f"act|del|{c['name']}")] for c in conts]
    rows.append([InlineKeyboardButton("🔄 بروزرسانی لیست",callback_data="act|refresh|x")])
    return InlineKeyboardMarkup(rows)

async def cmd_start(upd:Update,ctx:CallbackContext):
    is_admin=upd.effective_user.id==ADMIN_ID
    msg="سلام! 👋\nبرای ساخت کانفیگ روی دکمه زیر بزنید."
    btn=[[InlineKeyboardButton("➕ ساخت کانفیگ جدید",callback_data="create")]]
    if is_admin: btn.append([InlineKeyboardButton("📋 لیست کانتینرها",callback_data="showlist")])
    await upd.message.reply_text(msg,reply_markup=InlineKeyboardMarkup(btn))

async def cb_create(update:Update,ctx:CallbackContext):
    uid_tg=update.effective_user.id
    sf=Path("containers_status.txt")
    lines=sf.read_text().splitlines() if sf.exists() else []

    # ✨ تغییر اصلی اینجاست
    # این شرط بررسی می‌کند که اگر کاربر ادمین "نیست" و قبلاً کانفیگ ساخته، به او اجازه ساخت مجدد ندهد
    if uid_tg != ADMIN_ID and any(l.startswith(str(uid_tg)) for l in lines):
        try: await update.callback_query.answer("شما قبلاً یک کانفیگ دریافت کرده‌اید.",show_alert=True)
        except telegram.error.BadRequest: pass
        return

    # ادمین یا کاربری که برای اولین بار کانفیگ می‌سازد، به این بخش می‌رسد
    idx=len(lines)+1; name=f"vless{idx}"; port=free_port(BASE_PORT+idx)
    uid,cfg=make_json(name,port); run_container(name,cfg,port)
    sf.write_text("\n".join(lines+[f"{uid_tg},{name},{port}"]))
    link=vless_link(uid,port,name)
    try: await update.callback_query.answer("کانفیگ ساخته شد!",show_alert=False)
    except telegram.error.BadRequest: pass
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("کپی کردم ✅",callback_data="ack")]])
    await update.callback_query.message.reply_text("🔗 لینک کانفیگ:",reply_markup=kb)
    await update.callback_query.message.reply_text(f"```\n{link}\n```",parse_mode="Markdown")

async def cb_showlist(update:Update,ctx:CallbackContext):
    if update.effective_user.id!=ADMIN_ID:
        try: await update.callback_query.answer("اجازه ندارید.",show_alert=True)
        except telegram.error.BadRequest: pass; return
    conts=list_containers()
    txt="\n".join(f"◾️ {c['name']} | پورت {c['port']} | {c['state']}" for c in conts) or "هیچ کانتینری یافت نشد."
    await update.callback_query.message.reply_text(txt,reply_markup=kb_list(conts))

async def cb_action(update:Update,ctx:CallbackContext):
    if update.effective_user.id!=ADMIN_ID:
        try: await update.callback_query.answer("اجازه ندارید.",show_alert=True)
        except telegram.error.BadRequest: pass; return
    _,act,name=update.callback_query.data.split("|")
    if act!="refresh" and not container_exists(name):
        try: await update.callback_query.answer("کانتینر یافت نشد.",show_alert=True)
        except telegram.error.BadRequest: pass; return
    if act=="start": sh(f"docker start {name}")
    elif act=="stop": sh(f"docker stop {name}")
    elif act=="del":
        sh(f"docker rm -f {name}"); cfg=CONFIG_DIR/f"{name}.json"; cfg.unlink(missing_ok=True)
    conts=list_containers()
    txt="\n".join(f"◾️ {c['name']} | پورت {c['port']} | {c['state']}" for c in conts) or "هیچ کانتینری باقی نمانده."
    kb=kb_list(conts) if conts else None
    try:
        await update.callback_query.edit_message_text(txt,reply_markup=kb)
    except telegram.error.BadRequest:
        # «Message is not modified» → فقط نادیده بگیر
        pass

async def cb_ack(update:Update,ctx:CallbackContext):
    try: await update.callback_query.answer("موفق باشید!",show_alert=False)
    except telegram.error.BadRequest: pass

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CallbackQueryHandler(cb_create,pattern="^create$"))
    app.add_handler(CallbackQueryHandler(cb_showlist,pattern="^showlist$"))
    app.add_handler(CallbackQueryHandler(cb_action,pattern="^act\\|"))
    app.add_handler(CallbackQueryHandler(cb_ack,pattern="^ack$"))
    app.run_polling()

if __name__=="__main__":
    main()
