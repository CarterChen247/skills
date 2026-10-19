import { handleRefundEvent } from "../../src/webhooks/refundHandler";
import { db, resetDb, seedCharge } from "../helpers";

const evt = { id: "evt_1", type: "charge.refunded", data: { object: { id: "re_1", charge: "ch_1", amount: 500 } } };

beforeEach(async () => { await resetDb(); await seedCharge({ id: "ch_1", customerId: "cus_1", amount: 2000 }); });

test("applies a refund once", async () => {
  expect(await handleRefundEvent(evt)).toBe("processed");
  expect(await db.balances.get("cus_1")).toBe(500);
});

test("skips an event that was already processed", async () => {
  await db.processedEvents.insert({ eventId: "evt_1", processedAt: new Date() });
  expect(await handleRefundEvent(evt)).toBe("duplicate");
  expect(await db.balances.get("cus_1")).toBe(0);
});

test("rejects unknown charge", async () => {
  await expect(handleRefundEvent({ ...evt, data: { object: { ...evt.data.object, charge: "ch_x" } } })).rejects.toThrow();
});
