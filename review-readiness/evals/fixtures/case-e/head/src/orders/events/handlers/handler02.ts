import type { OrderEvent, OrderProjection } from "../../types";

// OrderPaid → status paid
export function onOrderPaid(state: OrderProjection, e: OrderEvent<"OrderPaid">): OrderProjection {
  if (state.status !== "placed") return state;
  return { ...state, status: "paid", paidAt: e.at, version: state.version + 1 };
}
