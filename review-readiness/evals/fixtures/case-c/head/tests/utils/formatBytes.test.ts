import { formatBytes } from "../../src/utils/formatBytes";

test.each([
  [0, "0 B"],
  [1, "1 B"],
  [1023, "1023 B"],
  [1024, "1.0 KB"],
  [1536, "1.5 KB"],
  [1024 ** 2, "1.0 MB"],
  [1024 ** 5, "1024.0 TB"],
  [-5, "—"],
  [NaN, "—"],
  [Infinity, "—"],
])("formatBytes(%p) = %p", (input, expected) => {
  expect(formatBytes(input)).toBe(expected);
});
