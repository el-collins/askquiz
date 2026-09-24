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
