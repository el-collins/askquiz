import React, { useEffect, useRef, useState } from "react";
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
import * as ImageManipulator from "expo-image-manipulator";
import { getOrCreateDeviceId } from "./deviceId";
import { askText, askImage, AskApiError } from "./api";

const MAX_IMAGE_DIMENSION = 1600;

export default function AskScreen() {
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const lastActionRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    getOrCreateDeviceId().then(setDeviceId);
  }, []);

  function resetExchange() {
    setAnswer(null);
    setError(null);
  }

  async function runAskText(id: string, content: string) {
    setImageUri(null);
    resetExchange();
    setLoading(true);
    try {
      const result = await askText(id, content);
      setAnswer(result);
    } catch (err) {
      setError(err instanceof AskApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAskText() {
    if (!deviceId || !question.trim()) return;
    const id = deviceId;
    const content = question.trim();
    lastActionRef.current = () => runAskText(id, content);
    await runAskText(id, content);
  }

  async function runAskImage(id: string, pickedUri: string) {
    resetExchange();
    setImageUri(pickedUri);
    setLoading(true);
    try {
      const resized = await ImageManipulator.manipulateAsync(
        pickedUri,
        [{ resize: { width: MAX_IMAGE_DIMENSION } }],
        { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG }
      );
      const result = await askImage(id, resized.uri, "image/jpeg");
      setAnswer(result);
    } catch (err) {
      setError(err instanceof AskApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCameraPress() {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      resetExchange();
      setImageUri(null);
      setError("Camera permission is required to photograph a question.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    if (result.canceled || !result.assets?.length) return;
    if (!deviceId) return;

    const id = deviceId;
    const pickedUri = result.assets[0].uri;
    lastActionRef.current = () => runAskImage(id, pickedUri);
    await runAskImage(id, pickedUri);
  }

  async function handleGalleryPress() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.7,
    });
    if (result.canceled || !result.assets?.length) return;
    if (!deviceId) return;

    const id = deviceId;
    const pickedUri = result.assets[0].uri;
    lastActionRef.current = () => runAskImage(id, pickedUri);
    await runAskImage(id, pickedUri);
  }

  function handleRetry() {
    lastActionRef.current?.();
  }

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="Type your question..."
        value={question}
        onChangeText={setQuestion}
        multiline
      />
      <Button title="Ask" onPress={handleAskText} disabled={!deviceId || loading} />
      <Button
        title="Photograph a question"
        onPress={handleCameraPress}
        disabled={!deviceId || loading}
      />
      <Button
        title="Choose from gallery"
        onPress={handleGalleryPress}
        disabled={!deviceId || loading}
      />
      {imageUri && <Image source={{ uri: imageUri }} style={styles.preview} />}
      {loading && <ActivityIndicator />}
      {error && (
        <View>
          <Text style={styles.error}>{error}</Text>
          {lastActionRef.current && (
            <Button title="Retry" onPress={handleRetry} disabled={loading} />
          )}
        </View>
      )}
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
    minHeight: 44,
  },
  preview: { width: 200, height: 200, marginVertical: 12, alignSelf: "center" },
  error: { color: "red", marginTop: 12 },
  answer: { fontSize: 18, fontWeight: "600", marginTop: 12 },
});
