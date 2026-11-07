"""The monthly payout script end to end against the in-memory store: export a window,
decide in the spreadsheet, settle, and mark paid."""

from __future__ import annotations

import csv
import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from app.models import Payee, PayoutEntry, PlaceRef, Review, ReviewExtraction
from app.pii import phone_hash

openpyxl = pytest.importorskip("openpyxl")
ADA, BOB, CHI = "2348011111111", "2348022222222", "2348033333333"
WINDOW = "2026-11"


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "payout.py"
    spec = importlib.util.spec_from_file_location("payout_script", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["payout_script"] = mod
    spec.loader.exec_module(mod)
    return mod


def _entry(rid, phone, group, points, kind="voice"):
    return PayoutEntry(
        review_id=rid, phone=phone, phone_hash=phone_hash(phone), business_id=f"b-{rid}",
        business_name=f"Biz {rid}", category="restaurant", group=group, kind=kind,
        points=points, window=WINDOW, entered_at=f"2026-11-02T10:00:0{rid[-1]}Z",
    )  # fmt: skip


@pytest.fixture
def script(monkeypatch, rewards_db, tmp_path):
    mod = _load_script()
    monkeypatch.chdir(tmp_path)
    sent: list[tuple] = []
    reviews = {}
    for rid in ("r1", "r2", "r3", "r4"):
        reviews[rid] = Review(
            review_id=rid, business_id=f"b-{rid}", submission_id=f"s-{rid}",
            reviewer_phone_hash="h", source="voice", audio_s3_key=f"reviews/{rid}/voice.m4a",
            extraction=ReviewExtraction(
                business=PlaceRef(place_id="b", name="n", formatted_address="a", country="NG"),
                business_name_as_said="n", one_line_summary=f"summary {rid}",
            ),
        )  # fmt: skip
    monkeypatch.setattr(mod.dynamo, "get_review", lambda rid: reviews.get(rid))
    monkeypatch.setattr(mod.s3, "presigned_url", lambda key, expires=3600: f"https://s3/{key}")
    monkeypatch.setattr(mod.s3, "get_json", lambda key: {})
    monkeypatch.setattr(mod.wa, "send_template", lambda *a, **k: sent.append(a) or "wamid")
    for e in (
        _entry("r1", ADA, "restaurants", 10, "reel_author"),
        _entry("r2", ADA, "others", 5),
        _entry("r3", BOB, "others", 5),
        _entry("r4", CHI, "hotels", 10, "reel_author"),
        _entry("r5", CHI, "hotels", 0, "reel_unverified"),
    ):
        rewards_db.entries[(e.phone_hash, e.review_id)] = e
    rewards_db.payees[phone_hash(ADA)] = Payee(
        phone=ADA, bank_name="GTBank", account_number="0123456789", account_name="Ada Obi"
    )
    rewards_db.payees[phone_hash(BOB)] = Payee(phone=BOB, method="amazon")
    return mod, rewards_db, sent, tmp_path


def test_export_settle_and_mark_paid(script):
    mod, db, sent, tmp = script
    assert mod.cmd_export(Namespace(window=WINDOW, out=None, metrics=False)) == 0
    wb = openpyxl.load_workbook(tmp / f"payout-{WINDOW}.xlsx")
    assert wb.sheetnames == ["Summary", "Shortlets", "Restaurants", "Hotels", "Others"]
    others = wb["Others"]
    header = [c.value for c in others[1]]
    rows = {r[header.index("review_id")].value: r for r in others.iter_rows(min_row=2)}
    hotel_ids = [r[0].value for r in wb["Hotels"].iter_rows(min_row=2)]
    assert hotel_ids == ["r4"]  # the unverified reel is left out: it can only be voided
    assert set(rows) == {"r2", "r3"} and rows["r2"][header.index("phone")].value == "***1111"
    assert rows["r2"][header.index("media_link")].value == "https://s3/reviews/r2/voice.m4a"
    # the reviewer voids Chi's hotel reel and bans Bob
    hotels = wb["Hotels"]
    hotels.cell(row=2, column=header.index("decision") + 1, value="void")
    others.cell(row=2 + list(rows).index("r3"), column=header.index("decision") + 1, value="ban")
    others.cell(row=2 + list(rows).index("r3"), column=header.index("note") + 1, value="spam x5")
    wb.save(tmp / "decided.xlsx")

    args = Namespace(window=WINDOW, sheet=str(tmp / "decided.xlsx"), apply=False)
    assert mod.cmd_settle(args) == 0
    assert not (tmp / f"transfers-{WINDOW}.csv").exists()  # dry run writes nothing
    assert all(e.status == "entered" for e in db.entries.values())

    args.apply = True
    assert mod.cmd_settle(args) == 0
    status = {rid: e.status for (_, rid), e in db.entries.items()}
    assert status == {
        "r1": "approved", "r2": "approved", "r3": "voided", "r4": "voided", "r5": "voided",
    }  # fmt: skip
    assert db.entries[(phone_hash(CHI), "r5")].note == "author not verified"
    assert phone_hash(BOB) in db.bans and db.bans[phone_hash(BOB)].note == "spam x5"
    with (tmp / f"transfers-{WINDOW}.csv").open() as f:
        transfers = list(csv.DictReader(f))
    assert len(transfers) == 1 and transfers[0]["amount_ngn"] == "15000"
    assert transfers[0]["account_number"] == "0123456789"
    assert db.payruns[WINDOW]["total_ngn"] == 15000

    mp = Namespace(window=WINDOW, csv=str(tmp / f"transfers-{WINDOW}.csv"), apply=True)
    assert mod.cmd_mark_paid(mp) == 0
    paid = {rid for (_, rid), e in db.entries.items() if e.status == "paid"}
    assert paid == {"r1", "r2"} and db.payruns[WINDOW]["paid_at"]
    assert sent and sent[0][0] == ADA and sent[0][2][:2] == ["Ada", "₦15,000"]
