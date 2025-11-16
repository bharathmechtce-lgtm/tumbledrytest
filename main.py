from fastapi import FastAPI, Request
import asyncpg, os, json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# === AI CLIENT ===
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-02-01"
)

# === SCHEMA ===
SCHEMA = """
Tables:
- customers(phone, name, city, total_spend)
- order_items(order_id, phone, sku, qty, price, order_date)
"""

# === RUN SQL ===
async def run_sql(sql: str):
    try:
        conn = await asyncpg.connect(os.getenv("DB_URL"))
        result = await conn.fetch(sql)
        await conn.close()
        return [dict(row) for row in result]
    except Exception as e:
        return [{"error": str(e)}]

# === WEBHOOK ===
@app.post("/webhook")
async def webhook(req: Request):
    form = await req.form()
    text = form["Body"].strip()

    # Text → SQL
    prompt = f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'"
    sql = client.chat.completions.create(
        model=os.getenv("DEPLOYMENT_NAME"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    ).choices[0].message.content.strip().strip('`')

    if not sql.lower().startswith("select"):
        return {"text": "I can only answer data questions."}

    rows = await run_sql(sql)
    if not rows or "error" in rows[0]:
        return {"text": "No data found."}

    # Data → Answer
    answer = client.chat.completions.create(
        model=os.getenv("DEPLOYMENT_NAME"),
        messages=[{"role": "user", "content": f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:"}],
        max_tokens=100
    ).choices[0].message.content.strip()

    return {"text": answer}
