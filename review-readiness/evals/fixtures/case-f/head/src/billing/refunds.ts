import type { Tx } from "../db";

/** Credits `amount` (minor units) back to the customer balance for `chargeId`. Not idempotent. */
export async function applyRefund(tx: Tx, chargeId: string, amount: number): Promise<void> {
  const charge = await tx.charges.findOne({ id: chargeId });
  if (!charge) throw new Error(`unknown charge ${chargeId}`);
  await tx.balances.increment({ customerId: charge.customerId }, amount);
  await tx.charges.update({ id: chargeId }, { refunded: charge.refunded + amount });
}
