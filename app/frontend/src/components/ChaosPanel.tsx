import { useState } from "react";
import { triggerChaos, cleanupChaos } from "../api";

interface Props {
  activeChaos: string[];
  onActiveChaosChange: (chaos: string[]) => void;
}

const CHAOS_SCENARIOS = [
  { tool: "chaos-cpu-stress", label: "CPU Stress", icon: "🔥" },
  { tool: "chaos-error-injection", label: "Error Injection", icon: "💥" },
  { tool: "chaos-latency-injection", label: "Latency Injection", icon: "🐌" },
  { tool: "chaos-pod-crash", label: "Pod Crash", icon: "💀" },
];

export default function ChaosPanel({ activeChaos, onActiveChaosChange }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);

  const handleTrigger = async (tool: string, label: string) => {
    setLoading(tool);
    try {
      const result = await triggerChaos(tool);
      if (result.status === "success") {
        onActiveChaosChange([...activeChaos, label]);
      }
    } catch {
      // ignore
    } finally {
      setLoading(null);
    }
  };

  const handleCleanup = async () => {
    setLoading("cleanup");
    try {
      const result = await cleanupChaos();
      if (result.status === "success" || result.status === "partial") {
        onActiveChaosChange([]);
      }
    } catch {
      // ignore
    } finally {
      setLoading(null);
    }
  };

  return (
    <>
      <button
        className={`chaos-toggle ${activeChaos.length > 0 ? "has-active" : ""}`}
        onClick={() => setExpanded(!expanded)}
      >
        ⚡ Trigger Incident{activeChaos.length > 0 ? ` (${activeChaos.length})` : ""}
      </button>

      <div className={`chaos-panel ${expanded ? "expanded" : ""}`}>
        <div className="chaos-content">
          <span className="chaos-label">Scenarios:</span>
          {CHAOS_SCENARIOS.map(({ tool, label, icon }) => {
            const isActive = activeChaos.includes(label);
            return (
              <button
                key={tool}
                className={`chaos-btn ${isActive ? "active" : ""}`}
                onClick={() => handleTrigger(tool, label)}
                disabled={loading !== null}
              >
                {icon} {label}
                {loading === tool && " ..."}
                {isActive && " ●"}
              </button>
            );
          })}
          {activeChaos.length > 0 && (
            <button
              className="chaos-btn cleanup"
              onClick={handleCleanup}
              disabled={loading !== null}
            >
              🧹 Cleanup All
              {loading === "cleanup" && " ..."}
            </button>
          )}
        </div>
      </div>
    </>
  );
}
