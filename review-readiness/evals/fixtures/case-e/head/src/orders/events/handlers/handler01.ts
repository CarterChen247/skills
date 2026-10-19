import type { OrderEvent, OrderProjection } from "../../types";

// OrderPlaced → initial projection
export function onOrderPlaced(state: OrderProjection | undefined, e: OrderEvent<"OrderPlaced">): OrderProjection {
  return { id: e.orderId, status: "placed", items: e.items, total: e.total, version: (state?.version ?? 0) + 1 };
}
