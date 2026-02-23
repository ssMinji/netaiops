import type { AppConfig } from "./types";

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch("./api/config");
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function streamChat(
  agentId: string,
  sessionId: string,
  message: string,
  modelId: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
) {
  const controller = new AbortController();

  try {
    const res = await fetch("./api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: agentId,
        session_id: sessionId,
        message,
        model_id: modelId,
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text();
      onError(`Error (${res.status}): ${text}`);
      onDone();
      return controller;
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        if (trimmed === "data: [DONE]") {
          onDone();
          return controller;
        }
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            onChunk(data.content);
          } catch {
            // skip malformed chunks
          }
        }
      }
    }

    onDone();
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return controller;
    onError(String(err));
    onDone();
  }

  return controller;
}

export async function triggerChaos(scenario: string): Promise<Record<string, unknown>> {
  const res = await fetch("./api/chaos/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  return res.json();
}

export async function cleanupChaos(): Promise<Record<string, unknown>> {
  const res = await fetch("./api/chaos/cleanup", { method: "POST" });
  return res.json();
}

export async function getChaosStatus(): Promise<{ active: string[] }> {
  const res = await fetch("./api/chaos/status");
  return res.json();
}

// -- Istio fault injection -------------------------------------------------
export async function applyFault(faultType: string): Promise<Record<string, unknown>> {
  const res = await fetch("./api/fault/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fault_type: faultType }),
  });
  return res.json();
}

export async function removeFault(faultType: string): Promise<Record<string, unknown>> {
  const res = await fetch("./api/fault/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fault_type: faultType }),
  });
  return res.json();
}

export async function cleanupFaults(): Promise<Record<string, unknown>> {
  const res = await fetch("./api/fault/cleanup", { method: "POST" });
  return res.json();
}

export async function getFaultStatus(): Promise<{ active: string[] }> {
  const res = await fetch("./api/fault/status");
  return res.json();
}
