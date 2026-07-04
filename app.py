from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
import datetime
import os

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")

class User(BaseModel):
    user_id: str
    days: int = 30

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

@app.get("/check/{user_id}")
async def check_subscription(user_id: str):
    db = await get_db()
    row = await db.fetchrow("SELECT exp_date, status FROM users WHERE id = $1", user_id)
    await db.close()
    if not row:
        return {"active": False, "reason": "user_not_found"}
    
    now = datetime.datetime.now()
    is_active = row['status'] == 'active' and row['exp_date'] > now
    return {
        "active": is_active,
        "expires": row['exp_date'].isoformat() if row['exp_date'] else None
    }

@app.post("/renew/{user_id}")
async def renew_subscription(user_id: str, days: int = 30):
    db = await get_db()
    new_date = datetime.datetime.now() + datetime.timedelta(days=days)
    await db.execute(
        "INSERT INTO users (id, exp_date, status) VALUES ($1, $2, 'active') "
        "ON CONFLICT (id) DO UPDATE SET exp_date = $2, status = 'active'",
        user_id, new_date
    )
    await db.close()
    return {"status": "renewed", "new_expires": new_date.isoformat()}

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
    return {"message": "Subscription API is running!"}
