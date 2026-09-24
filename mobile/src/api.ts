const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 28_000; // stays above the backend's 15s Groq timeout

export class AskApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "AskApiError";
    this.status = status;
  }
}

async function postAsk(deviceId: string, form: FormData): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/ask`, {
      method: "POST",
      headers: { "X-Device-Id": deviceId },
      body: form,
      signal: controller.signal,
    });
  } catch {
    throw new AskApiError(0, "Couldn't get an answer, try again.");
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 429) {
    throw new AskApiError(429, "You've hit today's limit.");
  }
  if (response.status === 413) {
    throw new AskApiError(413, "That photo is too large. Try again with a smaller image.");
  }
  if (!response.ok) {
    throw new AskApiError(response.status, "Couldn't get an answer, try again.");
  }

  const data = await response.json();
  return data.answer as string;
}

export async function askText(deviceId: string, content: string): Promise<string> {
  const form = new FormData();
  form.append("type", "text");
  form.append("content", content);
  return postAsk(deviceId, form);
}

export async function askImage(
  deviceId: string,
  uri: string,
  mimeType: string
): Promise<string> {
  const form = new FormData();
  form.append("type", "image");
  form.append("image", {
    uri,
    name: "question.jpg",
    type: mimeType,
  } as unknown as Blob);
  return postAsk(deviceId, form);
}
