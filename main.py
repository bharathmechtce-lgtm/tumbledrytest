# main.py
from fastapi import FastAPI, Request
import asyncpg
import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ----------------------------------------------------------------------
# Startup log – verify env vars are loaded
# ----------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print("\n=== ENV CHECK ===")
    print(f"KEY:       {os.getenv('AZURE_OPENAI_KEY', 'MISSING')[:6]}...")
    print(f"ENDPOINT:  {os.getenv('AZURE_OPENAI_ENDPOINT', 'MISSING')}")
    print(f"DEPLOY:    {os.getenv('DEPLOYMENT_NAME', 'MISSING')}")
    print(f"DB_URL:    {os.getenv('DB_URL', 'MISSING')[:30]}...")
    print("==================\n")

# ----------------------------------------------------------------------
# AzureOpenAI client – Foundry requires `api_key` in headers
# ----------------------------------------------------------------------
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-02-01",
    http_client=None,   # use default
    timeout=30,         # prevent hanging
    default_headers={"api_key": os.getenv("AZURE_OPENAI_KEY")}
)

# ----------------------------------------------------------------------
# DB schema description for the LLM
# ----------------------------------------------------------------------
SCHEMA = """
Tables:
- customers(phone, name, city, total_spend)
- order_items(order_id, phone, sku, qty, price, order_date)
"""

# ----------------------------------------------------------------------
# Execute SQL on Neon
# ----------------------------------------------------------------------
async def run_sql(sql: str):
    try:
        conn = await asyncpg.connect(os.getenv("DB_URL"))
        rows = await conn.fetch(sql)
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]

# ----------------------------------------------------------------------
# Health-check (stops 405 errors from Twilio console)
# ----------------------------------------------------------------------
@app.get("/webhook")
async def webhook_get():
    return {"status": "ok", "detail": "POST /webhook for Twilio"}

# ----------------------------------------------------------------------
# Main webhook – receives SMS from Twilio
# ----------------------------------------------------------------------
@app.post("/webhook")
async def webhook(req: Request):
    form = await req.form()
    text = form.get("Body", "").strip()
    if not text:
        return {"text": "Empty message."}

    # ---- 1. Convert natural language → SQL -----------------
    prompt = f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'"
    try:
        resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        sql = resp.choices[0].message.content.strip().strip("`").strip()
    except Exception as e:
        return {"text": f"AI SQL error: {str(e)}"}

    if not sql.lower().startswith("select"):
        return {"text": "I can only answer data questions."}

    # ---- 2. Run SQL ---------------------------------------
    rows = await run_sql(sql)
    if not rows or "error" in rows[0]:
        err = rows[0].get("error", "No data")
        return {"text": f"Query error: {err}"}

    # ---- 3. Turn rows → natural-language answer ----------
    try:
        resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{
                "role": "user",
                "content": f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:"
            }],
            max_tokens=100,
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"AI answer error: {str(e)}"

    return {"text": answer}
