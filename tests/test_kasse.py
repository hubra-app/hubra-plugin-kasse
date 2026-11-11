"""The Kasse plugin: expense claims, the tab and collective orders.

Runs with Hubra's fixtures once the plugin is in plugins/kasse of a Hubra
checkout (see README.md).
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/kasse"
TREASURER = [
    "kasse.claims.read",
    "kasse.claims.update",
    "kasse.tab.update",
    "kasse.orders.update",
]
# A valid Swiss IBAN (check digits correct).
IBAN = "CH93 0076 2011 6238 5295 7"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def club(client, app, db, seeded_db):
    """Kim the treasurer, Max and Mia (ordinary members), a category."""
    from hubra.core.models.finance import TransactionCategory

    set_modules(True, "kasse")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    kim = _make_role_and_member(db, tier, name="Kim", permission_keys=TREASURER)
    max_ = _make_role_and_member(db, tier, name="Max")
    mia = _make_role_and_member(db, tier, name="Mia")
    cat = TransactionCategory(name="Kasse")
    db.session.add(cat)
    db.session.commit()
    return {"kim": kim.id, "max": max_.id, "mia": mia.id, "cat": cat.id}


def _bell(db, member_id):
    from hubra.core.models.notification import Notification

    return [
        n.title
        for n in db.session.scalars(
            select(Notification).where(Notification.member_id == member_id)
        )
    ]


def _claim(client, **fields):
    form = {"title": "Kreide", "amount": "23.50", "spentOn": "2026-10-01"}
    form.update(fields)
    form["receipt"] = (io.BytesIO(PNG), "quittung.png", "image/png")
    return client.post(f"{BASE}/claims", data=form, content_type="multipart/form-data")


# ── Expense claims ───────────────────────────────────────────────────────────


def test_a_claim_goes_from_receipt_to_booked_expense(client, db, club):
    from hubra.core.models.finance import Transaction

    _login(client, "max@test.ch")
    res = _claim(client, iban=IBAN)
    assert res.status_code == 201, res.get_json()
    claim = res.get_json()
    assert claim["status"] == "submitted"
    assert claim["hasReceipt"] and claim["iban"] == IBAN.replace(" ", "")
    assert client.get(f"{BASE}/claims/{claim['id']}/receipt").data == PNG
    # Max can't approve his own claim, nor see everyone's.
    assert (
        client.post(
            f"{BASE}/claims/{claim['id']}/decide", json={"approve": True}
        ).status_code
        == 403
    )
    assert client.get(f"{BASE}/claims/all").status_code == 403

    # Mia can't see it or its receipt.
    _login(client, "mia@test.ch")
    assert client.get(f"{BASE}/claims").get_json() == []
    assert client.get(f"{BASE}/claims/{claim['id']}/receipt").status_code == 404

    _login(client, "kim@test.ch")
    assert [c["id"] for c in client.get(f"{BASE}/claims/all").get_json()] == [
        claim["id"]
    ]
    assert client.get(f"{BASE}/claims/{claim['id']}/receipt").data == PNG
    # Paying comes after approving; rejecting needs a reason.
    assert client.post(f"{BASE}/claims/{claim['id']}/pay", json={}).status_code == 409
    assert (
        client.post(
            f"{BASE}/claims/{claim['id']}/decide", json={"approve": False}
        ).status_code
        == 400
    )
    ok = client.post(f"{BASE}/claims/{claim['id']}/decide", json={"approve": True})
    assert ok.get_json()["status"] == "approved"
    paid = client.post(
        f"{BASE}/claims/{claim['id']}/pay", json={"categoryId": club["cat"]}
    )
    assert paid.status_code == 200, paid.get_json()
    body = paid.get_json()
    assert body["status"] == "paid" and body["transactionId"]

    tx = db.session.get(Transaction, body["transactionId"])
    assert tx.type == "expense" and float(tx.amount) == -23.5
    assert tx.member_id == club["max"] and tx.method == "IBAN"
    assert tx.category_id == club["cat"]
    assert any("genehmigt" in t for t in _bell(db, club["max"]))
    assert any("ausbezahlt" in t for t in _bell(db, club["max"]))
    # A paid claim stays: the treasurer can't delete it, nor can its owner.
    assert client.delete(f"{BASE}/claims/{claim['id']}").status_code == 403
    _login(client, "max@test.ch")
    assert client.delete(f"{BASE}/claims/{claim['id']}").status_code == 409


def test_a_claim_checks_its_input(client, club):
    _login(client, "max@test.ch")
    assert _claim(client, amount="0").status_code == 400
    assert _claim(client, iban="CH93 0076 2011 6238 5295 8").status_code == 400
    future = (date.today() + timedelta(days=3)).isoformat()
    assert _claim(client, spentOn=future).status_code == 400
    bad = client.post(
        f"{BASE}/claims",
        data={
            "title": "x",
            "amount": "5",
            "receipt": (io.BytesIO(b"MZ"), "a.exe", "application/x-msdownload"),
        },
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400
    # Without a receipt is fine; the owner can withdraw it while undecided.
    plain = client.post(f"{BASE}/claims", json={"title": "Zug", "amount": "12.40"})
    assert plain.status_code == 201
    assert client.delete(f"{BASE}/claims/{plain.get_json()['id']}").status_code == 204


# ── The tab ──────────────────────────────────────────────────────────────────


def test_the_tab_is_ticked_and_settled_into_invoices(client, db, club):
    from hubra.core.models.finance import Invoice

    _login(client, "kim@test.ch")
    beer = client.post(
        f"{BASE}/products", json={"name": "Bier", "price": "4.00"}
    ).get_json()
    water = client.post(
        f"{BASE}/products", json={"name": "Wasser", "price": "2.50"}
    ).get_json()

    _login(client, "max@test.ch")
    assert (
        client.post(f"{BASE}/products", json={"name": "x", "price": 1}).status_code
        == 403
    )
    client.post(f"{BASE}/tab", json={"productId": beer["id"], "qty": 2})
    tab = client.post(f"{BASE}/tab", json={"productId": water["id"]}).get_json()
    assert tab["total"] == 10.5 and len(tab["ticks"]) == 2
    assert all(t["canUndo"] for t in tab["ticks"])
    # Max can't tick on someone else's tab.
    other = client.post(
        f"{BASE}/tab", json={"productId": beer["id"], "memberId": club["mia"]}
    )
    assert other.status_code == 403
    # A price change later doesn't change what was ticked.
    _login(client, "kim@test.ch")
    client.patch(f"{BASE}/products/{beer['id']}", json={"price": "5.00"})
    client.post(f"{BASE}/tab", json={"productId": beer["id"], "memberId": club["mia"]})

    _login(client, "mia@test.ch")
    mine = client.get(f"{BASE}/tab").get_json()
    assert mine["total"] == 5.0
    # Mia can't take back Max's tick.
    max_tick = tab["ticks"][0]["id"]
    assert client.delete(f"{BASE}/tab/{max_tick}").status_code == 403

    _login(client, "kim@test.ch")
    totals = client.get(f"{BASE}/tab/members").get_json()["members"]
    assert {(r["memberName"], r["total"]) for r in totals} == {
        ("Test Max", 10.5),
        ("Test Mia", 5.0),
    }
    done = client.post(
        f"{BASE}/tab/settle", json={"categoryId": club["cat"], "dueDays": 20}
    ).get_json()
    assert done == {"invoices": 2, "total": 15.5}
    invoices = db.session.scalars(
        select(Invoice).where(Invoice.purpose == "other")
    ).all()
    assert sorted(float(i.amount) for i in invoices) == [5.0, 10.5]
    assert all((i.due - i.issued).days == 20 for i in invoices)
    assert client.get(f"{BASE}/tab/members").get_json()["members"] == []
    # A settled tick can't be taken back, and settling again bills nothing.
    assert client.delete(f"{BASE}/tab/{max_tick}").status_code == 409
    assert client.post(f"{BASE}/tab/settle", json={}).get_json()["invoices"] == 0


# ── Collective orders ────────────────────────────────────────────────────────


def _order(client, **fields):
    body = {
        "title": "Trainingsanzug 2027",
        "deadline": (date.today() + timedelta(days=14)).isoformat(),
        "supplier": "Sport Muster AG",
        "items": [
            {"name": "Jacke", "price": "65.00", "sizes": "S, M, L"},
            {"name": "Mütze", "price": "15.00"},
        ],
    }
    body.update(fields)
    return client.post(f"{BASE}/orders", json=body)


def test_a_collective_order_runs_to_the_supplier_list_and_invoices(client, db, club):
    from hubra.core.models.finance import Invoice

    _login(client, "kim@test.ch")
    order = _order(client).get_json()
    jacket, cap = order["items"]
    assert jacket["sizes"] == ["S", "M", "L"] and cap["sizes"] == []

    _login(client, "max@test.ch")
    url = f"{BASE}/orders/{order['id']}/mine"
    assert (
        client.put(
            url, json={"lines": [{"itemId": jacket["id"], "qty": 1}]}
        ).status_code
        == 400
    )
    mine = client.put(
        url,
        json={
            "lines": [
                {"itemId": jacket["id"], "size": "M", "qty": 1},
                {"itemId": cap["id"], "qty": 2},
            ]
        },
    ).get_json()
    assert mine["myTotal"] == 95.0 and len(mine["mine"]) == 2
    assert "lines" not in mine  # only the board sees everyone's
    _login(client, "mia@test.ch")
    client.put(url, json={"lines": [{"itemId": jacket["id"], "size": "M", "qty": 1}]})

    _login(client, "kim@test.ch")
    # The price of something ordered can't change, nor can it be removed.
    changed = client.patch(
        f"{BASE}/orders/{order['id']}",
        json={
            "items": [
                {
                    "id": jacket["id"],
                    "name": "Jacke",
                    "price": "70",
                    "sizes": "S, M, L",
                },
                {"id": cap["id"], "name": "Mütze", "price": "15"},
            ]
        },
    )
    assert changed.status_code == 400
    full = client.get(f"{BASE}/orders/{order['id']}").get_json()
    assert full["summary"] == [
        {"itemId": jacket["id"], "itemName": "Jacke", "size": "M", "qty": 2},
        {"itemId": cap["id"], "itemName": "Mütze", "size": None, "qty": 2},
    ]
    assert client.post(f"{BASE}/orders/{order['id']}/bill", json={}).status_code == 409
    client.post(f"{BASE}/orders/{order['id']}/close", json={})

    _login(client, "max@test.ch")
    assert client.put(url, json={"lines": []}).status_code == 409

    _login(client, "kim@test.ch")
    csv = client.get(f"{BASE}/orders/{order['id']}/list.csv").data.decode("utf-8-sig")
    assert "Jacke;M;2" in csv and "Test Max;Mütze;;2;15.00;30.00" in csv
    billed = client.post(
        f"{BASE}/orders/{order['id']}/bill", json={"categoryId": club["cat"]}
    ).get_json()
    assert billed["invoices"] == 2 and billed["order"]["status"] == "billed"
    amounts = sorted(
        float(i.amount)
        for i in db.session.scalars(
            select(Invoice).where(Invoice.description == "Trainingsanzug 2027")
        )
    )
    assert amounts == [65.0, 95.0]
    assert client.delete(f"{BASE}/orders/{order['id']}").status_code == 409


def test_an_order_past_its_deadline_takes_no_orders(client, club):
    _login(client, "kim@test.ch")
    past = (date.today() - timedelta(days=1)).isoformat()
    order = _order(client, deadline=past).get_json()
    assert order["open"] is False
    _login(client, "max@test.ch")
    item = order["items"][1]["id"]
    res = client.put(
        f"{BASE}/orders/{order['id']}/mine",
        json={"lines": [{"itemId": item, "qty": 1}]},
    )
    assert res.status_code == 409
    _login(client, "kim@test.ch")
    assert (
        client.post(
            f"{BASE}/orders/{order['id']}/close", json={"reopen": True}
        ).status_code
        == 400
    )


def test_the_fridge_sheet_has_a_code_per_product(client, app, club, monkeypatch):
    from hubra_kasse import qrsheet

    coded = []
    real = qrsheet.qr_data_uri
    monkeypatch.setattr(qrsheet, "qr_data_uri", lambda text: coded.append(text) or real(text))
    _login(client, "kim@test.ch")
    product = client.post(f"{BASE}/products", json={"name": "Bier", "price": "4.00"}).get_json()
    monkeypatch.setitem(app.config, "FRONTEND_BASE_URL", "")
    assert client.get(f"{BASE}/products/qr.pdf").status_code == 503
    monkeypatch.setitem(app.config, "FRONTEND_BASE_URL", "https://app.hubra.club/")
    # A link from the request is ignored: the codes go to the club app only.
    res = client.get(f"{BASE}/products/qr.pdf?link=https://evil.example/?x=")
    assert res.status_code == 200 and res.data.startswith(b"%PDF")
    assert len(coded) == 1
    assert coded[0].startswith("https://app.hubra.club/")
    assert coded[0].endswith(f"/app/kasse/tab?tick={product['id']}")
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/products/qr.pdf?link=https://x/").status_code == 403


# ── Dashboard widgets ───────────────────────────────────────────────────────


def test_widgets(db, club):
    from decimal import Decimal

    from hubra.core import contracts
    from hubra.core.models.member import Member
    from hubra_kasse.models import KasseClaim, KasseTick

    max_ = db.session.get(Member, club["max"])
    db.session.add_all([
        KasseTick(member_id=club["max"], name="Bier", price=Decimal("4.50"), qty=2),
        KasseTick(member_id=club["max"], name="Wasser", price=Decimal("2.00"), qty=1),
        KasseTick(member_id=club["mia"], name="Bier", price=Decimal("4.50"), qty=1),
        KasseClaim(member_id=club["max"], title="Kreide", amount=Decimal("23.50"),
                   spent_on=date(2026, 10, 1), status="submitted"),
        KasseClaim(member_id=club["mia"], title="Bälle", amount=Decimal("1200.00"),
                   spent_on=date(2026, 10, 2), status="approved"),
        KasseClaim(member_id=club["mia"], title="Alt", amount=Decimal("5.00"),
                   spent_on=date(2026, 9, 2), status="paid"),
    ])
    db.session.commit()

    tab = contracts.widget_data("kasse.tab", {}, actor=max_)
    assert tab["value"] == "CHF 11.00" and tab["sub"] in ("2 Striche", "2 ticks")
    claims = contracts.widget_data("kasse.claims", {}, actor=contracts.SYSTEM)
    assert claims["value"] == 2 and claims["sub"] == "CHF 1'223.50"

    # Claims need the right to read them; the tab is every member's own.
    offered = [o.contract.name for o in contracts.widgets(actor=max_)]
    assert "kasse.tab" in offered and "kasse.claims" not in offered


def test_the_tab_settings_are_the_settle_defaults(client, db, club, monkeypatch):
    from hubra.core.models.finance import Invoice

    # Module settings are kept per club; a plain dict stands in for one here.
    stored: dict = {}
    monkeypatch.setattr("hubra.core.modules.get_config", lambda code: dict(stored))
    monkeypatch.setattr("hubra.core.modules.set_config", lambda code, c: stored.update(c))

    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/tab/settings").status_code == 403
    _login(client, "kim@test.ch")
    assert client.get(f"{BASE}/tab/settings").get_json() == {"categoryId": None, "dueDays": 30}
    assert client.put(f"{BASE}/tab/settings", json={"categoryId": 99999}).status_code == 400
    got = client.put(
        f"{BASE}/tab/settings", json={"categoryId": club["cat"], "dueDays": 10}
    ).get_json()
    assert got == {"categoryId": club["cat"], "dueDays": 10}
    beer = client.post(f"{BASE}/products", json={"name": "Bier", "price": "4.00"}).get_json()
    client.post(f"{BASE}/tab", json={"productId": beer["id"]})
    assert client.post(f"{BASE}/tab/settle", json={"categoryId": None}).get_json()["invoices"] == 1
    invoice = db.session.scalars(select(Invoice).where(Invoice.purpose == "other")).one()
    assert (invoice.due - invoice.issued).days == 10


# ── Products as consumables in Inventory ─────────────────────────────────────


def test_products_are_consumables_in_inventory(client, db, club):
    """Through Inventory's contracts only; skipped where Inventory isn't installed."""
    from hubra.core.contracts import SYSTEM, available, query

    from hubra_kasse.items import link_missing, on_item_deleted, on_item_saved
    from hubra_kasse.models import KasseProduct

    def item(item_id):
        return query("inventory.items.get", ids=[item_id], actor=SYSTEM)[0]

    set_modules(False, "inventory")
    _login(client, "kim@test.ch")
    # Without Inventory the tab works as before; the product has no item.
    old = client.post(f"{BASE}/products", json={"name": "Mate", "price": "3.00"}).get_json()
    assert old["itemId"] is None and old["stock"] is None

    set_modules(True, "inventory")
    if not available("inventory.stock.adjust"):
        pytest.skip("needs the Inventory plugin with stock counts")
    beer = client.post(
        f"{BASE}/products",
        json={"name": "Bier", "price": "4.00", "stock": 12, "minStock": 3, "unit": "Flaschen"},
    ).get_json()
    got = item(beer["itemId"])
    assert (got["name"], got["category"], got["stock"], got["min_stock"], got["unit"]) == (
        "Bier", "Consumable", 12, 3, "Flaschen",
    )
    assert (beer["stock"], beer["minStock"], beer["lowStock"]) == (12, 3, False)

    # A tick takes from the stock, a tick taken back puts it back.
    _login(client, "max@test.ch")
    tab = client.post(f"{BASE}/tab", json={"productId": beer["id"], "qty": 9}).get_json()
    assert item(beer["itemId"])["stock"] == 3
    client.delete(f"{BASE}/tab/{tab['ticks'][0]['id']}")
    assert item(beer["itemId"])["stock"] == 12

    # Renamed here goes there; a count by hand; renamed there comes back.
    _login(client, "kim@test.ch")
    client.patch(f"{BASE}/products/{beer['id']}", json={"name": "Lager", "stock": 2})
    assert (item(beer["itemId"])["name"], item(beer["itemId"])["stock"]) == ("Lager", 2)
    listed = {p["name"]: p for p in client.get(f"{BASE}/products").get_json()}
    assert listed["Lager"]["lowStock"] is True
    from hubra.core.contracts import call

    call("inventory.items.save", item_id=beer["itemId"], name="Lager hell", actor=SYSTEM)
    on_item_saved(item_id=beer["itemId"])
    assert db.session.get(KasseProduct, beer["id"]).name == "Lager hell"

    # Products from before get their item from the job.
    assert link_missing() == 1
    assert item(db.session.get(KasseProduct, old["id"]).item_id)["category"] == "Consumable"

    # Deleted in Inventory: off the tab.
    on_item_deleted(item_id=beer["itemId"])
    product = db.session.get(KasseProduct, beer["id"])
    assert product.item_id is None and product.active is False


# ── Security (audit 2026-11-11) ──────────────────────────────────────────────


SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def test_a_receipt_is_a_photo_or_pdf_by_its_bytes(client, db, club):
    """The browser's type doesn't count: an SVG or HTML "photo" would run
    script in the club app when the treasurer opens it."""
    _login(client, "max@test.ch")
    for blob, name, kind in (
        (SVG, "q.svg", "image/svg+xml"),
        (SVG, "q.png", "image/png"),
        (b"<html><script>alert(1)</script>", "q.jpg", "image/jpeg"),
    ):
        res = client.post(
            f"{BASE}/claims",
            data={"title": "x", "amount": "5", "receipt": (io.BytesIO(blob), name, kind)},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400, name
    pdf = client.post(
        f"{BASE}/claims",
        data={
            "title": "x",
            "amount": "5",
            "receipt": (io.BytesIO(b"%PDF-1.7\n..."), "q.pdf", "application/octet-stream"),
        },
        content_type="multipart/form-data",
    ).get_json()
    assert pdf["receiptType"] == "application/pdf"
    res = client.get(f"{BASE}/claims/{pdf['id']}/receipt?inline=1")
    assert res.mimetype == "application/pdf"
    assert "sandbox" in res.headers["Content-Security-Policy"]


def test_an_old_svg_receipt_only_leaves_as_a_download(client, db, club):
    from hubra.core import files as store
    from hubra_kasse.models import KasseClaim

    _login(client, "max@test.ch")
    claim_id = _claim(client).get_json()["id"]
    claim = db.session.get(KasseClaim, claim_id)
    claim.receipt_key = store.put("kasse", SVG, "image/svg+xml").key
    claim.receipt_type = "image/svg+xml"
    db.session.commit()
    _login(client, "kim@test.ch")
    res = client.get(f"{BASE}/claims/{claim_id}/receipt?inline=1")
    assert res.status_code == 200
    assert res.mimetype == "application/octet-stream"
    assert res.headers["Content-Disposition"].startswith("attachment")


def test_the_supplier_list_has_no_formulas(client, db, club):
    from hubra.core.models.member import Member

    db.session.get(Member, club["max"]).first_name = "=HYPERLINK(1)"
    db.session.commit()
    _login(client, "kim@test.ch")
    order = client.post(
        f"{BASE}/orders",
        json={
            "title": "Caps",
            "deadline": (date.today() + timedelta(days=5)).isoformat(),
            "items": [{"name": "@SUM(A1)", "price": "10"}],
        },
    ).get_json()
    _login(client, "max@test.ch")
    client.put(
        f"{BASE}/orders/{order['id']}/mine",
        json={"lines": [{"itemId": order["items"][0]["id"], "qty": 1}]},
    )
    _login(client, "kim@test.ch")
    csv = client.get(f"{BASE}/orders/{order['id']}/list.csv").data.decode("utf-8-sig")
    assert "'@SUM(A1);;1" in csv and "'=HYPERLINK(1)" in csv
    assert "\n=" not in csv and ";=" not in csv and ";@" not in csv


def test_money_on_someone_elses_tab_is_on_record(client, db, club):
    from hubra.core.models.audit import AuditEntry

    _login(client, "kim@test.ch")
    product = client.post(f"{BASE}/products", json={"name": "Bier", "price": "4"}).get_json()
    client.patch(f"{BASE}/products/{product['id']}", json={"price": "5"})
    tab = client.post(
        f"{BASE}/tab", json={"productId": product["id"], "memberId": club["max"]}
    ).get_json()
    client.delete(f"{BASE}/tab/{tab['ticks'][0]['id']}")
    actions = set(
        db.session.scalars(
            select(AuditEntry.action).where(AuditEntry.action.like("kasse.%"))
        )
    )
    assert {
        "kasse.product.create",
        "kasse.product.update",
        "kasse.tick.create",
        "kasse.tick.delete",
    } <= actions


def test_nobody_decides_or_pays_their_own_claim(client, db, club):
    """Four eyes: the treasurer's own claim needs another treasurer."""
    from hubra.core.models.member import Member
    from hubra_kasse.models import KasseClaim

    _login(client, "kim@test.ch")
    own = _claim(client).get_json()
    base = f"{BASE}/claims/{own['id']}"
    refused = client.post(f"{base}/decide", json={"approve": True})
    assert refused.status_code == 403 and refused.get_json()["error"] == "OWN_CLAIM"
    db.session.get(KasseClaim, own["id"]).status = "approved"
    db.session.commit()
    refused = client.post(f"{base}/pay", json={})
    assert refused.status_code == 403 and refused.get_json()["error"] == "OWN_CLAIM"
    assert db.session.get(KasseClaim, own["id"]).status == "approved"
    # Not even an admin; and a decided claim can't be withdrawn either.
    assert db.session.get(Member, club["kim"]) is not None
    assert client.delete(base).status_code == 409


def test_the_treasurer_rejects_instead_of_deleting(client, db, club):
    _login(client, "max@test.ch")
    claim = _claim(client).get_json()
    _login(client, "kim@test.ch")
    assert client.delete(f"{BASE}/claims/{claim['id']}").status_code == 403
    client.post(f"{BASE}/claims/{claim['id']}/decide", json={"approve": False, "note": "doppelt"})
    _login(client, "max@test.ch")
    # Rejected stays on record too.
    assert client.delete(f"{BASE}/claims/{claim['id']}").status_code == 409


def test_a_deleted_invoice_puts_its_ticks_back_on_the_tab(client, db, club):
    """Club schemas have no foreign keys: Kasse unbills by itself."""
    from hubra.core.contracts import SYSTEM, call
    from hubra_kasse.models import KasseTick

    _login(client, "kim@test.ch")
    product = client.post(f"{BASE}/products", json={"name": "Bier", "price": "4"}).get_json()
    client.post(f"{BASE}/tab", json={"productId": product["id"], "memberId": club["max"]})
    client.post(f"{BASE}/tab/settle", json={"categoryId": club["cat"]})
    tick = db.session.scalar(select(KasseTick).where(KasseTick.member_id == club["max"]))
    assert tick.invoice_id is not None
    call("finance.invoice.delete", invoice_id=tick.invoice_id, actor=SYSTEM)
    db.session.commit()
    db.session.refresh(tick)
    # Open again (on Postgres in tests the foreign key nulls it first).
    assert tick.invoice_id is None
    assert client.get(f"{BASE}/tab/members").get_json()["members"][0]["total"] == 4.0


def test_purge_orphans_clears_links_to_rows_that_are_gone(db, club):
    from hubra_kasse.links import purge_orphans
    from hubra_kasse.models import KasseOrderItem, KasseTick

    if db.engine.dialect.name != "sqlite":
        pytest.skip("needs a schema without foreign keys, like a club's")
    db.session.add(
        KasseTick(member_id=club["max"], product_id=987654, name="Bier", price=4, qty=1, invoice_id=987654)
    )
    db.session.add(KasseOrderItem(order_id=987654, name="Cap", price=10))
    db.session.commit()
    done = purge_orphans()
    db.session.commit()
    assert done["reopened"] == 1 and done["products"] == 1 and done["orderRows"] == 1
    tick = db.session.scalar(select(KasseTick).where(KasseTick.name == "Bier"))
    assert tick.invoice_id is None and tick.product_id is None
