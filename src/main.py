from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sqlite3
import os

app = FastAPI(title="Bayou Blades Lead System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "leads.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        business_type TEXT,
        budget TEXT,
        temperature TEXT DEFAULT 'cold',
        score REAL DEFAULT 0.0,
        created_at TEXT,
        notes TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        message TEXT,
        direction TEXT,
        created_at TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    )''')
    conn.commit()
    conn.close()

init_db()

class Lead(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    business_type: Optional[str] = None
    budget: Optional[str] = None
    notes: Optional[str] = None

class LeadUpdate(BaseModel):
    temperature: Optional[str] = None
    notes: Optional[str] = None

def score_lead(budget: str) -> tuple:
    budget = (budget or "").lower()
    if any(x in budget for x in ["5k", "10k", "over", "large"]):
        return "hot", 0.9
    elif any(x in budget for x in ["1k", "2k", "3k", "medium"]):
        return "warm", 0.5
    else:
        return "cold", 0.2

@app.get("/")
def root():
    return {"status": "Bayou Blades Lead System is running!"}

@app.get("/api/dashboard/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE temperature='hot'")
    hot = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE temperature='warm'")
    warm = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE temperature='cold'")
    cold = c.fetchone()[0]
    conn.close()
    return {"total_leads": total, "hot": hot, "warm": warm, "cold": cold}

@app.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    if status:
        query += " AND temperature=?"
        params.append(status)
    if search:
        query += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    keys = ["id","name","email","phone","business_type","budget","temperature","score","created_at","notes"]
    return [dict(zip(keys, row)) for row in rows]

@app.post("/api/leads")
def create_lead(lead: Lead):
    temperature, score = score_lead(lead.budget or "")
    created_at = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO leads (name,email,phone,business_type,budget,temperature,score,created_at,notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (lead.name, lead.email, lead.phone, lead.business_type, lead.budget, temperature, score, created_at, lead.notes)
    )
    lead_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": lead_id, "temperature": temperature, "score": score, "message": "Lead created successfully"}

@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id=?", (lead_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    keys = ["id","name","email","phone","business_type","budget","temperature","score","created_at","notes"]
    return dict(zip(keys, row))

@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: int, update: LeadUpdate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if update.temperature:
        c.execute("UPDATE leads SET temperature=? WHERE id=?", (update.temperature, lead_id))
    if update.notes:
        c.execute("UPDATE leads SET notes=? WHERE id=?", (update.notes, lead_id))
    conn.commit()
    conn.close()
    return {"message": "Lead updated"}

@app.get("/api/leads/{lead_id}/conversation")
def get_conversation(lead_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM conversations WHERE lead_id=? ORDER BY created_at", (lead_id,))
    rows = c.fetchall()
    conn.close()
    keys = ["id","lead_id","message","direction","created_at"]
    return [dict(zip(keys, row)) for row in rows]

@app.post("/api/webhooks/twilio/sms")
async def twilio_webhook(From: str = "", Body: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM leads WHERE phone=?", (From,))
    lead = c.fetchone()
    if lead:
        c.execute(
            "INSERT INTO conversations (lead_id,message,direction,created_at) VALUES (?,?,?,?)",
            (lead[0], Body, "inbound", datetime.now().isoformat())
        )
        conn.commit()
    conn.close()
    return {"status": "received"}
