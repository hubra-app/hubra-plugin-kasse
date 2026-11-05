"""Kasse API: /api/v1/app/kasse.

GET    /options                       what the caller may do, categories
GET    /claims                        the caller's expense claims
GET    /claims/all?show=open|all      everyone's (treasurer)
POST   /claims                        multipart: title, amount, spentOn, notes?, iban?, receipt
GET    /claims/<id>/receipt           the receipt (owner or treasurer)
DELETE /claims/<id>                   owner while submitted, or treasurer
POST   /claims/<id>/decide            {approve, note?}
POST   /claims/<id>/pay               {categoryId?, method?, paidOn?}: books the expense
GET    /products                      what can go on the tab
POST   /products                      {name, price}
PATCH  /products/<id>                 {name?, price?, active?, position?}
DELETE /products/<id>
GET    /products/qr.pdf?link=         the codes for the fridge
GET    /tab                           the caller's open ticks and total
POST   /tab                           {productId, qty?, memberId? (treasurer)}
DELETE /tab/<id>                      own tick within 15 minutes, or treasurer
GET    /tab/members                   open totals per member (treasurer)
POST   /tab/settle                    {categoryId?, dueDays?}: one invoice per member
GET    /orders                        collective orders
POST   /orders                        {title, deadline, description?, supplier?, items}
GET    /orders/<id>                   with the caller's lines; all lines for the board
PATCH  /orders/<id>                   same fields; items only before anyone ordered
DELETE /orders/<id>
PUT    /orders/<id>/mine              {lines: [{itemId, size?, qty}]} while open
POST   /orders/<id>/close             {reopen?}
GET    /orders/<id>/list.csv          the list for the supplier
POST   /orders/<id>/bill              {categoryId?, dueDays?}: one invoice per member
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, jsonify, request, send_file
from sqlalchemy import func, select

from hubra.core import files as store
from hubra.core.auth.helpers import get_current_member
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.finance import Invoice, TransactionCategory
from hubra.core.models.member import Member
from hubra.core.permissions import (
    member_has_permission,
    permission_required,
    require_member,
)
from hubra.core.utils import log_audit

from .models import (
    KasseClaim,
    KasseOrder,
    KasseOrderItem,
    KasseOrderLine,
    KasseProduct,
    KasseTick,
)
from .notify import notify

kasse_bp = Blueprint("kasse_bp", __name__)

OWNER = "kasse"
CLAIMS_READ = "kasse.claims.read"
CLAIMS = "kasse.claims.update"
TAB = "kasse.tab.update"
ORDERS = "kasse.orders.update"
# A member can take back a tick this long after making it.
UNDO = timedelta(minutes=15)
METHODS = ("IBAN", "Cash", "Twint", "Card")
RECEIPT_TYPES = ("image/", "application/pdf")


class Invalid(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@kasse_bp.errorhandler(Invalid)
def _invalid(exc: Invalid):
    return api_error("VALIDATION_ERROR", exc.message, 400)


# ── Reading the body ─────────────────────────────────────────────────────────


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _text(data, key: str, limit: int, required: bool = False) -> str | None:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise Invalid(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise Invalid(f"{key} must be text")
    value = value.strip()
    if len(value) > limit:
        raise Invalid(f"{key} is longer than {limit} characters")
    return value


def _int(data, key: str, low: int, high: int, default=None) -> int | None:
    value = data.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise Invalid(f"{key} must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise Invalid(f"{key} must be a whole number") from None
    if not low <= number <= high:
        raise Invalid(f"{key} must be between {low} and {high}")
    return number


def _date(data, key: str, required: bool = False) -> date | None:
    value = data.get(key)
    if not value:
        if required:
            raise Invalid(f"{key} is required")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise Invalid(f"{key} must be a date (YYYY-MM-DD)") from None


def _money(data, key: str, required: bool = False, positive: bool = False):
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise Invalid(f"{key} is required")
        return None
    try:
        amount = Decimal(str(value).replace(",", ".").replace("'", "")).quantize(
            Decimal("0.01")
        )
    except InvalidOperation:
        raise Invalid(f"{key} must be an amount") from None
    if amount < 0 or amount >= Decimal("100000000"):
        raise Invalid(f"{key} is out of range")
    if positive and amount == 0:
        raise Invalid(f"{key} must be more than 0")
    return amount


def _bool(data, key: str) -> bool:
    value = data.get(key)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _iban(data) -> str | None:
    value = _text(data, "iban", 42)
    if value is None:
        return None
    iban = value.replace(" ", "").upper()
    if not (15 <= len(iban) <= 34 and iban[:2].isalpha() and iban[2:].isalnum()):
        raise Invalid("iban is not an IBAN")
    # The check digits (ISO 13616, mod 97).
    moved = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    if int(digits) % 97 != 1:
        raise Invalid("iban is not an IBAN (check digits)")
    return iban


def _category_id(data) -> int | None:
    value = _int(data, "categoryId", 1, 2**31 - 1)
    if value is not None and db.session.get(TransactionCategory, value) is None:
        raise Invalid("categoryId: no such category")
    return value


def _get(model, row_id: int):
    row = db.session.get(model, row_id)
    if row is None:
        return None, api_error("NOT_FOUND", "not found", 404)
    return row, None


# ── Output ───────────────────────────────────────────────────────────────────


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _names(ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        m.id: m.name
        for m in db.session.scalars(select(Member).where(Member.id.in_(ids)))
    }


def _can(member, key: str) -> bool:
    return bool(member) and member_has_permission(member, key)


def _claim(c: KasseClaim, names: dict) -> dict:
    return {
        "id": c.id,
        "memberId": c.member_id,
        "memberName": names.get(c.member_id or 0),
        "title": c.title,
        "amount": _num(c.amount),
        "spentOn": _iso(c.spent_on),
        "notes": c.notes,
        "iban": c.iban,
        "hasReceipt": bool(c.receipt_key),
        "receiptName": c.receipt_name,
        "receiptType": c.receipt_type,
        "status": c.status,
        "decidedByName": names.get(c.decided_by or 0),
        "decidedAt": _iso(c.decided_at),
        "decisionNote": c.decision_note,
        "transactionId": c.transaction_id,
        "paidAt": _iso(c.paid_at),
        "createdAt": _iso(c.created_at),
    }


def _product(p: KasseProduct) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "price": _num(p.price),
        "position": p.position,
        "active": p.active,
    }


def _tick(t: KasseTick, me: int, can_tab: bool, now: datetime) -> dict:
    created = (
        t.created_at
        if t.created_at.tzinfo
        else t.created_at.replace(tzinfo=timezone.utc)
    )
    return {
        "id": t.id,
        "productId": t.product_id,
        "name": t.name,
        "price": _num(t.price),
        "qty": t.qty,
        "total": _num(t.price * t.qty),
        "createdAt": _iso(t.created_at),
        "canUndo": t.invoice_id is None
        and (can_tab or (t.member_id == me and now - created <= UNDO)),
    }


def _sizes(item: KasseOrderItem) -> list[str]:
    return [s.strip() for s in (item.sizes or "").split(",") if s.strip()]


def _item(i: KasseOrderItem) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "price": _num(i.price),
        "sizes": _sizes(i),
    }


def _line(line: KasseOrderLine, names: dict, items: dict) -> dict:
    item = items.get(line.item_id)
    return {
        "id": line.id,
        "itemId": line.item_id,
        "itemName": item.name if item else "",
        "memberId": line.member_id,
        "memberName": names.get(line.member_id or 0),
        "size": line.size,
        "qty": line.qty,
        "price": _num(line.price),
        "total": _num(line.price * line.qty),
        "invoiceId": line.invoice_id,
    }


def _open(order: KasseOrder, today: date) -> bool:
    return order.status == "open" and order.deadline >= today


# ── Options ──────────────────────────────────────────────────────────────────


@kasse_bp.get("/options")
@require_member
def options():
    member = get_current_member()
    can = {
        "claimsRead": _can(member, CLAIMS_READ) or _can(member, CLAIMS),
        "claims": _can(member, CLAIMS),
        "tab": _can(member, TAB),
        "orders": _can(member, ORDERS),
    }
    out = {"can": can, "memberId": member.id}
    if can["claims"] or can["tab"] or can["orders"]:
        out["categories"] = [
            {"id": c.id, "name": c.name}
            for c in db.session.scalars(
                select(TransactionCategory).order_by(TransactionCategory.name)
            )
        ]
    return jsonify(out)


# ── Expense claims ───────────────────────────────────────────────────────────


@kasse_bp.get("/claims")
@require_member
def my_claims():
    member = get_current_member()
    rows = db.session.scalars(
        select(KasseClaim)
        .where(KasseClaim.member_id == member.id)
        .order_by(KasseClaim.created_at.desc())
        .limit(500)
    ).all()
    names = _names([c.member_id for c in rows] + [c.decided_by for c in rows])
    return jsonify([_claim(c, names) for c in rows])


def _treasurer(member, **_kw):
    return "treasurer" if _can(member, CLAIMS) else None


@kasse_bp.get("/claims/all")
@permission_required(
    "claims", "read", "See every member's expense claims", allow=_treasurer
)
def all_claims():
    query = select(KasseClaim).order_by(KasseClaim.created_at.desc())
    if request.args.get("show", "open") == "open":
        query = query.where(KasseClaim.status.in_(("submitted", "approved")))
    rows = db.session.scalars(query.limit(500)).all()
    names = _names([c.member_id for c in rows] + [c.decided_by for c in rows])
    return jsonify([_claim(c, names) for c in rows])


@kasse_bp.post("/claims")
@require_member
def create_claim():
    member = get_current_member()
    data = request.form if request.files or request.form else _body()
    claim = KasseClaim(
        member_id=member.id,
        title=_text(data, "title", 200, required=True),
        amount=_money(data, "amount", required=True, positive=True),
        spent_on=_date(data, "spentOn") or date.today(),
        notes=_text(data, "notes", 2000),
        iban=_iban(data),
        status="submitted",
    )
    if claim.spent_on > date.today():
        raise Invalid("spentOn lies in the future")
    upload = request.files.get("receipt")
    if upload is not None and upload.filename:
        blob = upload.read()
        kind = (upload.mimetype or "").lower()
        if not blob:
            raise Invalid("the receipt is empty")
        if not kind.startswith(RECEIPT_TYPES):
            raise Invalid("the receipt must be a photo or a PDF")
        try:
            stored = store.put(OWNER, blob, kind)
        except store.FileTooLarge as err:
            return api_error("FILE_TOO_LARGE", str(err), 413)
        except store.FileStoreError:
            return api_error(
                "FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503
            )
        claim.receipt_key = stored.key
        claim.receipt_name = upload.filename[:200]
        claim.receipt_type = kind[:100]
    db.session.add(claim)
    db.session.flush()
    log_audit(member.id, "kasse.claim.create", "KasseClaim", claim.id, claim.title)
    db.session.commit()
    return jsonify(_claim(claim, _names([member.id]))), 201


def _own_or(member, claim: KasseClaim, key: str) -> bool:
    return claim.member_id == member.id or _can(member, key)


@kasse_bp.get("/claims/<int:claim_id>/receipt")
@require_member
def claim_receipt(claim_id: int):
    member = get_current_member()
    claim, err = _get(KasseClaim, claim_id)
    if err:
        return err
    if not (_own_or(member, claim, CLAIMS_READ) or _can(member, CLAIMS)):
        return api_error("NOT_FOUND", "not found", 404)
    if not claim.receipt_key:
        return api_error("NOT_FOUND", "this claim has no receipt", 404)
    try:
        blob = store.read(claim.receipt_key)
    except store.FileNotFound:
        return api_error("NOT_FOUND", "the receipt is missing from the store", 404)
    except store.FileStoreError:
        return api_error(
            "FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503
        )
    return send_file(
        io.BytesIO(blob),
        mimetype=claim.receipt_type or "application/octet-stream",
        as_attachment=request.args.get("inline") != "1",
        download_name=claim.receipt_name or f"receipt-{claim.id}",
    )


@kasse_bp.delete("/claims/<int:claim_id>")
@require_member
def delete_claim(claim_id: int):
    member = get_current_member()
    claim, err = _get(KasseClaim, claim_id)
    if err:
        return err
    mine = claim.member_id == member.id and claim.status == "submitted"
    if not (mine or _can(member, CLAIMS)):
        return api_error(
            "FORBIDDEN", "only a claim not yet decided can be withdrawn", 403
        )
    if claim.status == "paid":
        return api_error("CLAIM_PAID", "a paid claim stays for the books", 409)
    if claim.receipt_key:
        try:
            store.remove(claim.receipt_key)
        except store.FileNotFound:
            pass
    log_audit(member.id, "kasse.claim.delete", "KasseClaim", claim.id, claim.title)
    db.session.delete(claim)
    db.session.commit()
    return "", 204


@kasse_bp.post("/claims/<int:claim_id>/decide")
@permission_required("claims", "update", "Approve, reject and pay expense claims")
def decide_claim(claim_id: int):
    member = get_current_member()
    claim, err = _get(KasseClaim, claim_id)
    if err:
        return err
    if claim.status == "paid":
        return api_error("CLAIM_PAID", "this claim is paid already", 409)
    data = _body()
    approve = _bool(data, "approve")
    note = _text(data, "note", 500)
    if not approve and not note:
        raise Invalid("say why the claim is rejected")
    claim.status = "approved" if approve else "rejected"
    claim.decided_by = member.id
    claim.decided_at = datetime.now(timezone.utc)
    claim.decision_note = note
    log_audit(
        member.id, f"kasse.claim.{claim.status}", "KasseClaim", claim.id, claim.title
    )
    if claim.member_id and claim.member_id != member.id:
        amount = f"{claim.amount:.2f}"
        notify(
            [claim.member_id],
            lambda de, t=claim.title, a=amount, ok=approve: (
                (f"Spesen {'genehmigt' if ok else 'abgelehnt'}: {t}", f"CHF {a}")
                if de
                else (
                    f"Expense claim {'approved' if ok else 'rejected'}: {t}",
                    f"CHF {a}",
                )
            ),
            "/app/kasse",
        )
    db.session.commit()
    names = _names([claim.member_id, claim.decided_by])
    return jsonify(_claim(claim, names))


@kasse_bp.post("/claims/<int:claim_id>/pay")
@permission_required("claims", "update", "Approve, reject and pay expense claims")
def pay_claim(claim_id: int):
    from hubra.api.finance.services import TransactionsService

    member = get_current_member()
    claim, err = _get(KasseClaim, claim_id)
    if err:
        return err
    if claim.status != "approved":
        return api_error(
            "CLAIM_NOT_APPROVED", "approve the claim before paying it", 409
        )
    data = _body()
    method = data.get("method") or ("IBAN" if claim.iban else "Cash")
    if method not in METHODS:
        raise Invalid(f"method must be one of {', '.join(METHODS)}")
    names = _names([claim.member_id])
    tx = TransactionsService.create(
        {
            "date": _date(data, "paidOn") or date.today(),
            "description": f"Spesen: {claim.title}"[:255],
            "category_id": _category_id(data),
            "member_id": claim.member_id,
            "payee_name": names.get(claim.member_id or 0),
            "amount": claim.amount,
            "method": method,
            "type": "expense",
        },
        member.id,
    )
    claim.status = "paid"
    claim.transaction_id = tx.id
    claim.paid_at = datetime.now(timezone.utc)
    if not claim.decided_by:
        claim.decided_by = member.id
        claim.decided_at = claim.paid_at
    if claim.member_id and claim.member_id != member.id:
        amount = f"{claim.amount:.2f}"
        notify(
            [claim.member_id],
            lambda de, t=claim.title, a=amount: (
                (f"Spesen ausbezahlt: {t}", f"CHF {a}")
                if de
                else (f"Expense claim paid: {t}", f"CHF {a}")
            ),
            "/app/kasse",
        )
    db.session.commit()
    names = _names([claim.member_id, claim.decided_by])
    return jsonify(_claim(claim, names))


# ── Products ─────────────────────────────────────────────────────────────────


@kasse_bp.get("/products")
@require_member
def list_products():
    rows = db.session.scalars(
        select(KasseProduct).order_by(KasseProduct.position, KasseProduct.name)
    )
    return jsonify([_product(p) for p in rows])


def _apply_product(p: KasseProduct, data: dict, partial: bool) -> None:
    if not partial or "name" in data:
        p.name = _text(data, "name", 120, required=True)
    if not partial or "price" in data:
        p.price = _money(data, "price", required=True)
    if "active" in data:
        p.active = _bool(data, "active")
    if "position" in data:
        p.position = _int(data, "position", 0, 10000, 0)


@kasse_bp.post("/products")
@permission_required("tab", "update", "Manage the tab and settle it")
def create_product():
    data = _body()
    last = db.session.scalar(select(func.max(KasseProduct.position))) or 0
    p = KasseProduct(active=True, position=last + 1)
    _apply_product(p, data, partial=False)
    db.session.add(p)
    db.session.commit()
    return jsonify(_product(p)), 201


@kasse_bp.patch("/products/<int:product_id>")
@permission_required("tab", "update", "Manage the tab and settle it")
def update_product(product_id: int):
    p, err = _get(KasseProduct, product_id)
    if err:
        return err
    _apply_product(p, _body(), partial=True)
    db.session.commit()
    return jsonify(_product(p))


@kasse_bp.delete("/products/<int:product_id>")
@permission_required("tab", "update", "Manage the tab and settle it")
def delete_product(product_id: int):
    p, err = _get(KasseProduct, product_id)
    if err:
        return err
    # Ticks keep their name and price, so the product can go.
    db.session.delete(p)
    db.session.commit()
    return "", 204


@kasse_bp.get("/products/qr.pdf")
@permission_required("tab", "update", "Manage the tab and settle it")
def products_qr():
    """?link=https://club.example/app/kasse/tab?tick= : the codes point there."""
    from . import qrsheet

    link = (request.args.get("link") or "").strip()
    if not link.startswith(("https://", "http://")) or len(link) > 300:
        raise Invalid("link must be the club app's address")
    rows = list(
        db.session.scalars(
            select(KasseProduct)
            .where(KasseProduct.active.is_(True))
            .order_by(KasseProduct.position, KasseProduct.name)
        )
    )
    german = (request.args.get("lang") or "de").startswith("de")
    pdf = qrsheet.sheet(rows, link, german)
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=request.args.get("inline") != "1",
        download_name="strichliste-qr.pdf",
    )


# ── The tab ──────────────────────────────────────────────────────────────────


def _open_ticks(member_id: int) -> list[KasseTick]:
    return list(
        db.session.scalars(
            select(KasseTick)
            .where(KasseTick.member_id == member_id)
            .where(KasseTick.invoice_id.is_(None))
            .order_by(KasseTick.created_at.desc())
        )
    )


def _tab(member_id: int, me: int, can_tab: bool) -> dict:
    now = datetime.now(timezone.utc)
    ticks = _open_ticks(member_id)
    total = sum((t.price * t.qty for t in ticks), Decimal("0"))
    return {
        "memberId": member_id,
        "total": _num(total),
        "ticks": [_tick(t, me, can_tab, now) for t in ticks],
    }


@kasse_bp.get("/tab")
@require_member
def my_tab():
    member = get_current_member()
    can_tab = _can(member, TAB)
    target = member.id
    if request.args.get("memberId") and can_tab:
        target = _int(request.args, "memberId", 1, 2**31 - 1)
    return jsonify(_tab(target, member.id, can_tab))


@kasse_bp.post("/tab")
@require_member
def tick():
    member = get_current_member()
    data = _body()
    product, err = _get(KasseProduct, _int(data, "productId", 1, 2**31 - 1) or 0)
    if err:
        return err
    if not product.active:
        return api_error("PRODUCT_INACTIVE", "this product is not on the tab", 409)
    target = member.id
    if data.get("memberId") not in (None, "", member.id):
        if not _can(member, TAB):
            return api_error("FORBIDDEN", "you may only tick on your own tab", 403)
        target = _int(data, "memberId", 1, 2**31 - 1)
        if db.session.get(Member, target) is None:
            raise Invalid("memberId: no such member")
    row = KasseTick(
        member_id=target,
        product_id=product.id,
        name=product.name,
        price=product.price,
        qty=_int(data, "qty", 1, 50, 1),
        created_by=member.id,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_tab(target, member.id, _can(member, TAB))), 201


@kasse_bp.delete("/tab/<int:tick_id>")
@require_member
def untick(tick_id: int):
    member = get_current_member()
    row, err = _get(KasseTick, tick_id)
    if err:
        return err
    can_tab = _can(member, TAB)
    if row.invoice_id is not None:
        return api_error("TICK_SETTLED", "this tick is on an invoice already", 409)
    created = (
        row.created_at
        if row.created_at.tzinfo
        else row.created_at.replace(tzinfo=timezone.utc)
    )
    own = row.member_id == member.id and datetime.now(timezone.utc) - created <= UNDO
    if not (own or can_tab):
        return api_error("FORBIDDEN", "a tick can be taken back for 15 minutes", 403)
    target = row.member_id
    db.session.delete(row)
    db.session.commit()
    return jsonify(_tab(target or member.id, member.id, can_tab))


def _open_totals() -> list[tuple[int, Decimal, int]]:
    rows = db.session.execute(
        select(
            KasseTick.member_id,
            func.sum(KasseTick.price * KasseTick.qty),
            func.sum(KasseTick.qty),
        )
        .where(KasseTick.invoice_id.is_(None))
        .where(KasseTick.member_id.isnot(None))
        .group_by(KasseTick.member_id)
    ).all()
    return [(m, Decimal(t or 0), int(n or 0)) for m, t, n in rows]


@kasse_bp.get("/tab/members")
@permission_required("tab", "update", "Manage the tab and settle it")
def tab_members():
    totals = _open_totals()
    names = _names([m for m, _, _ in totals])
    last = db.session.scalar(select(func.max(KasseTick.settled_at)))
    out = [
        {"memberId": m, "memberName": names.get(m), "total": _num(t), "count": n}
        for m, t, n in totals
        if t > 0
    ]
    out.sort(key=lambda r: (r["memberName"] or "").lower())
    return jsonify({"members": out, "lastSettled": _iso(last)})


def _invoice(
    member_id: int, amount: Decimal, text: str, data: dict, actor: int
) -> Invoice:
    from hubra.api.finance.services import InvoicesService

    today = date.today()
    due = today + timedelta(days=_int(data, "dueDays", 0, 365, 30))
    return InvoicesService.create(
        {
            "member_id": member_id,
            "issued": today,
            "due": due,
            "amount": amount,
            "purpose": "other",
            "description": text[:512],
            "category_id": _category_id(data),
        },
        actor,
    )


@kasse_bp.post("/tab/settle")
@permission_required("tab", "update", "Manage the tab and settle it")
def settle_tab():
    member = get_current_member()
    data = _body()
    now = datetime.now(timezone.utc)
    label = _text(data, "description", 200) or "Strichliste"
    count = 0
    total = Decimal("0")
    for member_id, amount, _n in _open_totals():
        if amount <= 0 or db.session.get(Member, member_id) is None:
            continue
        ticks = _open_ticks(member_id)
        invoice = _invoice(
            member_id, amount, f"{label} bis {now:%d.%m.%Y}", data, member.id
        )
        for t in ticks:
            t.invoice_id = invoice.id
            t.settled_at = now
        count += 1
        total += amount
    log_audit(member.id, "kasse.tab.settle", "KasseTick", None, f"{count} invoices")
    db.session.commit()
    return jsonify({"invoices": count, "total": _num(total)})


# ── Collective orders ────────────────────────────────────────────────────────


def _order(
    o: KasseOrder, me: int, manage: bool, today: date, full: bool = False
) -> dict:
    items = list(
        db.session.scalars(
            select(KasseOrderItem)
            .where(KasseOrderItem.order_id == o.id)
            .order_by(KasseOrderItem.position, KasseOrderItem.id)
        )
    )
    lines = list(
        db.session.scalars(
            select(KasseOrderLine)
            .where(KasseOrderLine.order_id == o.id)
            .order_by(KasseOrderLine.id)
        )
    )
    mine = [line for line in lines if line.member_id == me]
    out = {
        "id": o.id,
        "title": o.title,
        "description": o.description,
        "deadline": _iso(o.deadline),
        "supplier": o.supplier,
        "status": o.status,
        "open": _open(o, today),
        "billedAt": _iso(o.billed_at),
        "items": [_item(i) for i in items],
        "people": len({line.member_id for line in lines}),
        "pieces": sum(line.qty for line in lines),
        "total": _num(sum((line.price * line.qty for line in lines), Decimal("0"))),
        "myTotal": _num(sum((line.price * line.qty for line in mine), Decimal("0"))),
    }
    if full:
        by_id = {i.id: i for i in items}
        names = _names([line.member_id for line in lines])
        out["mine"] = [_line(line, names, by_id) for line in mine]
        if manage:
            out["lines"] = [_line(line, names, by_id) for line in lines]
            out["summary"] = _summary(items, lines)
    return out


def _summary(items, lines) -> list[dict]:
    """Pieces per item and size, for the supplier."""
    count: dict[tuple[int, str], int] = defaultdict(int)
    for line in lines:
        count[(line.item_id, line.size or "")] += line.qty
    out = []
    for item in items:
        sizes = _sizes(item) or [""]
        extra = sorted(s for (i, s) in count if i == item.id and s not in sizes)
        for size in [*sizes, *extra]:
            n = count.get((item.id, size), 0)
            if n:
                out.append(
                    {
                        "itemId": item.id,
                        "itemName": item.name,
                        "size": size or None,
                        "qty": n,
                    }
                )
    return out


def _apply_order(o: KasseOrder, data: dict, partial: bool) -> None:
    if not partial or "title" in data:
        o.title = _text(data, "title", 200, required=True)
    if not partial or "deadline" in data:
        o.deadline = _date(data, "deadline", required=True)
    if not partial or "description" in data:
        o.description = _text(data, "description", 5000)
    if not partial or "supplier" in data:
        o.supplier = _text(data, "supplier", 200)


def _apply_items(o: KasseOrder, data: dict) -> None:
    raw = data.get("items")
    if not isinstance(raw, list) or not raw:
        raise Invalid("an order needs at least one item")
    if len(raw) > 50:
        raise Invalid("at most 50 items")
    existing = {
        i.id: i
        for i in db.session.scalars(
            select(KasseOrderItem).where(KasseOrderItem.order_id == o.id)
        )
    }
    ordered = set(
        db.session.scalars(
            select(KasseOrderLine.item_id).where(KasseOrderLine.order_id == o.id)
        )
    )
    keep = set()
    for pos, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise Invalid("items must be a list of objects")
        item = existing.get(entry.get("id") or 0)
        if item is None:
            item = KasseOrderItem(order_id=o.id)
            db.session.add(item)
        name = _text(entry, "name", 200, required=True)
        price = _money(entry, "price", required=True)
        if item.id in ordered and price != item.price:
            raise Invalid(
                f"{item.name}: the price can't change once someone ordered it"
            )
        sizes = entry.get("sizes") or []
        if isinstance(sizes, str):
            sizes = sizes.split(",")
        sizes = [str(s).strip()[:40] for s in sizes if str(s).strip()]
        if len(sizes) > 30:
            raise Invalid("at most 30 sizes per item")
        item.name, item.price, item.sizes, item.position = (
            name,
            price,
            ", ".join(sizes) or None,
            pos,
        )
        if item.id:
            keep.add(item.id)
    for item_id, item in existing.items():
        if item_id not in keep:
            if item_id in ordered:
                raise Invalid(f"{item.name}: someone ordered it, so it stays")
            db.session.delete(item)


@kasse_bp.get("/orders")
@require_member
def list_orders():
    member = get_current_member()
    manage = _can(member, ORDERS)
    today = date.today()
    rows = db.session.scalars(
        select(KasseOrder).order_by(KasseOrder.deadline.desc(), KasseOrder.id.desc())
    )
    return jsonify([_order(o, member.id, manage, today) for o in rows])


@kasse_bp.post("/orders")
@permission_required("orders", "update", "Run collective orders")
def create_order():
    member = get_current_member()
    data = _body()
    o = KasseOrder(status="open", created_by=member.id)
    _apply_order(o, data, partial=False)
    db.session.add(o)
    db.session.flush()
    _apply_items(o, data)
    log_audit(member.id, "kasse.order.create", "KasseOrder", o.id, o.title)
    db.session.commit()
    return jsonify(_order(o, member.id, True, date.today(), full=True)), 201


@kasse_bp.get("/orders/<int:order_id>")
@require_member
def get_order(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    return jsonify(_order(o, member.id, _can(member, ORDERS), date.today(), full=True))


@kasse_bp.patch("/orders/<int:order_id>")
@permission_required("orders", "update", "Run collective orders")
def update_order(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    if o.status == "billed":
        return api_error("ORDER_BILLED", "this order is billed already", 409)
    data = _body()
    _apply_order(o, data, partial=True)
    if "items" in data:
        _apply_items(o, data)
    db.session.commit()
    return jsonify(_order(o, member.id, True, date.today(), full=True))


@kasse_bp.delete("/orders/<int:order_id>")
@permission_required("orders", "update", "Run collective orders")
def delete_order(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    if o.status == "billed":
        return api_error("ORDER_BILLED", "a billed order stays for the books", 409)
    log_audit(member.id, "kasse.order.delete", "KasseOrder", o.id, o.title)
    db.session.delete(o)
    db.session.commit()
    return "", 204


@kasse_bp.put("/orders/<int:order_id>/mine")
@require_member
def order_mine(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    if not _open(o, date.today()):
        return api_error("ORDER_CLOSED", "this order takes no more changes", 409)
    raw = _body().get("lines")
    if not isinstance(raw, list) or len(raw) > 100:
        raise Invalid("lines must be a list")
    items = {
        i.id: i
        for i in db.session.scalars(
            select(KasseOrderItem).where(KasseOrderItem.order_id == o.id)
        )
    }
    wanted: dict[tuple[int, str], int] = defaultdict(int)
    for entry in raw:
        if not isinstance(entry, dict):
            raise Invalid("lines must be a list of objects")
        item = items.get(_int(entry, "itemId", 1, 2**31 - 1) or 0)
        if item is None:
            raise Invalid("itemId: not part of this order")
        size = _text(entry, "size", 40) or ""
        sizes = _sizes(item)
        if sizes and size not in sizes:
            raise Invalid(f"{item.name}: choose a size")
        if not sizes:
            size = ""
        qty = _int(entry, "qty", 0, 99, 1)
        if qty:
            wanted[(item.id, size)] += qty
    for line in db.session.scalars(
        select(KasseOrderLine)
        .where(KasseOrderLine.order_id == o.id)
        .where(KasseOrderLine.member_id == member.id)
    ):
        db.session.delete(line)
    for (item_id, size), qty in wanted.items():
        db.session.add(
            KasseOrderLine(
                order_id=o.id,
                item_id=item_id,
                member_id=member.id,
                size=size or None,
                qty=min(qty, 99),
                price=items[item_id].price,
            )
        )
    db.session.commit()
    return jsonify(_order(o, member.id, _can(member, ORDERS), date.today(), full=True))


@kasse_bp.post("/orders/<int:order_id>/close")
@permission_required("orders", "update", "Run collective orders")
def close_order(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    if o.status == "billed":
        return api_error("ORDER_BILLED", "this order is billed already", 409)
    reopen = _bool(_body(), "reopen")
    if reopen and o.deadline < date.today():
        raise Invalid("move the deadline before reopening the order")
    o.status = "open" if reopen else "closed"
    db.session.commit()
    return jsonify(_order(o, member.id, True, date.today(), full=True))


@kasse_bp.get("/orders/<int:order_id>/list.csv")
@permission_required("orders", "update", "Run collective orders")
def order_csv(order_id: int):
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    items = list(
        db.session.scalars(
            select(KasseOrderItem)
            .where(KasseOrderItem.order_id == o.id)
            .order_by(KasseOrderItem.position)
        )
    )
    lines = list(
        db.session.scalars(
            select(KasseOrderLine).where(KasseOrderLine.order_id == o.id)
        )
    )
    by_id = {i.id: i for i in items}
    names = _names([line.member_id for line in lines])
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Artikel", "Grösse", "Anzahl"])
    for row in _summary(items, lines):
        w.writerow([row["itemName"], row["size"] or "", row["qty"]])
    w.writerow([])
    w.writerow(["Mitglied", "Artikel", "Grösse", "Anzahl", "Preis", "Total"])
    for line in sorted(
        lines, key=lambda x: ((names.get(x.member_id or 0) or "").lower(), x.id)
    ):
        item = by_id.get(line.item_id)
        w.writerow(
            [
                names.get(line.member_id or 0) or "",
                item.name if item else "",
                line.size or "",
                line.qty,
                f"{line.price:.2f}",
                f"{line.price * line.qty:.2f}",
            ]
        )
    safe = "".join(ch if ch.isalnum() else "-" for ch in o.title)[:60] or "order"
    return Response(
        "﻿" + out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
    )


@kasse_bp.post("/orders/<int:order_id>/bill")
@permission_required("orders", "update", "Run collective orders")
def bill_order(order_id: int):
    member = get_current_member()
    o, err = _get(KasseOrder, order_id)
    if err:
        return err
    if o.status == "billed":
        return api_error("ORDER_BILLED", "this order is billed already", 409)
    if o.status != "closed":
        return api_error("ORDER_OPEN", "close the order before billing it", 409)
    data = _body()
    lines = list(
        db.session.scalars(
            select(KasseOrderLine).where(KasseOrderLine.order_id == o.id)
        )
    )
    per_member: dict[int, list[KasseOrderLine]] = defaultdict(list)
    for line in lines:
        if line.member_id:
            per_member[line.member_id].append(line)
    count = 0
    for member_id, own in per_member.items():
        amount = sum((line.price * line.qty for line in own), Decimal("0"))
        if amount <= 0 or db.session.get(Member, member_id) is None:
            continue
        invoice = _invoice(member_id, amount, o.title, data, member.id)
        for line in own:
            line.invoice_id = invoice.id
        count += 1
    o.status = "billed"
    o.billed_at = datetime.now(timezone.utc)
    log_audit(member.id, "kasse.order.bill", "KasseOrder", o.id, f"{count} invoices")
    db.session.commit()
    return jsonify(
        {
            "invoices": count,
            "order": _order(o, member.id, True, date.today(), full=True),
        }
    )
