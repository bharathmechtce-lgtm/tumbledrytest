# main.py - FINAL WORKING VERSION
from fastapi import FastAPI, Request
import asyncpg, os, json
import requests  # <-- THIS WAS MISSING
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Startup log - SYNC
@app.on_event("startup")
def startup_event():
    print("\n=== ENV CHECK ===")
    for k in ["AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT", "DEPLOYMENT_NAME", "DB_URL"]:
        v = os.getenv(k)
        print(f"{k}: {v[:4] + '...' if v else 'MISSING'}")
    print("==================\n")

# Azure Client - Force api-key
client = AzureOpenAI(
    api_key="dummy",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-02-01",
    default_headers={"api-key": os.getenv("AZURE_OPENAI_KEY")}
)

SCHEMA = """
Tables:
- customers(phone, name, city, total_spend)
- order_items(order_id, phone, sku, qty, price, order_date)
"""

async def run_sql(sql: str):
    try:
        conn = await asyncpg.connect(os.getenv("DB_URL"))
        rows = await conn.fetch(sql)
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]

@app.get("/webhook")
async def get():
    return {"status": "ok"}

def call_ai(prompt: str):
    url = f"{os.getenv('AZURE_OPENAI_ENDPOINT')}openai/deployments/{os.getenv('DEPLOYMENT_NAME')}/chat/completions?api-version=2024-02-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": os.getenv("AZURE_OPENAI_KEY")
    }
    data = {"messages": [{"role": "user", "content": prompt}], "max_tokens": 150}
    resp = requests.post(url, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip().strip("`").strip()

@app.post("/webhook")
async def post(req: Request):
    text = (await req.form()).get("Body", "").strip()
    if not text: return {"text": "Empty"}

    prompt = f"{SCHEMA}\nConvert to SQL (SELECT only): '{text}'"
    try:
        sql = call_ai(prompt)
    except Exception as e:
        return {"text": f"AI SQL error: {str(e)}"}

    if not sql.lower().startswith("select"): return {"text": "Only data questions."}

    rows = await run_sql(sql)
    if not rows or "error" in rows[0]: return {"text": f"Error: {rows[0].get('error', 'No data')}"}

    prompt2 = f"Data: {json.dumps(rows[:5])}\nQuestion: {text}\nAnswer in 2 lines, bold numbers:"
    try:
        answer = call_ai(prompt2)
    except Exception as e:
        answer = f"AI answer error: {str(e)}"

    return {"text": answer}
