# main.py
from fastapi import FastAPI, Request
import asyncpg, os, json
from openai import AzureOpenAI
from dotenv import load_dotenv

# ----------------------------------------------------------------------
# Load .env (Render injects env vars, but load_dotenv works locally too)
# ----------------------------------------------------------------------
load_dotenv()

app = FastAPI()

# ----------------------------------------------------------------------
# Startup logging – proves env vars are present
# ----------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    key = os.getenv("AZURE_OPENAI_KEY")
    ep  = os.getenv("AZURE_OPENAI_ENDPOINT")
    dep = os.getenv("DEPLOYMENT_NAME")
    db  = os.getenv("DB_URL")
    print("\n=== ENV CHECK ===")
    print(f"KEY:       {key[:4] + '...' if key else 'MISSING'}")
    print(f"ENDPOINT:  {ep or 'MISSING'}")
    print(f"DEPLOY:    {dep or 'MISSING'}")
    print(f"DB_URL:    {db[:30] + '...' if db else 'MISSING'}")
    print("==================\n")

# ----------------------------------------------------------------------
# Azure OpenAI client
# ----------------------------------------------------------------------
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-02-01"
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
# Helper: run SQL against Neon
# ----------------------------------------------------------------------
async def run_sql(sql: str):
    try:
        conn = await asyncpg.connect(os.getenv("DB_URL"))
        result = await conn.fetch(sql)
        await conn.close()
        return [dict(row) for row in result]
    except Exception as e:
        return [{"error": str(e)}]

# ----------------------------------------------------------------------
# Health-check GET (stops 405 errors from Twilio console)
# ----------------------------------------------------------------------
@app.get("/webhook")
async def webhook_get():
    return {"status": "ok", "message": "POST /webhook for Twilio"}

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
        sql_resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        sql = sql_resp.choices[0].message.content.strip().strip("`").strip()
    except Exception as e:
        return {"text": f"AI SQL error: {str(e)}"}

    if not sql.lower().startswith("select"):
        return {"text": "I can only answer data questions."}

    # ---- 2. Execute SQL ------------------------------------
    rows = await run_sql(sql)
    if not rows or "error" in rows[0]:
        err = rows[0].get("error", "No data")
        return {"text": f"Query error: {err}"}

    # ---- 3. Convert rows → natural-language answer ----------
    try:
        answer_resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{
                "role": "user",
                "content": f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:"
            }],
            max_tokens=100,
        )
        answer = answer_resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"AI answer error: {str(e)}"

    return {"text": answer}
