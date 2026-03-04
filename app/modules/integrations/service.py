import csv
import io
import uuid
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.cases.models import Case
from app.core.enums import CaseOutcome, CaseStatus, AuditAction, TargetType
from app.modules.audit.service import log

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = {"student_id", "outcome", "visit_date", "notes"}

async def import_hospital_csv(
    db: AsyncSession,
    csv_bytes: bytes,
    imported_by_id: uuid.UUID,
) -> dict:
    """
    Parse and import hospital CSV data as historical Case records.
    Returns import summary: {total, imported, skipped, errors: list[str]}
    """
    summary = {
        "total": 0,
        "imported": 0,
        "skipped": 0,
        "errors": []
    }

    try:
        # Decode and parse CSV
        content = csv_bytes.decode("utf-8")
        f = io.StringIO(content)
        reader = csv.DictReader(f)
        
        # Validate columns
        if not EXPECTED_COLUMNS.issubset(set(reader.fieldnames or [])):
            missing = EXPECTED_COLUMNS - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        rows = list(reader)
        summary["total"] = len(rows)

        if len(rows) > 1000:
            raise ValueError("CSV exceeds maximum limit of 1000 rows.")

        # Pre-fetch existing users to avoid N+1 queries
        student_ids = [row["student_id"] for row in rows if row.get("student_id")]
        
        user_result = await db.execute(
            select(User).where(User.student_id.in_(student_ids))
        )
        users = list(user_result.scalars().all())
        user_map = {u.student_id: u.id for u in users}

        for i, row in enumerate(rows, start=1):
            try:
                # 1. Validate student_id
                student_id = row.get("student_id")
                user_id = user_map.get(student_id)
                if not user_id:
                    summary["skipped"] += 1
                    summary["errors"].append(f"Row {i}: Student ID '{student_id}' not found.")
                    continue

                # 2. Validate outcome
                raw_outcome = row.get("outcome", "").upper()
                try:
                    outcome = CaseOutcome(raw_outcome)
                except ValueError:
                    summary["skipped"] += 1
                    summary["errors"].append(f"Row {i}: Invalid outcome '{raw_outcome}'.")
                    continue

                # 3. Validate visit_date
                raw_date = row.get("visit_date")
                try:
                    visit_date = datetime.fromisoformat(raw_date)
                    if visit_date.tzinfo is None:
                        from datetime import timezone
                        visit_date = visit_date.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    summary["skipped"] += 1
                    summary["errors"].append(f"Row {i}: Invalid date format '{raw_date}'.")
                    continue

                # 4. Create historical case
                new_case = Case(
                    user_id=user_id,
                    flow_id=None,
                    status=CaseStatus.CLOSED,
                    outcome=outcome,
                    score=0,
                    answers_enc="HISTORICAL_IMPORT",
                    notes=row.get("notes", ""),
                    created_at=visit_date
                )
                db.add(new_case)
                summary["imported"] += 1

            except Exception as e:
                summary["skipped"] += 1
                summary["errors"].append(f"Row {i}: Unexpected error: {str(e)}")

        # Audit log the completion
        await log(
            db,
            actor_id=imported_by_id,
            action=AuditAction.IMPORT_COMPLETED,
            target_type=TargetType.IMPORT,
            target_id=None,
            diff={
                "total": summary["total"],
                "imported": summary["imported"],
                "skipped": summary["skipped"]
            }
        )
        
        await db.commit()
        return summary

    except Exception as e:
        logger.exception("Hospital CSV import failed")
        raise ValueError(str(e))
