from fastapi import FastAPI, Request, Form
import asyncpg, os, json, requests
from dotenv import load_dotenv
import asyncio

load_dotenv()
app = FastAPI()

# Add missing DEPLOYMENT_NAME
os.environ['DEPLOYMENT_NAME'] = os.getenv('DEPLOYMENT_NAME', 'gpt4o-mini')

SCHEMA = """
Tables:
- customers(phone, name, city, total_spend)
- order_items(order_id, phone, sku, qty, price, order_date)
"""

async def run_sql(sql: str):
    db_url = os.getenv("DB_URL")
    if not db_url:
        return [{"error": "DB_URL missing"}]
    try:
        conn = await asyncpg.connect(db_url)
        rows = await conn.fetch(sql)
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]

def ai(prompt: str) -> str:
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    key = os.getenv('AZURE_OPENAI_KEY')
    deployment = os.getenv('DEPLOYMENT_NAME')
    
    if not all([endpoint, key, deployment]):
        return f"Missing env: endpoint={bool(endpoint)}, key={bool(key)}, deployment={deployment}"
    
    url = f"{endpoint}openai/deployments/{deployment}/chat/completions?api-version=2024-02-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": key
    }
    data = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip().strip("`").strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

@app.get("/webhook")
async def get():
    return {"status": "ok"}

@app.post("/webhook")
async def post(request: Request):
    form = await request.form()
    text = form.get("Body", "").strip()
    if not text:
        return {"text": "Empty message."}

    # Step 1: AI → SQL
    sql_prompt = f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'"
    sql = ai(sql_prompt)
    
    if not sql.lower().startswith("select"):
        return {"text": "Only data questions allowed."}

    # Step 2: Run SQL
    rows = await run_sql(sql)
    if not rows or "error" in rows[0]:
        return {"text": f"DB Error: {rows[0].get('error', 'No data')}"} 

    # Step 3: AI → Answer
    summary_prompt = f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines. Bold numbers:"
    answer = ai(summary_prompt)

    return {"text": answer}
