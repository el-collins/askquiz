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
