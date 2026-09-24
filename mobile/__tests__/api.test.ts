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
  const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(url).toBe("http://localhost:8000/ask");
  expect(options.method).toBe("POST");
  expect(options.headers["X-Device-Id"]).toBe("device-1");
});

test("askText throws AskApiError with status 429 when rate limited", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 429,
    json: async () => ({}),
  });

  await expect(askText("device-1", "hi")).rejects.toMatchObject({
    status: 429,
    message: "You've hit today's limit.",
  });
});

test("askText throws AskApiError with a specific message on 413", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 413,
    json: async () => ({}),
  });

  await expect(askText("device-1", "hi")).rejects.toMatchObject({
    status: 413,
    message: "That photo is too large. Try again with a smaller image.",
  });
});

test("askText throws AskApiError with the generic message on other server errors", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 502,
    json: async () => ({}),
  });

  await expect(askText("device-1", "hi")).rejects.toMatchObject({
    status: 502,
    message: "Couldn't get an answer, try again.",
  });
});

test("askText throws AskApiError with status 0 on network failure", async () => {
  (global.fetch as jest.Mock).mockRejectedValue(new Error("offline"));

  await expect(askText("device-1", "hi")).rejects.toMatchObject({
    status: 0,
    message: "Couldn't get an answer, try again.",
  });
});

test("askText throws AskApiError with status 0 after the request times out", async () => {
  jest.useFakeTimers();
  (global.fetch as jest.Mock).mockImplementation((_url: string, options: RequestInit) => {
    return new Promise((_resolve, reject) => {
      options.signal?.addEventListener("abort", () => {
        const err = new Error("aborted");
        err.name = "AbortError";
        reject(err);
      });
    });
  });

  const promise = askText("device-1", "hi");
  const assertion = expect(promise).rejects.toMatchObject({
    status: 0,
    message: "Couldn't get an answer, try again.",
  });
  jest.advanceTimersByTime(30_000);
  await assertion;
  jest.useRealTimers();
});

test("askImage sends the multipart fields the backend expects", async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ answer: "B. Paris" }),
  });
  const appendSpy = jest.spyOn(FormData.prototype, "append");

  const answer = await askImage("device-1", "file:///photo.jpg", "image/jpeg");

  expect(answer).toBe("B. Paris");
  expect(appendSpy).toHaveBeenCalledWith("type", "image");
  expect(appendSpy).toHaveBeenCalledWith(
    "image",
    expect.objectContaining({ uri: "file:///photo.jpg", type: "image/jpeg" })
  );
  const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(url).toBe("http://localhost:8000/ask");
  expect(options.method).toBe("POST");
  expect(options.headers["X-Device-Id"]).toBe("device-1");

  appendSpy.mockRestore();
});
