import { askText, askImage } from "../src/api";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("askText returns the answer on success", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ answer: "B. Queue" }),
  });

  const answer = await askText("device-1", "Which data structure uses FIFO?");

  expect(answer).toBe("B. Queue");
  const [, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(options.headers["X-Device-Id"]).toBe("device-1");
});

test("askText throws AskApiError with status 429 when rate limited", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 429,
    json: async () => ({}),
  });

  await expect(askText("device-1", "hi")).rejects.toMatchObject({ status: 429 });
});

test("askText throws AskApiError with status 0 on network failure", async () => {
  (global.fetch as jest.Mock).mockRejectedValue(new Error("offline"));

  await expect(askText("device-1", "hi")).rejects.toMatchObject({ status: 0 });
});

test("askImage submits a multipart form and returns the answer", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ answer: "B. Paris" }),
  });

  const answer = await askImage("device-1", "file:///photo.jpg", "image/jpeg");

  expect(answer).toBe("B. Paris");
});
