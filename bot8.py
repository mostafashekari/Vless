#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import json, uuid, socket, shlex, subprocess, telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application, CommandHandler, CallbackContext, CallbackQueryHandler
)

# --- Constants and Settings ---
TOKEN = "7654851929:AAFgrDaS5JNiaXxIaQnWoQQB8hpeX4uhjNM"
ADMIN_IDS = {71228850}
SERVER_IP, BASE_PORT, DOCKER_IMG = "185.110.188.25", 20002, "v2fly/v2fly-core"
CONFIG_DIR = Path("/root/vless_configs"); CONFIG_DIR.mkdir(exist_ok=True)
HOST_HEADER, HEADER_TYPE, SECURITY, ENCRYPTION, NETWORK = "telewebion.com", "http", "", "none", "tcp"
SUPPORT_ID = "@vpnsuppo"
STATUS_FILE = Path("containers_status.txt")


# --- Shell and Docker Helper Functions ---
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

# --- VLESS Config and Link Functions ---
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
       f"--restart unless-stopped "
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

# --- Container List and Keyboard Functions ---
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
    rows=[[InlineKeyboardButton(f"▶️ فعال‌سازی {c['name']}",callback_data=f"act|start|{c['name']}"),
           InlineKeyboardButton(f"⏸️ توقف {c['name']}",callback_data=f"act|stop|{c['name']}"),
           InlineKeyboardButton(f"🗑️ حذف {c['name']}",callback_data=f"act|del|{c['name']}")] for c in conts]
    rows.append([InlineKeyboardButton("🔄 بروزرسانی لیست",callback_data="act|refresh|x")])
    return InlineKeyboardMarkup(rows)

# --- Main Bot Handlers ---
async def cmd_start(upd:Update,ctx:CallbackContext):
    is_admin = upd.effective_user.id in ADMIN_IDS
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

    if uid_tg not in ADMIN_IDS and any(l.startswith(str(uid_tg)) for l in lines):
        try: await update.callback_query.answer("شما قبلاً یک کانفیگ دریافت کرده‌اید.",show_alert=True)
        except telegram.error.BadRequest: pass
        return

    existing_indices = set()
    for line in lines:
        try:
            name_part = line.split(',')[1]
            if name_part.startswith('vless'):
                existing_indices.add(int(name_part.replace('vless', '')))
        except (IndexError, ValueError):
            continue

    idx = 1
    while idx in existing_indices:
        idx += 1
    name = f"vless{idx}"
    
    port=free_port(BASE_PORT+idx)
    uid,cfg=make_json(name,port); run_container(name,cfg,port)
    
    # ✨ قابلیت جدید: ذخیره نام و یوزرنیم کاربر در فایل وضعیت
    first_name = (user.first_name or "").replace(",", "") # حذف کاما برای جلوگیری از خرابی فایل
    username = user.username or ""
    new_line = f"{uid_tg},{name},{port},{first_name},{username}"
    STATUS_FILE.write_text("\n".join(lines + [new_line]))

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

    user_info = f"نام: {first_name}"
    if username:
        user_info += f" | یوزرنیم: @{username}"
    
    safe_user_info = escape_markdown(user_info, version=2)
    safe_name = escape_markdown(name, version=2)
    safe_user_id = escape_markdown(str(user.id), version=2)

    admin_message = (
        f"✅ *کانفیگ جدید ساخته شد*\n\n"
        f"👤 *توسط کاربر:*\n{safe_user_info}\n"
        f"آیدی عددی: `{safe_user_id}`\n"
        f"🔗 *کانفیگ \\({safe_name}\\):*"
    )
    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(chat_id=admin_id, text=admin_message, parse_mode="MarkdownV2")
            await ctx.bot.send_message(chat_id=admin_id, text=link) 
        except telegram.error.TelegramError as e:
            print(f"ارسال پیام به ادمین {admin_id} با خطا مواجه شد: {e}")


async def cb_myconfig(update: Update, ctx: CallbackContext):
    user_id = update.effective_user.id
    if not STATUS_FILE.exists():
        await update.callback_query.message.reply_text("هنوز هیچ کانفیگی ساخته نشده است.")
        return

    lines = STATUS_FILE.read_text().splitlines()
    user_configs = []
    is_admin = user_id in ADMIN_IDS

    for line in lines:
        parts = line.split(',')
        if len(parts) < 3: continue
        
        line_user_id, name, port = parts[0], parts[1], parts[2]
        
        if is_admin:
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
    if is_admin:
        final_message = "📋 **لیست تمام کانفیگ‌های ساخته شده:**\n\n" + final_message

    await update.callback_query.message.reply_text(final_message, parse_mode="Markdown")
    await update.callback_query.answer()


async def cb_showlist(update:Update,ctx:CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        try: await update.callback_query.answer("شما اجازه دسترسی ندارید.",show_alert=True)
        except telegram.error.BadRequest: pass; return
    
    # ✨ قابلیت جدید: خواندن اطلاعات کاربران برای نمایش در لیست
    user_map = {}
    if STATUS_FILE.exists():
        for line in STATUS_FILE.read_text().splitlines():
            parts = line.split(',')
            if len(parts) >= 2:
                name = parts[1]
                # سازگاری با فرمت قدیمی و جدید
                if len(parts) >= 5:
                    first_name = parts[3]
                    username = f"(@{parts[4]})" if parts[4] else ""
                    user_map[name] = f"{first_name} {username}".strip()
                else:
                    user_map[name] = "کاربر نامشخص"

    conts = list_containers()
    up_count = sum(1 for c in conts if c['state'] == 'Up')
    total_count = len(conts)
    header = f"📊 **وضعیت کانتینرها**\nتعداد کل: {total_count} | تعداد فعال (Up): {up_count}\n\n"
    
    list_items = []
    for c in conts:
        # ✨ نمایش اطلاعات کاربر در کنار مشخصات کانفیگ
        user_display = user_map.get(c['name'], "کاربر نامشخص")
        list_items.append(f"◾️ `{c['name']}` | **{c['state']}**\n    👤 {user_display}")

    list_text = "\n".join(list_items) or "هیچ کانتینری یافت نشد."
    
    await update.callback_query.message.reply_text(header + list_text, parse_mode="Markdown", reply_markup=kb_list(conts))


async def cb_action(update:Update,ctx:CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        try: await update.callback_query.answer("شما اجازه دسترسی ندارید.",show_alert=True)
        except telegram.error.BadRequest: pass; return
        
    _,act,name=update.callback_query.data.split("|")
    if act!="refresh" and not container_exists(name):
        try: await update.callback_query.answer("کانتینر یافت نشد.",show_alert=True)
        except telegram.error.BadRequest: pass; return
        
    if act=="start": sh(f"docker start {name}")
    elif act=="stop": sh(f"docker stop {name}")
    elif act=="del":
        sh(f"docker rm -f {name}"); cfg=CONFIG_DIR/f"{name}.json"; cfg.unlink(missing_ok=True)
        if STATUS_FILE.exists():
            lines = STATUS_FILE.read_text().splitlines()
            lines_to_keep = []
            for line in lines:
                parts = line.split(',')
                # سازگاری با فرمت‌های مختلف فایل وضعیت
                if len(parts) >= 2 and parts[1] == name:
                    continue
                lines_to_keep.append(line)
            STATUS_FILE.write_text("\n".join(lines_to_keep))

    # After action, refresh the list
    await cb_showlist(update, ctx)
    await update.callback_query.answer(f"عملیات {act} برای {name} انجام شد.")


async def cb_ack(update:Update,ctx:CallbackContext):
    try: await update.callback_query.answer("موفق باشید!",show_alert=False)
    except telegram.error.BadRequest: pass

# --- Main Function and Bot Execution ---
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
