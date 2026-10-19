import { db } from "../db";
import { applyRefund } from "../billing/refunds";
import { logger } from "../logger";

export interface StripeEvent {
  id: string; // evt_...
  type: string;
  data: { object: { id: string /* re_... */; charge: string; amount: number } };
}

/**
 * Handles `charge.refunded` webhooks. Stripe may deliver the same event more than once,
 * so we record processed event IDs and skip duplicates.
 */
export async function handleRefundEvent(event: StripeEvent): Promise<"processed" | "duplicate"> {
  const refund = event.data.object;

  const seen = await db.processedEvents.findOne({ eventId: event.id });
  if (seen) {
    logger.info("duplicate refund event", { eventId: event.id });
    return "duplicate";
  }

  await db.transaction(async (tx) => {
    await applyRefund(tx, refund.charge, refund.amount);
    await tx.processedEvents.insert({ eventId: refund.id, processedAt: new Date() });
  });

  return "processed";
}
