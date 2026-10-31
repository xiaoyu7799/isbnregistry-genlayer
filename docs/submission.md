# IsbnRegistry — Intelligent Contracts submission copy

Title: IsbnRegistry — on-chain proof that a book is what it claims to be

## Description

Citation registries, reading lists, and academic tools need an on-chain
record that a book actually exists with exactly the title, publisher,
and publication date claimed — not just a string someone typed.
IsbnRegistry is a reusable bibliographic identity primitive for
GenLayer. Anyone registers an ISBN-13; the contract first enforces the
ISBN-13 checksum deterministically, rejecting mistyped or invented
numbers before any record exists. Anyone can then verify the record:
validators independently fetch the same edition record from the Open
Library and must agree exactly on title, publishers, publication date,
ISBN membership, and page count. Only then is the record written as
verified, with the exact source URL. Other contracts and tools can read
a verified record and trust that validators agreed the book is what it
claims to be. There is no LLM in the contract: identity equivalence is
a deterministic field comparison, not a judgment call.

## How consensus is used

The contract itself fetches the web. The leader fetches the Open
Library edition JSON; every validator independently re-fetches the same
URL and accepts the leader's result only if its own record matches
exactly — title after strip, publishers list exactly, publish_date
exactly, an isbn_13 list containing the requested ISBN, and
number_of_pages equal when both sides report one. Any field mismatch
rejects. A failed fetch raises before any write, so the record stays
pending and retryable, and a verified record can never be re-verified
or overwritten. The nondet result carries only strings and ints (the
publishers list travels as one "|"-joined string); no floats ever
cross the nondet boundary. The core result — the verified bibliographic
identity — is produced by GenLayer consensus, not by the caller, not by
one server, and not by an LLM.

## Links

- GitHub: https://github.com/xiaoyu7799/isbnregistry-genlayer
- Contract: https://explorer-studio.genlayer.com/address/0xb560F2C68407DC06430C95a27287d8B3f0564856
- Deploy tx: 0x0fa932d2af21d8fccb64204c406f951d9cba7ea538bb63309ff70602b0790b95
- Register tx (book #0): 0x02d7be9d10060969d64e2309ce39d5a558829747762818a9ff0542006f94499c
- Verify tx (book #0): 0x3fad504afffcd1b0b111056f8a1d8533f51624b043e90685e6e191dec1ce70e3
- Verified book #0: ISBN 9780134685991, "Effective Java", publishers ["Addison-Wesley Professional"], publish_date "December 27, 2017", number_of_pages 416
- Source: https://openlibrary.org/isbn/9780134685991.json
