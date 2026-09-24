const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class AskApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "AskApiError";
    this.status = status;
  }
}

async function postAsk(deviceId: string, form: FormData): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/ask`, {
      method: "POST",
      headers: { "X-Device-Id": deviceId },
      body: form,
    });
  } catch {
    throw new AskApiError(0, "Network request failed");
  }

  if (response.status === 429) {
    throw new AskApiError(429, "You've hit today's limit.");
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
