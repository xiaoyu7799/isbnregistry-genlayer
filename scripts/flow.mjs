/* End-to-end on-chain flow against an already-deployed IsbnRegistry contract.
 *
 * Usage:
 *   CONTRACT_ADDRESS=0x... GENLAYER_PRIVATE_KEY=0x... node scripts/flow.mjs
 *   # or without a key: an ephemeral account is used (permissionless writes).
 *
 * Steps: register ISBN 9780134685991 -> verify it on-chain (validators
 * fetch the Open Library edition record and must agree on title,
 * publishers, publish_date, ISBN membership and page count exactly) ->
 * read it back and assert the expected verified fields. Writes
 * evidence.json (tx hashes, final status, verified record). No key is
 * ever written to disk.
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createClient, createAccount, generatePrivateKey } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import { TransactionStatus } from "genlayer-js/types";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const deployment = JSON.parse(readFileSync(path.join(root, "deployment.json"), "utf-8"));
const address = process.env.CONTRACT_ADDRESS || deployment.contractAddress;
if (!address) throw new Error("No contract address: set CONTRACT_ADDRESS or run deploy first");

const account = createAccount(process.env.GENLAYER_PRIVATE_KEY || generatePrivateKey());
console.log("Flow account:", account.address);
console.log("Contract:", address);
const client = createClient({ chain: studionet, account });

async function waitFinal(hash, label) {
  console.log(`${label} tx:`, hash);
  const receipt = await client.waitForTransactionReceipt({
    hash,
    status: TransactionStatus.FINALIZED,
    retries: 180,
    interval: 5000,
  });
  console.log(`${label} final:`, receipt.statusName ?? receipt.status);
  return receipt;
}

const ISBN = "9780134685991";
const registerTx = await client.writeContract({
  address,
  functionName: "register_isbn",
  args: [ISBN],
  value: 0n,
  leaderOnly: false,
});
await waitFinal(registerTx, "register");

const countRaw = await client.readContract({ address, functionName: "get_count", args: [] });
const count = Number(countRaw);
console.log("Book count:", count);
const id = BigInt(count - 1);

const verifyTx = await client.writeContract({
  address,
  functionName: "verify_isbn",
  args: [id],
  value: 0n,
  leaderOnly: false,
});
const verifyReceipt = await waitFinal(verifyTx, "verify");

const recordRaw = await client.readContract({
  address,
  functionName: "get_book",
  args: [id],
});
const record = typeof recordRaw === "string" ? JSON.parse(recordRaw) : recordRaw;
console.log("Verified record:", JSON.stringify(record, null, 2));
if (record.status !== "verified") throw new Error("Flow did not produce a verified record");
if (record.title !== "Effective Java") throw new Error(`Unexpected title: ${record.title}`);
if (JSON.stringify(record.publishers) !== JSON.stringify(["Addison-Wesley Professional"])) {
  throw new Error(`Unexpected publishers: ${JSON.stringify(record.publishers)}`);
}
if (record.publish_date !== "December 27, 2017") throw new Error(`Unexpected publish_date: ${record.publish_date}`);
if (record.number_of_pages !== 416) throw new Error(`Unexpected number_of_pages: ${record.number_of_pages}`);

const evidence = {
  network: "Stable Studionet",
  chainId: 61999,
  rpcUrl: "https://studio.genlayer.com/api",
  contractAddress: address,
  explorer: `https://explorer-studio.genlayer.com/address/${address}`,
  flowAccount: account.address,
  bookId: Number(id),
  isbn13: ISBN,
  registerTxHash: registerTx,
  verifyTxHash: verifyTx,
  verifyReceiptStatus: verifyReceipt.statusName ?? ({ 0: "UNINITIALIZED", 1: "PENDING", 2: "PROPOSING", 3: "COMMITTING", 4: "REVEALING", 5: "ACCEPTED", 6: "UNDETERMINED", 7: "FINALIZED", 8: "CANCELED" }[verifyReceipt.status] ?? String(verifyReceipt.status ?? "")),
  record,
  checkedAt: new Date().toISOString(),
};
writeFileSync(path.join(root, "evidence.json"), JSON.stringify(evidence, null, 2) + "\n");
console.log("Wrote evidence.json");
