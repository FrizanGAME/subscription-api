from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
import datetime
import os

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")

class SubscriptionUpdate(BaseModel):
    user_id: str
    days: int = 30
    plan_name: str = "basic"

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

@app.on_event("startup")
async def startup():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            exp_date TIMESTAMP,
            status TEXT DEFAULT 'active',
            plan_name TEXT DEFAULT 'basic'
        )
    """)
    await db.close()

@app.get("/check/{user_id}")
async def check_subscription(user_id: str):
    db = await get_db()
    row = await db.fetchrow(
        "SELECT exp_date, status, plan_name FROM users WHERE id = $1",
        user_id
    )
    await db.close()
    if not row:
        return {"active": False, "plan": None, "reason": "user_not_found"}
    
    now = datetime.datetime.now()
    is_active = row['status'] == 'active' and row['exp_date'] > now
    return {
        "active": is_active,
        "plan": row['plan_name'],
        "expires": row['exp_date'].isoformat() if row['exp_date'] else None
    }

@app.post("/renew")
async def renew_subscription(data: SubscriptionUpdate):
    db = await get_db()
    new_date = datetime.datetime.now() + datetime.timedelta(days=data.days)
    
    await db.execute("""
        INSERT INTO users (id, exp_date, status, plan_name)
        VALUES ($1, $2, 'active', $3)
        ON CONFLICT (id) DO UPDATE SET
            exp_date = $2,
            status = 'active',
            plan_name = $3
    """, data.user_id, new_date, data.plan_name)
    
    await db.close()
    return {
        "status": "renewed",
        "plan": data.plan_name,
        "new_expires": new_date.isoformat()
    }

@app.post("/change-plan")
async def change_plan(user_id: str, new_plan: str):
    db = await get_db()
    row = await db.fetchrow("SELECT exp_date FROM users WHERE id = $1", user_id)
    if not row:
        await db.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.execute(
        "UPDATE users SET plan_name = $1 WHERE id = $2",
        new_plan, user_id
    )
    await db.close()
    return {"status": "changed", "new_plan": new_plan}

@app.post("/check-expired")
async def check_expired():
    db = await get_db()
    now = datetime.datetime.now()
    await db.execute(
        "UPDATE users SET status = 'expired' WHERE exp_date < $1 AND status = 'active'",
        now
    )
    await db.close()
    return {"status": "checked", "message": "Expired users deactivated"}

@app.get("/")
async def root():
    return {"message": "Subscription API with plans is running!"}
