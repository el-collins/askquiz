# AskQuiz Mobile App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Expo/React Native (Android) app that lets a student type a question or photograph one, sends it to the backend's `/ask` endpoint with a persisted anonymous device ID, and shows the short answer or a clear error.

**Architecture:** A single-screen app (`AskScreen`) backed by two small, independently-testable modules: `deviceId.ts` (generates/persists a device UUID) and `api.ts` (calls the backend and translates HTTP errors into a typed `AskApiError`). The screen itself is verified manually on a device/emulator, per the spec's explicit call to skip automated mobile component tests for the MVP.

**Tech Stack:** Expo (managed workflow), TypeScript, `expo-image-picker`, `expo-crypto`, `@react-native-async-storage/async-storage`, Jest (`jest-expo` preset) for the two pure-logic modules.

**Spec:** `docs/superpowers/specs/2026-09-24-askquiz-mvp-design.md`

**Depends on:** `docs/superpowers/plans/2026-09-24-askquiz-backend.md` — the app calls the `POST /ask` contract that plan implements (multipart `type`/`content`/`image` fields, `X-Device-Id` header, `{"answer": str}` response, `429`/`400`/`413`/`502` error codes). The backend should be runnable locally (`docker compose up`) before Task 5 of this plan.

## Global Constraints

- Android build only for now; same Expo/React Native codebase keeps iOS cheap to add later (spec section 2).
- No login/accounts — anonymous, device-based identity only (spec sections 2, 4.1).
- No question/answer history is stored or shown — each screen only reflects the current exchange (spec sections 2, 4.1).
- The app never holds or sends a Groq API key — it only ever talks to the backend's `/ask` endpoint (spec section 4.1).
- No automated component/UI tests for the MVP — mobile testing is manual, on a real device/emulator (spec section 7). Only the pure-logic modules (`deviceId.ts`, `api.ts`) get automated tests.
- No response streaming — the app makes one request and waits for one JSON response (spec section 5).

## Review Focus

- Backend unreachable (network error) — expect a clear in-app error message, not a crash or silent hang. → tested in Task 3.
- Rate limit hit (`429`) — expect a specific "hit your limit" message, not a generic error. → tested in Task 3.
- Camera permission denied — expect a clear message rather than a silent failure. → manually verified in Task 4.
- Empty/whitespace-only question submitted — expect the app not to fire a request for nothing. → manually verified in Task 4 (guard already in the handler).
- Ask attempted before the device ID has loaded — expect the Ask/photo buttons to stay disabled rather than firing a request with no device ID. → manually verified in Task 4.

---

### Task 1: Expo project scaffolding

**Files:**
- Create: `mobile/` (via `create-expo-app`)
- Modify: `mobile/app.json`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: a bootable Expo TypeScript project at `mobile/`

- [ ] **Step 1: Scaffold the project**

Run (from the repo root): `npx create-expo-app@latest mobile --template blank-typescript`

- [ ] **Step 2: Install the libraries this plan needs**

Run (from `mobile/`): `npx expo install @react-native-async-storage/async-storage expo-crypto expo-image-picker`

- [ ] **Step 3: Set the app name**

Edit `mobile/app.json`, set `"name"` and `"expo.name"` to `"AskQuiz"`, and `"expo.android.package"` to `"com.askquiz.app"`.

- [ ] **Step 4: Verify the app boots (manual)**

Run: `npx expo start`, open on an Android emulator or Expo Go on a physical device.
Expected: the default template screen renders with no errors.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): scaffold Expo TypeScript project"
```

---

### Task 2: Device ID persistence

**Files:**
- Create: `mobile/src/deviceId.ts`
- Create: `mobile/__tests__/deviceId.test.ts`
- Create: `mobile/jest.config.js`
- Modify: `mobile/package.json`

**Interfaces:**
- Consumes: `@react-native-async-storage/async-storage`, `expo-crypto` (installed in Task 1)
- Produces: `export async function getOrCreateDeviceId(): Promise<string>` in `src/deviceId.ts`

- [ ] **Step 1: Add the Jest setup**

Run (from `mobile/`): `npx expo install jest-expo --dev` then `npm install --save-dev jest @types/jest`

Add to `mobile/package.json` scripts: `"test": "jest"`

```javascript
// mobile/jest.config.js
module.exports = {
  preset: "jest-expo",
};
```

- [ ] **Step 2: Write the failing tests**

```typescript
// mobile/__tests__/deviceId.test.ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Crypto from "expo-crypto";
import { getOrCreateDeviceId } from "../src/deviceId";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

jest.mock("expo-crypto", () => ({
  randomUUID: jest.fn(),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  (Crypto.randomUUID as jest.Mock).mockReset();
});

test("creates and persists a new device id on first call", async () => {
  (Crypto.randomUUID as jest.Mock).mockReturnValue("generated-uuid");

  const id = await getOrCreateDeviceId();

  expect(id).toBe("generated-uuid");
  expect(await AsyncStorage.getItem("askquiz_device_id")).toBe("generated-uuid");
});

test("returns the existing device id on subsequent calls", async () => {
  await AsyncStorage.setItem("askquiz_device_id", "existing-uuid");

  const id = await getOrCreateDeviceId();

  expect(id).toBe("existing-uuid");
  expect(Crypto.randomUUID).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run (from `mobile/`): `npm test -- deviceId`
Expected: FAIL with `Cannot find module '../src/deviceId'`

- [ ] **Step 4: Write the minimal implementation**

```typescript
// mobile/src/deviceId.ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Crypto from "expo-crypto";

const DEVICE_ID_KEY = "askquiz_device_id";

export async function getOrCreateDeviceId(): Promise<string> {
  const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }
  const newId = Crypto.randomUUID();
  await AsyncStorage.setItem(DEVICE_ID_KEY, newId);
  return newId;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm test -- deviceId`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add mobile/src/deviceId.ts mobile/__tests__/deviceId.test.ts mobile/jest.config.js mobile/package.json mobile/package-lock.json
git commit -m "feat(mobile): add persisted anonymous device id"
```

---

### Task 3: Backend API client

**Files:**
- Create: `mobile/src/api.ts`
- Create: `mobile/__tests__/api.test.ts`

**Interfaces:**
- Consumes: the backend's `POST /ask` contract (multipart `type`/`content`/`image`, `X-Device-Id` header, `{"answer": str}` / `429`/`400`/`413`/`502` — defined in `docs/superpowers/plans/2026-09-24-askquiz-backend.md` Task 4)
- Produces: `export async function askText(deviceId: string, content: string): Promise<string>`; `export async function askImage(deviceId: string, uri: string, mimeType: string): Promise<string>`; `export class AskApiError extends Error { status: number }` — all in `src/api.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// mobile/__tests__/api.test.ts
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mobile/`): `npm test -- api`
Expected: FAIL with `Cannot find module '../src/api'`

- [ ] **Step 3: Write the minimal implementation**

```typescript
// mobile/src/api.ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- api`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add mobile/src/api.ts mobile/__tests__/api.test.ts
git commit -m "feat(mobile): add backend API client with typed errors"
```

---

### Task 4: Ask screen UI

**Files:**
- Create: `mobile/src/AskScreen.tsx`
- Modify: `mobile/App.tsx`

**Interfaces:**
- Consumes: `getOrCreateDeviceId` from `src/deviceId.ts` (Task 2); `askText`, `askImage`, `AskApiError` from `src/api.ts` (Task 3)
- Produces: default-exported `AskScreen` component in `src/AskScreen.tsx`, rendered from `App.tsx`

No automated tests for this task — per the spec, mobile UI verification is manual. Each step below is a manual check to run on a device/emulator.

- [ ] **Step 1: Implement the screen**

```typescript
// mobile/src/AskScreen.tsx
import React, { useEffect, useState } from "react";
import {
  View,
  TextInput,
  Button,
  Text,
  ActivityIndicator,
  StyleSheet,
  Image,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { getOrCreateDeviceId } from "./deviceId";
import { askText, askImage, AskApiError } from "./api";

export default function AskScreen() {
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getOrCreateDeviceId().then(setDeviceId);
  }, []);

  async function handleAskText() {
    if (!deviceId || !question.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await askText(deviceId, question.trim());
      setAnswer(result);
    } catch (err) {
      setError(err instanceof AskApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePickImage() {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setError("Camera permission is required to photograph a question.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    if (result.canceled || !result.assets?.length) return;

    const asset = result.assets[0];
    setImageUri(asset.uri);

    if (!deviceId) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const mimeType = asset.mimeType ?? "image/jpeg";
      const answerText = await askImage(deviceId, asset.uri, mimeType);
      setAnswer(answerText);
    } catch (err) {
      setError(err instanceof AskApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="Type your question..."
        value={question}
        onChangeText={setQuestion}
      />
      <Button title="Ask" onPress={handleAskText} disabled={!deviceId || loading} />
      <Button
        title="Photograph a question"
        onPress={handlePickImage}
        disabled={!deviceId || loading}
      />
      {imageUri && <Image source={{ uri: imageUri }} style={styles.preview} />}
      {loading && <ActivityIndicator />}
      {error && <Text style={styles.error}>{error}</Text>}
      {answer && <Text style={styles.answer}>{answer}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, justifyContent: "center" },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  preview: { width: 200, height: 200, marginVertical: 12, alignSelf: "center" },
  error: { color: "red", marginTop: 12 },
  answer: { fontSize: 18, fontWeight: "600", marginTop: 12 },
});
```

```typescript
// mobile/App.tsx
import { SafeAreaView } from "react-native";
import AskScreen from "./src/AskScreen";

export default function App() {
  return (
    <SafeAreaView style={{ flex: 1 }}>
      <AskScreen />
    </SafeAreaView>
  );
}
```

- [ ] **Step 2: Manually verify the text flow**

With the backend running locally (see Task 5), run `npx expo start` and open the app. Type a question, tap "Ask".
Expected: a short answer appears; the Ask button is disabled while loading.

- [ ] **Step 3: Manually verify the image flow**

Tap "Photograph a question", grant camera permission, photograph a sample multiple-choice question.
Expected: an image preview appears, followed by a short answer.

- [ ] **Step 4: Manually verify the Review Focus error cases**

- Deny the camera permission when prompted → expect the "Camera permission is required..." message, no crash.
- Tap "Ask" with an empty or whitespace-only question → expect nothing happens (no request fires, no loading spinner).
- Stop the backend (`docker compose down` in `backend/`) and tap "Ask" → expect "Couldn't get an answer, try again."
- Reload the app immediately and tap "Ask" before the device ID could plausibly have loaded → expect the button to be disabled until `deviceId` is set.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/AskScreen.tsx mobile/App.tsx
git commit -m "feat(mobile): add ask screen with text and image input"
```

---

### Task 5: End-to-end smoke test against the real backend

**Files:**
- Create: `mobile/.env.example`

**Interfaces:**
- Consumes: the full backend stack from `docs/superpowers/plans/2026-09-24-askquiz-backend.md`
- Produces: a confirmed working end-to-end flow; no new code interfaces

- [ ] **Step 1: Document the API base URL**

```text
# mobile/.env.example
# Android emulator (AVD) reaching your host machine: use 10.0.2.2
# Physical device on the same network: use your machine's LAN IP
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000
```

- [ ] **Step 2: Start the backend**

From `backend/`: `docker compose up --build -d` (see the backend plan's Task 5 for full setup).

- [ ] **Step 3: Point the app at the backend**

Set `EXPO_PUBLIC_API_BASE_URL` in `mobile/.env` (copy from `.env.example`, adjusting for emulator vs. physical device), then `npx expo start`.

- [ ] **Step 4: Run one full text round trip**

Type a real question, tap "Ask".
Expected: a short, correct answer appears within a few seconds.

- [ ] **Step 5: Run one full image round trip**

Photograph a real multiple-choice question.
Expected: a short, correct answer appears within a few seconds.

- [ ] **Step 6: Verify the rate-limit UX end-to-end**

In `backend/.env`, set `DAILY_REQUEST_CAP=1`, restart the backend (`docker compose up -d --build`), send two questions from the app with the same device.
Expected: the second attempt shows "You've hit today's limit."

- [ ] **Step 7: Restore defaults and commit**

Reset `backend/.env`'s `DAILY_REQUEST_CAP` to a real value and stop the backend (`docker compose down`).

```bash
git add mobile/.env.example
git commit -m "chore(mobile): document API base URL for local/device testing"
```
