import { onOrderPlaced } from "../../../src/orders/events/handlers/handler01";
test("creates projection", () => {
  const p = onOrderPlaced(undefined, { type: "OrderPlaced", orderId: "o1", items: [], total: 0, at: "t" } as any);
  expect(p.status).toBe("placed");
  expect(p.version).toBe(1);
});
