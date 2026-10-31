/* Simulation only — not consensus evidence.
 *
 * This script performs NO on-chain transactions and proves nothing
 * about GenLayer consensus. It exists only as a cheap pre-flight check:
 * it fetches the live Open Library edition JSON in Node, applies the
 * EXACT same ISBN-13 checksum and exact-field logic the contract uses,
 * and prints PASS/FAIL. The real evidence is the on-chain verify
 * transaction (scripts/flow.mjs) plus evidence.json — never this file.
 *
 * Usage: node scripts/simulate.mjs [isbn13]
 * Default ISBN: 9780134685991 ("Effective Java").
 */
const ISBN = process.argv[2] || "9780134685991";

function fail(msg) {
  console.log("FAIL:", msg);
  process.exit(1);
}

// ISBN-13 checksum, mirroring contracts/isbnregistry.py exactly:
// weights 1, 3 alternating over the first 12 digits;
// check digit = (10 - (sum % 10)) % 10.
function checksumOk(isbn) {
  if (isbn.length !== 13 || !/^\d{13}$/.test(isbn)) return false;
  let total = 0;
  for (let i = 0; i < 12; i++) {
    total += (i % 2 === 0 ? 1 : 3) * Number(isbn[i]);
  }
  return (10 - (total % 10)) % 10 === Number(isbn[12]);
}

console.log("ISBN:", ISBN);
if (!checksumOk(ISBN)) fail("ISBN-13 checksum failed");
console.log("Checksum: PASS");

// A deliberately invalid ISBN must fail the same check (guard against
// a check that passes everything).
if (checksumOk("9780134685992")) fail("checksum accepted a bad check digit");
console.log("Negative checksum control (9780134685992): correctly rejected");

const url = `https://openlibrary.org/isbn/${ISBN}.json`;
console.log("Fetching:", url);
const res = await fetch(url);
if (!res.ok) fail(`Open Library HTTP ${res.status}`);
const data = await res.json();
console.log("Live edition JSON keys:", Object.keys(data).join(", "));

// Exact-field logic, mirroring the contract's fetch + validator:
// title after strip, publishers list exactly, publish_date exactly,
// isbn_13 list containing the ISBN, pages equal when both report one.
const title = typeof data.title === "string" ? data.title.trim() : "";
if (!title) fail("missing title");
const publishers = Array.isArray(data.publishers) ? data.publishers.map((p) => String(p).trim()) : [];
if (publishers.length === 0) fail("missing publishers");
if (!Array.isArray(data.isbn_13) || !data.isbn_13.includes(ISBN)) fail("isbn_13 does not contain the requested ISBN");
const pages = typeof data.number_of_pages === "number" ? data.number_of_pages : null;
console.log("Title:", JSON.stringify(title));
console.log("Publishers:", JSON.stringify(publishers));
console.log("Publish date:", JSON.stringify(data.publish_date));
console.log("Pages:", pages);
console.log("Authors field present in edition JSON:", "authors" in data, "(expected: false — authors live on the work record and are NOT checked)");

if (ISBN === "9780134685991") {
  if (title !== "Effective Java") fail(`unexpected title: ${title}`);
  if (JSON.stringify(publishers) !== JSON.stringify(["Addison-Wesley Professional"])) fail(`unexpected publishers: ${JSON.stringify(publishers)}`);
  if (data.publish_date !== "December 27, 2017") fail(`unexpected publish_date: ${data.publish_date}`);
  if (pages !== 416) fail(`unexpected number_of_pages: ${pages}`);
  console.log("Expected-record assertions: PASS");
}

console.log("SIMULATION PASS — local logic only; on-chain consensus evidence comes from scripts/flow.mjs");
