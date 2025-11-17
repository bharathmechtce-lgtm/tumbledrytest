from fastapi import FastAPI, Request
import os
import asyncpg
import requests

app = FastAPI()

# === ENV ===
load_dotenv()
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_WA = os.getenv("TWILIO_WA", "whatsapp:+14155238886")
DB_URL = os.getenv("DB_URL")

# === Neon Pool ===
pool = None

@app.on_event("startup")
async def startup_event():
    global pool
    print("=== ENV CHECK ===")
    print("KEY:", os.getenv("AZURE_OPENAI_KEY")[:5] + "...")
    print("ENDPOINT:", os.getenv("AZURE_OPENAI_ENDPOINT"))
    print("DEPLOY:", os.getenv("DEPLOYMENT_NAME"))
    print("DB_URL:", DB_URL[:30] + "...")
    print("==================")
    pool = await asyncpg.create_pool(DB_URL)

@app.on_event("shutdown")
async def close_pool():
    if pool:
        await pool.close()

# === Root (to avoid 404) ===
@app.get("/")
def home():
    return "Bot is LIVE. Send a message!"

# === Webhook ===
@app.post("/webhook")
async def webhook(request: Request):
    form = await request.form()
    msg = form.get("Body", "").strip()
    sender = form.get("From", "")

    print(f"INCOMING FROM {sender}: {msg}")

    # Pull name from Neon
    name = "DB Error"
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("SELECT name FROM users LIMIT 1;")
            name = row["name"] if row else "No Name"
        except Exception as e:
            print("DB ERROR:", e)

    # Reply
    reply = f"You said: {msg}\nDB says: {name}"

    # Send via Twilio
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = {
        "To": sender,
        "From": TWILIO_WA,
        "Body": reply
    }
    requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_TOKEN))

    return "OK"
