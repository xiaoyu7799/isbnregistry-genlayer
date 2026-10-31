# IsbnRegistry — a bibliographic identity primitive for GenLayer

**Contract:** https://explorer-studio.genlayer.com/address/0xb560F2C68407DC06430C95a27287d8B3f0564856
**Repo:** https://github.com/xiaoyu7799/isbnregistry-genlayer
**Network:** Stable Studionet only — chain ID 61999, RPC https://studio.genlayer.com/api. Gasless, zero cost, no real funds.

Citation registries, reading lists, and academic tools need an on-chain
record that a book actually exists with exactly the title, publisher,
and publication date claimed — not just a string someone typed. A
self-asserted "title + ISBN" pair proves nothing: anyone can type any
title next to any number.

IsbnRegistry proves a book's identity by consensus against the public
Open Library record, plus a deterministic checksum. It is a reusable
primitive: other contracts and tools can read a verified record and
trust that validators agreed the book is what it claims to be.

## Mechanism (summary)

1. **Register (deterministic, substantive).** `register_isbn(isbn13)`
   accepts only a 13-digit string that passes the ISBN-13 checksum
   (weights 1, 3 alternating over the first 12 digits; check digit =
   `(10 - (sum % 10)) % 10`). The checksum loop runs in the contract,
   so a mistyped or invented number is rejected before any record
   exists. This is not format-only validation: most random 13-digit
   strings fail the checksum.
2. **Verify (consensus).** `verify_isbn(id)` fetches the edition JSON
   from `https://openlibrary.org/isbn/{ISBN13}.json` (free, no API key).
   Every validator independently re-fetches the same record and accepts
   the leader's result only if its own record matches **exactly**:
   title after strip, publishers list exactly, publish_date exactly,
   an `isbn_13` list containing the requested ISBN, and
   `number_of_pages` equal when both sides report one. Any field
   mismatch rejects. There is no tolerance, no LLM, and no format-only
   acceptance.
3. **Store.** Only after consensus is the record written with status
   `verified`, together with the exact source URL. A verified record
   can never be re-verified or overwritten. A failed fetch raises
   before any write, so the record stays `pending` and retryable.

Full consensus design: [`docs/mechanism.md`](docs/mechanism.md).

## Contract

- **Address:** `0xb560F2C68407DC06430C95a27287d8B3f0564856`
- **Deploy tx:** `0x0fa932d2af21d8fccb64204c406f951d9cba7ea538bb63309ff70602b0790b95` (FINALIZED)
- **File:** [`contracts/isbnregistry.py`](contracts/isbnregistry.py)
- **Writes:** `register_isbn(isbn13) -> u256`, `verify_isbn(id) -> str`
- **Views:** `get_book(id)`, `get_count()`, `list_books(offset, limit 1–20)`
- **Storage:** `books: TreeMap[u256, str]` (JSON records),
  `ids: DynArray[u256]`, `next_id: u256`
- **Verified flow (see [`evidence.json`](evidence.json)):** book #0,
  ISBN `9780134685991`, registered by tx
  `0x02d7be9d10060969d64e2309ce39d5a558829747762818a9ff0542006f94499c`
  (FINALIZED), verified by tx
  `0x3fad504afffcd1b0b111056f8a1d8533f51624b043e90685e6e191dec1ce70e3`
  (FINALIZED), read back verified:
  title `Effective Java`, publishers `["Addison-Wesley Professional"]`,
  publish_date `December 27, 2017`, number_of_pages `416`,
  source `https://openlibrary.org/isbn/9780134685991.json`.

## Usage (genlayer-js 1.1.8)

```js
import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import { TransactionStatus } from "genlayer-js/types";

const ADDRESS = "0xb560F2C68407DC06430C95a27287d8B3f0564856";
const client = createClient({ chain: studionet, account });

// Register an ISBN (checksum enforced on-chain).
const registerTx = await client.writeContract({
  address: ADDRESS, functionName: "register_isbn",
  args: ["9780134685991"], value: 0n, leaderOnly: false,
});
await client.waitForTransactionReceipt({
  hash: registerTx, status: TransactionStatus.FINALIZED,
  retries: 180, interval: 5000,
});

// Verify it: validators fetch Open Library and must agree exactly.
const verifyTx = await client.writeContract({
  address: ADDRESS, functionName: "verify_isbn",
  args: [0n], value: 0n, leaderOnly: false,
});
await client.waitForTransactionReceipt({
  hash: verifyTx, status: TransactionStatus.FINALIZED,
  retries: 180, interval: 5000,
});

// Read the verified record back.
const record = JSON.parse(await client.readContract({
  address: ADDRESS, functionName: "get_book", args: [0n],
}));
```

## Scripts

```bash
npm install
node scripts/simulate.mjs   # local pre-flight check only — see below
node scripts/deploy.mjs     # writes deployment.json (key never written to disk)
node scripts/flow.mjs       # registers + verifies ISBN 9780134685991, writes evidence.json
```

Both deploy and flow accept `GENLAYER_PRIVATE_KEY`; if omitted, an
ephemeral key is generated for that run only. Studionet is gasless and
the contract is permissionless, so losing that key loses nothing.

## Simulation vs. on-chain consensus evidence — read this first

`scripts/simulate.mjs` performs **no on-chain transactions** and proves
nothing about GenLayer consensus. It only fetches the live Open Library
JSON in Node and applies the same checksum and exact-field logic as a
cheap pre-flight check, printing PASS/FAIL. It exists so a broken
assumption (wrong source format, wrong expected record) is caught
before spending a deployment.

The real evidence is:

- the on-chain verify transaction reaching FINALIZED,
- the read-back record in `evidence.json` showing status `verified`
  with the exact expected fields,
- the explorer page for the contract address showing the deploy,
  register, and verify transactions as FINALIZED / SUCCESS / Accepted.

Never cite a simulation PASS as consensus evidence.

## Honest limits

- **No authors check, deliberately.** The Open Library edition JSON
  carries no authors field (authors live on the separate work record).
  Requiring authors would fail on valid books, so this contract proves
  title/publisher/date/pages identity, not authorship.
- **Source records can change.** Open Library is community-editable, so
  its record for an ISBN can change over time. A verified record is a
  snapshot of what validators agreed on at verification time; a later
  verify of the same ISBN could differ if the source record changes.
  Verified records are not re-checked.
- **ISBN-13 only.** Older 10-digit ISBNs are out of scope by design.
- **Publisher join character.** Publishers travel through the nondet
  result as one `|`-joined string; a publisher name containing `|`
  would split incorrectly. No such name appears in the tested record,
  and Open Library publisher names do not use that character in
  practice, but the edge case is noted.
- **No frontend.** This is a standalone Intelligent Contract by design.
  The scripts above are the calling tools; there is no app, no Pages
  site, and no logo.

## Repository layout

- `contracts/isbnregistry.py` — the Intelligent Contract
- `scripts/deploy.mjs`, `scripts/flow.mjs`, `scripts/simulate.mjs`
- `docs/mechanism.md` — full consensus design
- `docs/submission.md` — Intelligent Contracts submission copy
- `deployment.json`, `evidence.json` — on-chain proof (no keys inside)
