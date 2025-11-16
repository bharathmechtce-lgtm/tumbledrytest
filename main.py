from fastapi import FastAPI, Request
import asyncpg, os, json, requests

app = FastAPI()

# === CONFIG (ENV VARS) ===
DB_URL = os.getenv("DB_URL")
AI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AI_KEY = os.getenv("AZURE_OPENAI_KEY")
DEPLOY_NAME = os.getenv("DEPLOYMENT_NAME", "gpt4o-mini")

SCHEMA = "Tables: customers(phone, name, city, total_spend), order_items(order_id, phone, sku, qty, price, order_date)"

# === DB ===
async def run_sql(sql: str):
    try:
        conn = await asyncpg.connect(DB_URL)
        rows = await conn.fetch(sql)
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]

# === AI ===
def ai(prompt: str) -> str:
    url = f"{AI_ENDPOINT}openai/deployments/{DEPLOY_NAME}/chat/completions?api-version=2024-02-01"
    try:
        r = requests.post(url, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 150},
                          headers={"api-key": AI_KEY, "Content-Type": "application/json"}, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip().strip("`")
    except Exception as e:
        return f"AI Error: {e}"

# === ROUTES ===
@app.get("/webhook")
async def get():
    return {"status": "ok"}

@app.post("/webhook")
async def post(req: Request):
    form = await req.form()
    text = form.get("Body", "").strip()
    if not text: return {"text": "Empty"}

    # 1. Text → SQL
    sql = ai(f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'")
    if not sql.lower().startswith("select"): return {"text": "Only data questions."}

    # 2. Run SQL
    rows = await run_sql(sql)
    if not rows or "error" in rows[0]: return {"text": f"Error: {rows[0].get('error','No data')}"}

    # 3. SQL Result → Answer
    answer = ai(f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:")
    return {"text": answer}
