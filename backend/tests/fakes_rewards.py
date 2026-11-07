"""In-memory stand-in for app/store/rewards_store.py, with the same function names."""

from __future__ import annotations

from app.models import Ban, Payee, PayoutEntry, PayoutOffer


class FakeRewardsStore:
    API = (
        "put_entry", "get_entry", "list_entries", "list_window", "delete_entry",
        "put_offer", "list_offers", "delete_offer", "get_payee", "put_payee",
        "delete_rewards_partition", "put_ig_code", "get_ig_code", "delete_ig_code",
        "get_ig_link", "claim_ig_link", "list_ig_links", "delete_ig_link", "claim_ig_message",
        "claim_media", "delete_media_claim", "get_ban", "put_ban", "delete_ban", "list_bans",
        "ig_account_banned", "put_payrun", "get_payrun",
    )  # fmt: skip

    def __init__(self):
        self.entries: dict[tuple[str, str], PayoutEntry] = {}
        self.offers: dict[tuple[str, str], PayoutOffer] = {}
        self.payees: dict[str, Payee] = {}
        self.codes: dict[str, dict] = {}
        self.links: dict[str, str] = {}
        self.ig_messages: set[str] = set()
        self.media: dict[str, str] = {}
        self.bans: dict[str, Ban] = {}
        self.banned_ig: set[str] = set()
        self.payruns: dict[str, dict] = {}

    # entries
    def put_entry(self, e, *, only_new=False):
        key = (e.phone_hash, e.review_id)
        if only_new and key in self.entries:
            return False
        self.entries[key] = e.model_copy(deep=True)
        return True

    def get_entry(self, h, rid):
        e = self.entries.get((h, rid))
        return e.model_copy(deep=True) if e else None

    def list_entries(self, h):
        return [e.model_copy(deep=True) for (eh, _), e in self.entries.items() if eh == h]

    def list_window(self, window):
        return [e.model_copy(deep=True) for e in self.entries.values() if e.window == window]

    def delete_entry(self, h, rid):
        self.entries.pop((h, rid), None)

    # offers
    def put_offer(self, h, o, ttl_seconds):
        self.offers[(h, o.review_id)] = o

    def list_offers(self, h):
        return [o for (oh, _), o in self.offers.items() if oh == h]

    def delete_offer(self, h, rid):
        self.offers.pop((h, rid), None)

    # payee
    def get_payee(self, h):
        return self.payees.get(h)

    def put_payee(self, h, p):
        self.payees[h] = p

    def delete_rewards_partition(self, h, keep):
        n = 0
        for key, e in list(self.entries.items()):
            if key[0] == h and not keep({"SK": f"ENTRY#{e.review_id}", **e.model_dump()}):
                del self.entries[key]
                n += 1
        for key in [k for k in self.offers if k[0] == h]:
            del self.offers[key]
            n += 1
        if h in self.payees:
            del self.payees[h]
            n += 1
        return n

    # instagram
    def put_ig_code(self, code, record, ttl_seconds):
        self.codes[code] = dict(record)

    def get_ig_code(self, code):
        return self.codes.get(code)

    def delete_ig_code(self, code):
        self.codes.pop(code, None)

    def get_ig_link(self, username):
        return self.links.get(username.lower())

    def claim_ig_link(self, username, h):
        owner = self.links.setdefault(username.lower(), h)
        return owner == h

    def list_ig_links(self, h):
        return [u for u, owner in self.links.items() if owner == h]

    def delete_ig_link(self, username):
        self.links.pop(username.lower(), None)

    def claim_ig_message(self, mid):
        if mid in self.ig_messages:
            return False
        self.ig_messages.add(mid)
        return True

    # media
    def claim_media(self, sha, rid):
        if sha in self.media:
            return False
        self.media[sha] = rid
        return True

    def delete_media_claim(self, sha):
        self.media.pop(sha, None)

    # bans
    def get_ban(self, h):
        return self.bans.get(h)

    def put_ban(self, b):
        self.bans[b.phone_hash] = b
        self.banned_ig.update(u.lower() for u in b.ig_usernames)

    def delete_ban(self, b):
        self.bans.pop(b.phone_hash, None)
        self.banned_ig.difference_update(u.lower() for u in b.ig_usernames)

    def list_bans(self):
        return list(self.bans.values())

    def ig_account_banned(self, username):
        return username.lower() in self.banned_ig

    # pay runs
    def put_payrun(self, window, record):
        self.payruns[window] = record

    def get_payrun(self, window):
        return self.payruns.get(window)
