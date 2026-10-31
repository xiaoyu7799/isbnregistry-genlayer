# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""IsbnRegistry: a bibliographic identity primitive for GenLayer.

Problem
-------
Citation registries, reading lists, and academic tools need an on-chain
record that a book actually exists with exactly the title, publisher,
and publication date claimed -- not just a string someone typed. A
self-asserted "title + ISBN" pair proves nothing: anyone can type any
title next to any number.

What this contract does
-----------------------
1. Anyone registers an ISBN-13. Registration is deterministic and
   substantive: the number must be exactly 13 digits AND pass the
   ISBN-13 checksum (weights 1, 3 alternating over the first 12 digits;
   check digit = (10 - (sum % 10)) % 10). The checksum loop runs in
   this contract, so a mistyped or invented number is rejected before
   any record exists.
2. Anyone verifies it. Validators independently fetch the same edition
   record from the Open Library (free, no API key) and must agree with
   the leader on the book's identity, field by field, exactly.
3. Only then is the verified record written on-chain, together with the
   exact source URL that was fetched.

Consensus design (the part that matters)
----------------------------------------
* Leader and every validator run the same fetch function.
* A validator accepts the leader result only if its own independently
  fetched record has:
    - the title exactly equal after strip,
    - the publishers list exactly equal (carried in the nondet result
      as one "|"-joined string and split back by the validator),
    - the publish_date exactly equal,
    - an isbn_13 list containing the requested ISBN,
    - number_of_pages equal when both sides report one.
  This is EXACT multi-field identity equivalence, not a tolerance and
  not a format check: any field mismatch rejects. Checking only the
  shape of the leader output would not be consensus, so the validator
  never accepts a record it did not independently reproduce.
* A failed fetch raises a UserError before any state is written, so
  the record stays "pending" and can be retried. A verified record can
  never be re-verified or overwritten.
* The nondet result carries only strings and ints, never floats:
  GenVM calldata cannot encode floats (returning a float crashed an
  earlier GenLayer project with "not calldata encodable ...: float").

Limits, stated honestly
-----------------------
* This proves identity against the Open Library edition record, not
  authorship: the edition JSON carries no authors field (authors live
  on the separate work record), so authors are deliberately NOT checked
  -- requiring them would fail on valid books.
* Open Library is community-editable, so its record for an ISBN can
  change over time. A verified record is a snapshot of what validators
  agreed on at verification time; a later verify of the same ISBN could
  differ if the source record changes. This contract does not
  re-check verified records.
* ISBN-13 only. Older 10-digit ISBNs are out of scope by design.
* No LLM anywhere in this contract, deliberately: identity equivalence
  is a deterministic field comparison, not a judgment call.
"""

import json

from genlayer import *


class IsbnRegistry(gl.Contract):
    books: TreeMap[u256, str]
    ids: DynArray[u256]
    next_id: u256

    def __init__(self):
        self.next_id = u256(0)

    # -- deterministic helpers -------------------------------------------

    def _load(self, book_id: u256) -> dict:
        if book_id not in self.books:
            raise gl.vm.UserError("EXPECTED: book_not_found")
        return json.loads(self.books[book_id])

    def _check_isbn13(self, isbn13: str) -> str:
        isbn13 = isbn13.strip()
        if len(isbn13) != 13:
            raise gl.vm.UserError("EXPECTED: isbn13_must_be_13_digits")
        for ch in isbn13:
            if ch < "0" or ch > "9":
                raise gl.vm.UserError("EXPECTED: isbn13_must_be_13_digits")
        total = 0
        index = 0
        while index < 12:
            digit = int(isbn13[index])
            if index % 2 == 0:
                total = total + digit
            else:
                total = total + 3 * digit
            index = index + 1
        check = (10 - (total % 10)) % 10
        if check != int(isbn13[12]):
            raise gl.vm.UserError("EXPECTED: isbn13_checksum_failed")
        return isbn13

    # -- writes ------------------------------------------------------------

    @gl.public.write
    def register_isbn(self, isbn13: str) -> u256:
        isbn13 = self._check_isbn13(isbn13)
        source_url = f"https://openlibrary.org/isbn/{isbn13}.json"
        book_id = self.next_id
        self.next_id = book_id + u256(1)
        record = {
            "id": int(book_id),
            "isbn13": isbn13,
            "requester": str(gl.message.sender_address),
            "status": "pending",
            "title": None,
            "publishers": None,
            "publish_date": None,
            "number_of_pages": None,
            "source_url": source_url,
        }
        self.books[book_id] = json.dumps(record)
        self.ids.append(book_id)
        return book_id

    @gl.public.write
    def verify_isbn(self, book_id: u256) -> str:
        record = self._load(book_id)
        if record["status"] != "pending":
            raise gl.vm.UserError("EXPECTED: book_already_verified")
        isbn13 = record["isbn13"]
        url = record["source_url"]

        def fetch_edition() -> dict:
            response = gl.nondet.web.get(url)
            status = getattr(response, "status", 200)
            if status != 200:
                raise gl.vm.UserError(f"EXTERNAL: open_library_status_{status}")
            body = response.body
            if isinstance(body, bytes):
                text = body.decode("utf-8")
            else:
                text = str(body)
            try:
                data = json.loads(text)
            except Exception:
                raise gl.vm.UserError("EXTERNAL: open_library_bad_json")
            if not isinstance(data, dict):
                raise gl.vm.UserError("EXTERNAL: open_library_bad_json")
            title = data.get("title")
            if not isinstance(title, str) or len(title.strip()) == 0:
                raise gl.vm.UserError("EXTERNAL: open_library_missing_title")
            publishers_raw = data.get("publishers")
            if not isinstance(publishers_raw, list) or len(publishers_raw) == 0:
                raise gl.vm.UserError("EXTERNAL: open_library_missing_publishers")
            publishers_joined = ""
            first = True
            for item in publishers_raw:
                if not isinstance(item, str) or len(item.strip()) == 0:
                    raise gl.vm.UserError("EXTERNAL: open_library_missing_publishers")
                if first:
                    publishers_joined = item.strip()
                    first = False
                else:
                    publishers_joined = publishers_joined + "|" + item.strip()
            publish_date = data.get("publish_date")
            if not isinstance(publish_date, str) or len(publish_date) == 0:
                raise gl.vm.UserError("EXTERNAL: open_library_missing_publish_date")
            isbn_list = data.get("isbn_13")
            if not isinstance(isbn_list, list):
                raise gl.vm.UserError("EXTERNAL: open_library_isbn_mismatch")
            found = False
            for item in isbn_list:
                if item == isbn13:
                    found = True
            if not found:
                raise gl.vm.UserError("EXTERNAL: open_library_isbn_mismatch")
            pages = data.get("number_of_pages")
            if isinstance(pages, int):
                pages_value = pages
            else:
                pages_value = -1
            # Only strings and ints cross the nondet boundary: publishers
            # travel as one "|"-joined string, pages as an int (-1 means
            # "not reported"). No floats, ever.
            return {
                "isbn13": isbn13,
                "title": title.strip(),
                "publishers": publishers_joined,
                "publish_date": publish_date,
                "number_of_pages": pages_value,
            }

        def validate(leader_result) -> bool:
            if isinstance(leader_result, gl.vm.UserError):
                try:
                    fetch_edition()
                except gl.vm.UserError:
                    return True
                except Exception:
                    return False
                return False
            if not isinstance(leader_result, gl.vm.Return):
                return False
            leader = leader_result.calldata
            if not isinstance(leader, dict):
                return False
            try:
                own = fetch_edition()
            except Exception:
                return False
            if leader.get("isbn13") != isbn13:
                return False
            if leader.get("title") != own["title"]:
                return False
            if leader.get("publishers") != own["publishers"]:
                return False
            if leader.get("publish_date") != own["publish_date"]:
                return False
            leader_pages = leader.get("number_of_pages")
            own_pages = own["number_of_pages"]
            if not isinstance(leader_pages, int) or not isinstance(own_pages, int):
                return False
            if leader_pages != -1 and own_pages != -1 and leader_pages != own_pages:
                return False
            return True

        result = gl.vm.run_nondet_unsafe(fetch_edition, validate)
        publishers = result["publishers"].split("|")
        if result["number_of_pages"] == -1:
            pages_out = None
        else:
            pages_out = result["number_of_pages"]
        record["status"] = "verified"
        record["title"] = result["title"]
        record["publishers"] = publishers
        record["publish_date"] = result["publish_date"]
        record["number_of_pages"] = pages_out
        self.books[book_id] = json.dumps(record)
        return json.dumps(record)

    # -- views -------------------------------------------------------------

    @gl.public.view
    def get_book(self, book_id: u256) -> str:
        return json.dumps(self._load(book_id))

    @gl.public.view
    def get_count(self) -> u256:
        return u256(len(self.ids))

    @gl.public.view
    def list_books(self, offset: u256, limit: u256) -> str:
        if limit < 1 or limit > 20:
            raise gl.vm.UserError("EXPECTED: limit_must_be_1_to_20")
        total = len(self.ids)
        start = int(offset)
        if start >= total:
            return json.dumps([])
        end = start + int(limit)
        if end > total:
            end = total
        out = []
        index = start
        while index < end:
            out.append(json.loads(self.books[self.ids[index]]))
            index += 1
        return json.dumps(out)
