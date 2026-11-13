"""Dashboard widgets of Kasse (docs/dashboards.md in hubra-app/hubra).

kasse.tab     stat  what the viewer has on the Strichliste, not billed yet
kasse.claims  stat  expense claims waiting for the treasurer

They read as the viewing member.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from hubra.core.extensions import db

from .models import KasseClaim, KasseTick


def _chf(amount) -> str:
    return f"CHF {Decimal(amount or 0):,.2f}".replace(",", "'")


def _german(member) -> bool:
    return (getattr(member, "language", None) or "de").lower().startswith("de")


def tab(ctx, config: dict) -> dict:
    """The viewer's open Strichliste: amount and how many ticks."""
    if ctx.actor is None:
        return {"value": _chf(0), "sub": None, "path": "/app/kasse/tab"}
    total, ticks = db.session.execute(
        select(func.coalesce(func.sum(KasseTick.price * KasseTick.qty), 0), func.count())
        .where(KasseTick.member_id == ctx.actor.id)
        .where(KasseTick.settled_at.is_(None))
    ).one()
    word = ("Strich", "Striche") if _german(ctx.actor) else ("tick", "ticks")
    sub = f"{ticks} {word[ticks != 1]}"
    return {"value": _chf(total), "sub": sub, "path": "/app/kasse/tab"}


def claims(ctx, config: dict) -> dict:
    """Claims not paid yet (submitted or approved), with their total."""
    count, total = db.session.execute(
        select(func.count(), func.coalesce(func.sum(KasseClaim.amount), 0)).where(
            KasseClaim.status.in_(("submitted", "approved"))
        )
    ).one()
    return {"value": count, "sub": _chf(total), "path": "/app/kasse"}
