# IsbnRegistry consensus design

## What is being proven

That the book with a given ISBN-13 is, in the Open Library edition
record, exactly the book its record claims: same title, same
publishers, same publication date, same page count. This is an
identity-equivalence proof, not a measurement: there is no tolerance
band, because a title that is "close" is a different book.

## Registration: deterministic and substantive

`register_isbn` runs the ISBN-13 checksum in the contract before any
state is written:

- the input must be exactly 13 characters, all digits;
- weights 1, 3 alternate over the first 12 digits;
- check digit = `(10 - (sum % 10)) % 10`, compared with the 13th digit.

Anything else raises an `EXPECTED` error (`isbn13_must_be_13_digits`
or `isbn13_checksum_failed`) and no record is created. This matters:
without the checksum, registration would accept any 13 digits and the
"registry" would be a typing exercise. With it, registration already
filters out mistyped and invented numbers, and verification only has to
confirm the identity of a structurally valid ISBN.

The record is created with status `pending` and all bibliographic
fields empty, plus the exact source URL
`https://openlibrary.org/isbn/{ISBN13}.json`.

## The nondet function

`verify_isbn` runs `fetch_edition` under `gl.vm.run_nondet_unsafe`:

1. Fetch the source URL. A non-200 status raises
   `EXTERNAL: open_library_status_{status}` before any write.
2. Parse the body as JSON. Unparseable or non-object bodies raise
   `EXTERNAL: open_library_bad_json`.
3. Extract and validate, raising `EXTERNAL: ...` on any missing piece:
   - `title`: a non-empty string, stripped;
   - `publishers`: a non-empty list of non-empty strings, stripped and
     joined into one string with `|` (see below);
   - `publish_date`: a non-empty string, kept exactly;
   - `isbn_13`: a list that must contain the requested ISBN, otherwise
     `EXTERNAL: open_library_isbn_mismatch`;
   - `number_of_pages`: carried as an int when present, otherwise the
     sentinel `-1` meaning "not reported".
4. The result carries only strings and ints. GenVM calldata cannot
   encode floats, so no float ever crosses the nondet boundary. (An
   earlier GenLayer project crashed its leader with
   "not calldata encodable ...: float" for exactly this reason.)

The `|` join is a transport encoding, not a semantic change: the
validator splits the joined string back into the list and compares
lists. A publisher name containing `|` would corrupt the round-trip;
that character does not appear in Open Library publisher names in
practice, and the limitation is recorded in the README.

## The validator

A validator accepts the leader result only if its own independently
fetched record satisfies all five checks:

1. title exactly equal after strip;
2. publishers list exactly equal after splitting the joined string;
3. publish_date exactly equal;
4. its own fetch confirmed the `isbn_13` list contains the requested
   ISBN (the fetch raises otherwise, so a mismatched ISBN can never
   produce a passing validator result);
5. number_of_pages equal when both sides report one (either side
   reporting `-1` skips the page check, since some editions omit it).

It never accepts a record it did not independently reproduce. If the
leader raised a UserError, the validator re-fetches: agreement that the
source is unavailable or mismatched is itself consensus that nothing
can be verified yet, and the record stays pending.

## The deterministic gate

After consensus, `verify_isbn` writes status `verified` with the
agreed title, publishers (split back into a list), publish_date,
number_of_pages (or null when unreported), and the stored source URL,
and returns the full record. Two further deterministic rules:

- A record whose status is not `pending` raises
  `EXPECTED: book_already_verified`: verified records are never
  re-verified or overwritten.
- A failed fetch or a consensus rejection writes nothing: the record
  stays `pending` and the verification can be retried later.

## Why no authors check

The edition JSON has no authors field. Authors live on the work record
(`https://openlibrary.org/works/{id}.json`), which would be a second
fetch, a second consensus surface, and a join between two records that
can change independently. For a minimal, reusable primitive, the
edition record alone is the right scope: it already carries title,
publishers, date, ISBNs, and pages — enough to establish that the book
exists as claimed. A future extension could add a work-record check as
a separate verified field; it is deliberately not smuggled into this
one.

## What this does not prove

- Authorship (see above).
- That the book's content matches its description: consensus proves
  the catalogue identity, not the text inside the book.
- Permanence of the source record: Open Library can be edited, so a
  verified record is a snapshot at verification time.
