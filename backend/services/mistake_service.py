"""错题收藏服务。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from backend.models import MistakeItem, SessionLocal, db_session


class MistakeService:
    """错题收藏管理服务。"""

    VALID_STATUS = {"new", "reviewing", "mastered"}
    VALID_SOURCE = {"manual_favorite", "auto_low_score"}

    @staticmethod
    def upsert_favorite(
        owner_address: str,
        *,
        qa_id: str,
        session_id: str,
        session_name: str | None,
        room_id: str,
        room_name: str | None,
        question_text: str,
        answer_text: str | None,
        question_category: str | None,
        answer_score: float | None,
        source: str = "manual_favorite",
    ) -> tuple[MistakeItem, bool]:
        normalized_source = source if source in MistakeService.VALID_SOURCE else "manual_favorite"
        with db_session() as session:
            existing = session.execute(
                select(MistakeItem).where(
                    MistakeItem.owner_address == owner_address,
                    MistakeItem.qa_id == qa_id,
                )
            ).scalar_one_or_none()

            if existing:
                existing.session_id = session_id
                existing.session_name = session_name
                existing.room_id = room_id
                existing.room_name = room_name
                existing.question_text_snapshot = question_text
                existing.answer_text_snapshot = answer_text
                existing.question_category = question_category
                existing.answer_score_snapshot = answer_score
                existing.source = normalized_source
                return existing, False

            item = MistakeItem(
                id=str(uuid.uuid4()),
                owner_address=owner_address,
                qa_id=qa_id,
                session_id=session_id,
                session_name=session_name,
                room_id=room_id,
                room_name=room_name,
                question_text_snapshot=question_text,
                answer_text_snapshot=answer_text,
                question_category=question_category,
                answer_score_snapshot=answer_score,
                source=normalized_source,
                status="new",
                review_count=0,
                last_reviewed_at=None,
            )
            session.add(item)
            return item, True

    @staticmethod
    def remove_favorite(owner_address: str, qa_id: str) -> bool:
        with db_session() as session:
            deleted = session.execute(
                delete(MistakeItem).where(
                    MistakeItem.owner_address == owner_address,
                    MistakeItem.qa_id == qa_id,
                )
            ).rowcount
        return bool(deleted)

    @staticmethod
    def is_favorited(owner_address: str, qa_id: str) -> bool:
        with SessionLocal() as session:
            item = session.execute(
                select(MistakeItem.id).where(
                    MistakeItem.owner_address == owner_address,
                    MistakeItem.qa_id == qa_id,
                )
            ).first()
        return item is not None

    @staticmethod
    def list_items(
        owner_address: str,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[MistakeItem]:
        with SessionLocal() as session:
            stmt = select(MistakeItem).where(MistakeItem.owner_address == owner_address)
            if status:
                stmt = stmt.where(MistakeItem.status == status)
            if category:
                stmt = stmt.where(MistakeItem.question_category == category)
            if keyword:
                key = f"%{keyword.strip()}%"
                stmt = stmt.where(MistakeItem.question_text_snapshot.like(key))
            stmt = stmt.order_by(MistakeItem.created_at.desc())
            return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get_item(item_id: str, owner_address: str) -> Optional[MistakeItem]:
        with SessionLocal() as session:
            return session.execute(
                select(MistakeItem).where(
                    MistakeItem.id == item_id,
                    MistakeItem.owner_address == owner_address,
                )
            ).scalar_one_or_none()

    @staticmethod
    def update_item(
        item_id: str,
        owner_address: str,
        *,
        status: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[MistakeItem]:
        with db_session() as session:
            item = session.execute(
                select(MistakeItem).where(
                    MistakeItem.id == item_id,
                    MistakeItem.owner_address == owner_address,
                )
            ).scalar_one_or_none()
            if not item:
                return None

            if status is not None:
                normalized_status = status.strip().lower()
                if normalized_status not in MistakeService.VALID_STATUS:
                    raise ValueError("status 必须是 new/reviewing/mastered")
                item.status = normalized_status

            if note is not None:
                item.note = note.strip()[:1000] or None
            return item

    @staticmethod
    def record_review(item_id: str, owner_address: str) -> Optional[MistakeItem]:
        with db_session() as session:
            item = session.execute(
                select(MistakeItem).where(
                    MistakeItem.id == item_id,
                    MistakeItem.owner_address == owner_address,
                )
            ).scalar_one_or_none()
            if not item:
                return None
            item.review_count = int(item.review_count or 0) + 1
            item.last_reviewed_at = datetime.utcnow()
            if item.status == "new":
                item.status = "reviewing"
            return item

    @staticmethod
    def build_stats(items: List[MistakeItem]) -> Dict[str, Any]:
        category_counts: Dict[str, int] = {}
        status_counts = {"new": 0, "reviewing": 0, "mastered": 0}
        for item in items:
            status = (item.status or "new").lower()
            if status in status_counts:
                status_counts[status] += 1
            category = (item.question_category or "未分类").strip() or "未分类"
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            "total": len(items),
            "status_counts": status_counts,
            "category_counts": category_counts,
            "mastered_rate": round((status_counts["mastered"] / len(items) * 100.0), 1) if items else 0.0,
        }

    @staticmethod
    def to_dict(item: MistakeItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "owner_address": item.owner_address,
            "qa_id": item.qa_id,
            "session_id": item.session_id,
            "session_name": item.session_name,
            "room_id": item.room_id,
            "room_name": item.room_name,
            "question_text": item.question_text_snapshot,
            "answer_text": item.answer_text_snapshot,
            "question_category": item.question_category,
            "answer_score": item.answer_score_snapshot,
            "source": item.source,
            "status": item.status,
            "note": item.note,
            "review_count": int(item.review_count or 0),
            "last_reviewed_at": item.last_reviewed_at.isoformat() if item.last_reviewed_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
