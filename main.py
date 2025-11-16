from fastapi import FastAPI, Request
import asyncpg, os, json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Startup: Print ENV
@app.on_event("startup")
async def startup_event():
    key = os.getenv("AZURE_OPENAI_KEY")
    ep = os.getenv("AZURE_OPENAI_ENDPOINT")
    dep = os.getenv("DEPLOYMENT_NAME")
    db = os.getenv("DB_URL")
    print("\n=== ENV CHECK ===")
    print(f"KEY: {key[:4] + '...' if key else 'MISSING'}")
    print(f"ENDPOINT: {ep or 'MISSING'}")
    print(f"DEPLOY: {dep or 'MISSING'}")
    print(f"DB_URL: {db[:30] + '...' if db else 'MISSING'}")
    print("==================\n")

# Azure OpenAI Client (Foundry Fix)
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-02-01",
    default_headers={"ms-azure-openai-key": os.getenv("AZURE_OPENAI_KEY")}
)

SCHEMA = """
Tables:
- customers(phone, name, city, total_spend)
- order_items(order_id, phone, sku, qty, price, order_date)
"""

# DB: Use Pool + Timeout (Fix connection error)
pool = None
@app.on_event("startup")
async def create_pool():
    global pool
    pool = await asyncpg.create_pool(
        os.getenv("DB_URL"),
        min_size=1,
        max_size=3,
        command_timeout=60
    )

@app.on_event("shutdown")
async def close_pool():
    global pool
    if pool:
        await pool.close()

async def run_sql(sql: str):
    global pool
    if not pool:
        return [{"error": "DB pool not ready"}]
    try:
        async with pool.acquire() as conn:
            result = await conn.fetch(sql)
        return [dict(row) for row in result]
    except Exception as e:
        return [{"error": str(e)}]

@app.get("/webhook")
async def webhook_get():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    form = await req.form()
    text = form.get("Body", "").strip()
    if not text:
        return {"text": "Empty message."}

    # 1. Text → SQL
    prompt = f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'"
    try:
        sql_resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            timeout=30
        )
        sql = sql_resp.choices[0].message.content.strip().strip("`").strip()
    except Exception as e:
        return {"text": f"AI SQL error: {str(e)}"}

    if not sql.lower().startswith("select"):
        return {"text": "I can only answer data questions."}

    # 2. Run SQL
    rows = await run_sql(sql)
    if not rows or "error" in rows[0]:
        err = rows[0].get("error", "No data")
        return {"text": f"Query error: {err}"}

    # 3. Data → Answer
    try:
        answer_resp = client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[{
                "role": "user",
                "content": f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:"
            }],
            max_tokens=100,
            timeout=30
        )
        answer = answer_resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"AI answer error: {str(e)}"

    return {"text": answer}
