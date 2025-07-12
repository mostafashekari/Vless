#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import json, uuid, socket, shlex, subprocess, telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackContext, CallbackQueryHandler
)

# --- ثابت‌ها و تنظیمات ---
TOKEN, ADMIN_ID = "7654851929:AAFgrDaS5JNiaXxIaQnWoQQB8hpeX4uhjNM", 71228850
SERVER_IP, BASE_PORT, DOCKER_IMG = "185.110.188.25", 20002, "v2fly/v2fly-core"
CONFIG_DIR = Path("/root/vless_configs"); CONFIG_DIR.mkdir(exist_ok=True)
HOST_HEADER, HEADER_TYPE, SECURITY, ENCRYPTION, NETWORK = "telewebion.com", "http", "", "none", "tcp"
SUPPORT_ID = "@vpnsuppo"
STATUS_FILE = Path("containers_status.txt")


# --- توابع کمکی Shell و Docker ---
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

# --- توابع ساخت کانفیگ و لینک VLESS ---
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

def get_uuid_from_config(name: str) -> str | None:
    config_path = CONFIG_DIR / f"{name}.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return data["inbounds"][0]["settings"]["clients"][0]["id"]
    except (IOError, json.JSONDecodeError, KeyError, IndexError):
        return None

# --- توابع مدیریت لیست کانتینرها و کیبوردها ---
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
    rows=[[InlineKeyboardButton(f"▶️ {c['name']}",callback_data=f"act|start|{c['name']}"),
           InlineKeyboardButton(f"⏸️ {c['name']}",callback_data=f"act|stop|{c['name']}"),
           InlineKeyboardButton(f"🗑️ {c['name']}",callback_data=f"act|del|{c['name']}")] for c in conts]
    rows.append([InlineKeyboardButton("🔄 بروزرسانی لیست",callback_data="act|refresh|x")])
    return InlineKeyboardMarkup(rows)

# --- توابع اصلی ربات (Handlers) ---
async def cmd_start(upd:Update,ctx:CallbackContext):
    is_admin=upd.effective_user.id==ADMIN_ID
    msg="سلام! 👋\nبرای مدیریت کانفیگ‌ها از دکمه‌های زیر استفاده کنید."
    btn=[
        [InlineKeyboardButton("➕ ساخت کانفیگ جدید",callback_data="create")],
        [InlineKeyboardButton("📄 کانفیگ من", callback_data="myconfig")]
    ]
    if is_admin: btn.append([InlineKeyboardButton("📋 لیست کانتینرها",callback_data="showlist")])
    await upd.message.reply_text(msg,reply_markup=InlineKeyboardMarkup(btn))

async def cb_create(update:Update,ctx:CallbackContext):
    user = update.effective_user
    uid_tg = user.id
    lines=STATUS_FILE.read_text().splitlines() if STATUS_FILE.exists() else []

    if uid_tg != ADMIN_ID and any(l.startswith(str(uid_tg)) for l in lines):
        try: await update.callback_query.answer("شما قبلاً یک کانفیگ دریافت کرده‌اید.",show_alert=True)
        except telegram.error.BadRequest: pass
        return

    idx=len(lines)+1; name=f"vless{idx}"; port=free_port(BASE_PORT+idx)
    uid,cfg=make_json(name,port); run_container(name,cfg,port)
    STATUS_FILE.write_text("\n".join(lines+[f"{uid_tg},{name},{port}"]))
    link=vless_link(uid,port,name)
    try: await update.callback_query.answer("کانفیگ ساخته شد!",show_alert=False)
    except telegram.error.BadRequest: pass
    
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("کپی کردم ✅",callback_data="ack")]])
    await update.callback_query.message.reply_text("🔗 لینک کانفیگ شما:",reply_markup=kb)
    await update.callback_query.message.reply_text(f"```\n{link}\n```",parse_mode="Markdown")

    subscription_info = (
        f"⚠️ **توجه:**\n\n"
        f"- این کانفیگ دارای **۱ ساعت مهلت تست رایگان** است.\n"
        f"- پس از اتمام مهلت تست، برای ادامه استفاده، نیاز به تهیه اشتراک ماهیانه دارید.\n\n"
        f"**اطلاعات اشتراک:**\n"
        f"- 💳 **قیمت:** ۹۹ هزار تومان (ماهیانه)\n"
        f"- 📊 **حجم:** نامحدود\n"
        f"- 👤 **کاربر:** تک کاربره\n\n"
        f"برای فعال‌سازی اشتراک و پرداخت، لطفاً به آیدی زیر پیام دهید:\n"
        f"**{SUPPORT_ID}**"
    )
    await update.callback_query.message.reply_text(subscription_info, parse_mode="Markdown")

    if uid_tg != ADMIN_ID:
        user_info = f"نام: {user.first_name}"
        if user.last_name: user_info += f" {user.last_name}"
        if user.username: user_info += f" | یوزرنیم: @{user.username}"
        
        admin_message = (
            f"✅ **کانفیگ جدید ساخته شد**\n\n"
            f"👤 **توسط کاربر:**\n{user_info}\n"
            f"آیدی عددی: `{user.id}`\n\n"
            f"🔗 **لینک کانفیگ:**\n```\n{link}\n```"
        )
        try:
            await ctx.bot.send_message(chat_id=ADMIN_ID, text=admin_message, parse_mode="Markdown")
        except telegram.error.TelegramError as e:
            print(f"Failed to send message to admin: {e}")


async def cb_myconfig(update: Update, ctx: CallbackContext):
    user_id = update.effective_user.id
    if not STATUS_FILE.exists():
        await update.callback_query.message.reply_text("هنوز هیچ کانفیگی ساخته نشده است.")
        return

    lines = STATUS_FILE.read_text().splitlines()
    user_configs = []

    for line in lines:
        parts = line.split(',')
        if len(parts) != 3: continue
        
        line_user_id, name, port = parts
        
        if user_id == ADMIN_ID:
            user_configs.append({'name': name, 'port': port})
        elif int(line_user_id) == user_id:
            user_configs.append({'name': name, 'port': port})
            break

    if not user_configs:
        await update.callback_query.message.reply_text("شما هنوز کانفیگی نساخته‌اید. روی دکمه 'ساخت کانفیگ جدید' بزنید.")
        return

    response_text = []
    for config in user_configs:
        name, port = config['name'], config['port']
        uid = get_uuid_from_config(name)
        if uid:
            link = vless_link(uid, port, name)
            response_text.append(f"کانفیگ `{name}`:\n```\n{link}\n```")
        else:
            response_text.append(f"اطلاعات کانفیگ `{name}` یافت نشد.")

    final_message = "\n\n".join(response_text)
    if user_id == ADMIN_ID:
        final_message = "📋 **لیست تمام کانفیگ‌های ساخته شده:**\n\n" + final_message

    await update.callback_query.message.reply_text(final_message, parse_mode="Markdown")
    await update.callback_query.answer()


async def cb_showlist(update:Update,ctx:CallbackContext):
    if update.effective_user.id!=ADMIN_ID:
        try: await update.callback_query.answer("اجازه ندارید.",show_alert=True)
        except telegram.error.BadRequest: pass; return
    
    conts=list_containers()
    
    # ✨ قابلیت جدید: شمارش کانتینرهای فعال
    up_count = sum(1 for c in conts if c['state'] == 'Up')
    total_count = len(conts)
    header = f"📊 **وضعیت کانتینرها**\nتعداد کل: {total_count} | تعداد فعال (Up): {up_count}\n\n"
    
    list_text="\n".join(f"◾️ `{c['name']}` | پورت {c['port']} | وضعیت: **{c['state']}**" for c in conts) or "هیچ کانتینری یافت نشد."
    
    await update.callback_query.message.reply_text(header + list_text, parse_mode="Markdown", reply_markup=kb_list(conts))


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
        # ✨ قابلیت جدید: حذف کاربر از فایل وضعیت تا بتواند دوباره کانفیگ بسازد
        if STATUS_FILE.exists():
            lines = STATUS_FILE.read_text().splitlines()
            # خطی که نام کانتینر در آن است را حذف می‌کنیم
            lines_to_keep = [line for line in lines if f',{name},' not in line]
            STATUS_FILE.write_text("\n".join(lines_to_keep))
    
    # بروزرسانی لیست پس از انجام عملیات
    conts=list_containers()
    up_count = sum(1 for c in conts if c['state'] == 'Up')
    total_count = len(conts)
    header = f"📊 **وضعیت کانتینرها**\nتعداد کل: {total_count} | تعداد فعال (Up): {up_count}\n\n"
    list_text="\n".join(f"◾️ `{c['name']}` | پورت {c['port']} | وضعیت: **{c['state']}**" for c in conts) or "هیچ کانتینری باقی نمانده."
    
    kb=kb_list(conts) if conts else None
    try:
        await update.callback_query.edit_message_text(header + list_text, parse_mode="Markdown", reply_markup=kb)
    except telegram.error.BadRequest as e:
        if 'Message is not modified' not in str(e): # اگر خطا مربوط به عدم تغییر پیام نبود، آن را نادیده نگیر
            await update.callback_query.message.reply_text(header + list_text, parse_mode="Markdown", reply_markup=kb)


async def cb_ack(update:Update,ctx:CallbackContext):
    try: await update.callback_query.answer("موفق باشید!",show_alert=False)
    except telegram.error.BadRequest: pass

# --- تابع اصلی و اجرای ربات ---
def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CallbackQueryHandler(cb_create,pattern="^create$"))
    app.add_handler(CallbackQueryHandler(cb_showlist,pattern="^showlist$"))
    app.add_handler(CallbackQueryHandler(cb_action,pattern="^act\\|"))
    app.add_handler(CallbackQueryHandler(cb_ack,pattern="^ack$"))
    app.add_handler(CallbackQueryHandler(cb_myconfig, pattern="^myconfig$"))
    
    app.run_polling()

if __name__=="__main__":
    main()
