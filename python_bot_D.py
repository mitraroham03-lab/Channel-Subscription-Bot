import os
import telebot
import razorpay
import hmac
import hashlib
import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, jsonify
from threading import Thread

# --- RENDER KEEP-ALIVE & WEBHOOK SERVER ---
app = Flask('')

@app.route('/')
def home(): 
    return "Bot is running and healthy!"

@app.route('/webhook', methods=['POST'])
def webhook():
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    data = request.data
    
    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        data,
        hashlib.sha256
    ).hexdigest()

    if webhook_signature != expected_signature:
        return jsonify({"status": "unauthorized"}), 401

    event_json = json.loads(data)
    if event_json['event'] == 'payment_link.paid':
        notes = event_json['payload']['payment_link']['entity']['notes']
        user_id = int(notes['user_id'])
        ch_id = int(notes['channel_id'])
        mins = int(notes['duration'])

        expiry_date = datetime.now() + timedelta(minutes=mins)
        
        try:
            invite_link = bot.create_chat_invite_link(
                ch_id, 
                member_limit=1, 
                expire_date=int(expiry_date.timestamp())
            ).invite_link

            users_col.insert_one({
                "user_id": user_id,
                "channel_id": ch_id,
                "expiry": expiry_date.timestamp()
            })

            bot.send_message(user_id, f"✅ *Payment Verified!*\n\nYour invite link is ready. It will expire in {mins} minutes.\n\n[Join Channel]({invite_link})", parse_mode="Markdown")
            bot.send_message(ADMIN_ID, f"💰 *Auto-Approved:* User {user_id} paid for {mins} mins.")
        except Exception as e:
            print(f"Error in Webhook Process: {e}")

    return jsonify({"status": "ok"}), 200

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_web).start()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = os.getenv('RAZORPAY_WEBHOOK_SECRET')

# --- CUSTOMIZABLE DISCLAIMER ---
DISCLAIMER_TEXT = """
⚠️ **IMPORTANT LEGAL DISCLAIMER AND TERMS OF SALE**

This document constitutes the full terms and conditions governing the sale and use of the digital product being offered.

**Nature of the Product**  
The Seller (a college student) is offering a bundle of **37 Python scripts** (the "Code") developed solely as part of the Seller’s personal learning and educational journey. The Code implements experimental strategy ideas inspired by publicly available YouTube educational content.  

The Code is provided **strictly as educational and experimental source code only**. It is **not** financial advice, investment advice, trading signals, a trading system, a recommendation to trade, or any form of advisory service. The Seller does not operate as a SEBI-registered Research Analyst, Investment Advisor, or any other regulated financial service provider.

**No Performance or Suitability Guarantees**  
- The Seller makes **no representations or warranties** whatsoever regarding the Code, including but not limited to its accuracy, reliability, completeness, fitness for any particular purpose, merchantability, or potential profitability.  
- Algorithmic trading and the use of any automated scripts involve **significant and substantial risk of loss**. You may lose some, all, or more than your invested capital.  
- Past performance (if any examples are shown), theoretical strategies, or educational concepts do **not** indicate or guarantee future results. Real-market performance is affected by numerous factors including (but not limited to) market volatility, slippage, transaction costs, brokerage fees, taxes, execution delays, liquidity issues, technical failures, internet connectivity, power outages, and changing regulatory or market conditions.  
- No backtests, paper trading results, or live performance data are provided or implied as reliable indicators.

**Risk Acknowledgment and Buyer’s Responsibility**  
By purchasing and using the Code, you acknowledge and agree that:  
- You are solely responsible for all decisions regarding the modification, testing, deployment, and use of the Code.  
- You must conduct your own thorough due diligence, including extensive testing in paper trading / simulation mode only, before considering any live trading.  
- You must ensure full compliance with all applicable laws and regulations in your jurisdiction.
- The Seller bears **no responsibility** for any trading outcomes, financial losses, technical issues, or other damages arising from the use or misuse of the Code.

**Limitation of Liability**  
To the maximum extent permitted by law (including under the Indian Consumer Protection Act, Information Technology Act, Contract Act, and equivalent laws in other jurisdictions):  
- The Seller shall **not** be liable for any direct, indirect, incidental, special, consequential, punitive, or exemplary damages, including but not limited to loss of profits, loss of capital, loss of data, business interruption, or any other financial or non-financial loss.  
- The Seller’s total liability, if any, shall be strictly limited to the amount actually paid by you for the Code.  
- This limitation applies even if the Seller has been advised of the possibility of such damages.

**Non-Refundable Digital Product**  
This is a **non-refundable digital product**. Once the download link or files are provided, no refunds, cancellations, or returns will be issued for any reason, including dissatisfaction, non-use, or perceived lack of performance.

**Intellectual Property and Usage Rights**  
The Code is provided under a personal, non-exclusive, non-transferable license for your own educational and experimental use only. You may modify it for personal learning purposes. You may **not** resell, redistribute, sublicense, or commercially exploit the Code or any derivative works without the Seller’s prior written permission.

**Governing Law and Dispute Resolution**  
These terms shall be governed by the laws of India. Any disputes shall be subject to the exclusive jurisdiction of the courts in [your city/state, India]. For international buyers, you agree to submit to Indian jurisdiction or resolve disputes amicably.

If you do not agree with any part of these terms, you must not purchase or use the Code.

**Seller Details**  
Seller: Roham (college student)  
This is a personal educational project. The Seller is **not** a SEBI-registered entity or licensed financial professional in any jurisdiction.

By clicking “I Accept” or proceeding with payment, you confirm that:  
- You have read, understood, and fully agree to all the above terms and disclaimers.  
- You purchase the Code at your own risk and with full awareness of the high risks involved.
"""

bot = telebot.TeleBot(BOT_TOKEN)
client_rzp = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
db = MongoClient(MONGO_URI)['sub_management']
channels_col = db['channels']
users_col = db['users']

# --- BOT LOGIC ---

@bot.message_handler(commands=['start'])
def start_handler(message):
    args = message.text.split()
    if len(args) > 1:
        try:
            ch_id = int(args[1])
            ch_data = channels_col.find_one({"channel_id": ch_id})
            if ch_data:
                markup = InlineKeyboardMarkup()
                for mins, price in ch_data['plans'].items():
                    # Updated display to USD ($)
                    markup.add(InlineKeyboardButton(f"{mins} mins - ${price}", callback_data=f"buy_{ch_id}_{mins}"))
                bot.send_message(message.chat.id, f"Welcome! Select a plan to join *{ch_data['name']}*:", reply_markup=markup, parse_mode="Markdown")
                return
        except (ValueError, TypeError): pass
    bot.send_message(message.chat.id, "Welcome to the Subscription Bot.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def show_disclaimer(call):
    """Intercepts the plan selection to show the disclaimer."""
    _, ch_id, mins = call.data.split("_")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ I Agree & Proceed", callback_data=f"agree_{ch_id}_{mins}"))
    markup.add(InlineKeyboardButton("❌ Decline", callback_data="cancel_purchase"))
    
    bot.edit_message_text(
        DISCLAIMER_TEXT,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("agree_"))
def create_payment(call):
    """Generates the actual payment link in USD after user agrees to terms."""
    _, ch_id, mins = call.data.split("_")
    ch_data = channels_col.find_one({"channel_id": int(ch_id)})
    
    if not ch_data:
        bot.answer_callback_query(call.id, "❌ Error: Channel not found.")
        return

    price = ch_data['plans'][mins]

    try:
        # Amount converted to cents for USD
        payment_link = client_rzp.payment_link.create({
            "amount": int(float(price) * 100), 
            "currency": "USD",
            "description": f"Access to {ch_data['name']} for {mins} mins",
            "notes": {"user_id": str(call.from_user.id), "channel_id": ch_id, "duration": mins},
            "callback_url": f"https://t.me/{(bot.get_me().username)}",
            "callback_method": "get"
        })

        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("💳 Pay Now ($)", url=payment_link['short_url']))
        bot.edit_message_text(
            f"✅ *Terms Accepted*\n\n💰 *Plan:* {mins} Minutes\n💵 *Total:* ${price} USD\n\nClick the button below to pay. Access is granted instantly after payment.", 
            call.message.chat.id, 
            call.message.message_id, 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Razorpay Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error creating payment link.")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_purchase")
def cancel_handler(call):
    bot.edit_message_text("❌ Purchase cancelled. You must agree to the terms to join.", call.message.chat.id, call.message.message_id)

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['add'])
def add_channel(message):
    if message.from_user.id != ADMIN_ID: return
    msg = bot.reply_to(message, "Forward a message from the private channel here.")
    bot.register_next_step_handler(msg, process_forward)

def process_forward(message):
    if not message.forward_from_chat:
        bot.reply_to(message, "Error: Forward a message from the channel.")
        return
    ch_id = message.forward_from_chat.id
    ch_name = message.forward_from_chat.title
    msg = bot.reply_to(message, f"Channel: {ch_name}\nEnter plans in format `Minutes:Price` (e.g., `1440:5.99, 10080:25`) \nNote: Prices are in USD.")
    bot.register_next_step_handler(msg, lambda m: save_channel(m, ch_id, ch_name))

def save_channel(message, ch_id, ch_name):
    try:
        plans = {p.split(":")[0].strip(): p.split(":")[1].strip() for p in message.text.split(",")}
        channels_col.update_one({"channel_id": ch_id}, {"$set": {"name": ch_name, "plans": plans}}, upsert=True)
        bot.reply_to(message, f"✅ Configured! Link: `https://t.me/{bot.get_me().username}?start={ch_id}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "Invalid format. Use `Mins:Price, Mins:Price`.")

# --- SCHEDULER (KICKING) ---

def kick_expired_users():
    now = datetime.now().timestamp()
    expired_users = users_col.find({"expiry": {"$lte": now}})
    for user in expired_users:
        try:
            bot.ban_chat_member(user['channel_id'], user['user_id'])
            bot.unban_chat_member(user['channel_id'], user['user_id'])
            bot.send_message(user['user_id'], "⚠️ Your subscription has expired. Use the original link to renew.")
            users_col.delete_one({"_id": user['_id']})
        except: pass

# --- STARTUP ---
if __name__ == '__main__':
    keep_alive()
    scheduler = BackgroundScheduler()
    scheduler.add_job(kick_expired_users, 'interval', minutes=1)
    scheduler.start()
    bot.infinity_polling()