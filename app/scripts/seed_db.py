import asyncio
import datetime
import uuid
import json
import logging
import traceback
import sqlalchemy.exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal, engine, Base
from app.core.enums import Role, FlowStatus, CaseOutcome, CaseStatus
from app.modules.auth.models import User
from app.modules.auth.service import pwd_context
from app.modules.flows.models import SymptomFlow
from app.modules.cases.models import Case
from app.modules.tokens.models import PrescriptionToken
from app.modules.audit.models import AuditLog

SAMPLE_FLOW = {
    "flow_id": "550e8400-e29b-41d4-a716-446655440000",
    "version": 1,
    "red_flags": ["q_chest_pain"],
    "start_node": "q1",
    "nodes": {
        "q1": {
            "type": "question",
            "text": "How long have your symptoms lasted?",
            "hint": "Include today",
            "options": [
                {"label": "Less than 1 day", "score": 5, "next": "q2"},
                {"label": "1 to 3 days", "score": 15, "next": "q2"},
                {"label": "More than 3 days", "score": 30, "next": "outcome_clinic"},
            ],
        },
        "q2": {
            "type": "question",
            "text": "Severity?",
            "options": [
                {"label": "Mild", "score": 5, "next": "outcome_self_care"},
                {"label": "Moderate", "score": 20, "next": "outcome_pharmacy"},
                {"label": "Severe", "score": 40, "next": "q_chest_pain"},
            ],
        },
        "q_chest_pain": {
            "type": "question",
            "text": "Chest pain?",
            "options": [
                {"label": "Yes", "score": 100, "next": "outcome_emergency"},
                {"label": "No", "score": 0, "next": "outcome_clinic"},
            ],
        },
        "outcome_self_care": {
            "type": "outcome",
            "result": "SELF_CARE",
            "issue_token": False,
            "message": "Rest and monitor your symptoms. Drink plenty of fluids.",
        },
        "outcome_pharmacy": {
            "type": "outcome",
            "result": "PHARMACY",
            "issue_token": True,
            "message": "Visit the campus pharmacy to collect recommended over-the-counter treatment.",
            "prescriptions": [
                {
                    "name": "Paracetamol 500mg",
                    "dose": "1–2 tablets every 4–6 hours as needed",
                    "instructions": "Maximum 8 tablets in 24 hours. Take with water."
                },
                {
                    "name": "Loratadine 10mg (Antihistamine)",
                    "dose": "1 tablet once daily",
                    "instructions": "Non-drowsy formula. Take in the morning."
                },
                {
                    "name": "Saline Nasal Spray",
                    "dose": "2 sprays per nostril, 2–3 times daily",
                    "instructions": "Shake before use. Safe for long-term use."
                }
            ]
        },
        "outcome_clinic": {
            "type": "outcome",
            "result": "CLINIC",
            "issue_token": False,
            "message": "Please book an appointment at the campus health clinic for a physical examination.",
        },
        "outcome_emergency": {
            "type": "outcome",
            "result": "EMERGENCY",
            "issue_token": False,
            "message": "IMMEDIATE ACTION REQUIRED: Please proceed to the nearest Emergency Department or call campus security.",
        },
    },
}

async def seed():
    async with engine.begin() as conn:
        print("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        print("Seeding users...")
        users = [
            User(email="student@campus.edu", password_hash=pwd_context.hash("password123"), role=Role.STUDENT, student_id="STU001"),
            User(email="clinician@campus.edu", password_hash=pwd_context.hash("password123"), role=Role.CLINICIAN),
            User(email="pharmacist@campus.edu", password_hash=pwd_context.hash("password123"), role=Role.PHARMACIST),
            User(email="admin@campus.edu", password_hash=pwd_context.hash("password123"), role=Role.ADMIN),
        ]
        db.add_all(users)
        await db.commit()
        for u in users: await db.refresh(u)
        student, clinician, pharmacist, admin = users

        print("Seeding active flow...")
        flow = SymptomFlow(
            name="General Winter Symptoms",
            version=1,
            rule_payload=SAMPLE_FLOW,
            status=FlowStatus.ACTIVE,
            created_by=admin.id,
            approved_by=admin.id,
            approved_at=datetime.datetime.now(datetime.UTC)
        )
        db.add(flow)
        await db.commit()
        await db.refresh(flow)

        print("Seeding example cases...")
        example_cases = [
            Case(user_id=student.id, flow_id=flow.id, answers_enc="{}", score=10, outcome=CaseOutcome.SELF_CARE, status=CaseStatus.TRIAGED),
            Case(user_id=student.id, flow_id=flow.id, answers_enc="{}", score=35, outcome=CaseOutcome.PHARMACY, status=CaseStatus.TRIAGED),
            Case(user_id=student.id, flow_id=flow.id, answers_enc="{}", score=145, outcome=CaseOutcome.EMERGENCY, status=CaseStatus.TRIAGED, is_flagged=True),
        ]
        db.add_all(example_cases)
        await db.commit()
        for c in example_cases: await db.refresh(c)

        print("Seeding prescription tokens...")
        from app.core.security import hash_token
        token_secret = "ABC123"
        token = PrescriptionToken(
            case_id=example_cases[1].id,
            token_hash=hash_token(token_secret),
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=7)
        )
        db.add(token)
        await db.commit()

        print(f"\nDatabase seeded successfully!")
        print(f"Student: student@campus.edu / password123")
        print(f"Clinician: clinician@campus.edu / password123")
        print(f"Pharmacist: pharmacist@campus.edu / password123")
        print(f"Admin: admin@campus.edu / password123")
        print(f"Sample Token Secret: {token_secret}")

if __name__ == "__main__":
    asyncio.run(seed())
