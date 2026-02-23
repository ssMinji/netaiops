import { useState, useEffect, useCallback, useRef } from "react";
import { fetchConfig, streamChat } from "./api";
import type { Agent, Model, Message } from "./types";
import ChatPage from "./components/ChatPage";
import AgentIcon from "./components/AgentIcon";
import WelcomeLogo from "./components/WelcomeLogo";

interface Session {
  id: string;
  messages: Message[];
}

function generateId(): string {
  return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
}

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [sessions, setSessions] = useState<Record<string, Session>>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeChaos, setActiveChaos] = useState<string[]>([]);
  const [activeFaults, setActiveFaults] = useState<string[]>([]);
  const controllerRef = useRef<AbortController | null>(null);

  // Load config on mount
  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        setAgents(cfg.agents);
        setModels(cfg.models);
        if (cfg.models.length > 0) setSelectedModel(cfg.models[0].id);
      })
      .catch(console.error);
  }, []);

  const getSession = useCallback(
    (agentId: string): Session => {
      if (sessions[agentId]) return sessions[agentId];
      return { id: generateId(), messages: [] };
    },
    [sessions],
  );

  const handleSelectAgent = useCallback(
    (agent: Agent) => {
      if (controllerRef.current) {
        controllerRef.current.abort();
        controllerRef.current = null;
      }
      setIsStreaming(false);
      setSelectedAgent(agent);
      if (!sessions[agent.id]) {
        setSessions((prev) => ({
          ...prev,
          [agent.id]: { id: generateId(), messages: [] },
        }));
      }
    },
    [sessions],
  );

  const handleNewConversation = useCallback(() => {
    if (!selectedAgent) return;
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
    setIsStreaming(false);
    setSessions((prev) => ({
      ...prev,
      [selectedAgent.id]: { id: generateId(), messages: [] },
    }));
  }, [selectedAgent]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!selectedAgent || isStreaming) return;

      const agentId = selectedAgent.id;
      const session = getSession(agentId);

      // Add user message
      const userMsg: Message = { role: "user", content: text };
      const updatedMessages = [...session.messages, userMsg];
      setSessions((prev) => ({
        ...prev,
        [agentId]: { ...session, messages: updatedMessages },
      }));

      // Start streaming
      setIsStreaming(true);
      let assistantContent = "";

      // Add empty assistant message
      setSessions((prev) => ({
        ...prev,
        [agentId]: {
          ...prev[agentId],
          messages: [...updatedMessages, { role: "assistant", content: "" }],
        },
      }));

      const ctrl = await streamChat(
        agentId,
        session.id,
        text,
        selectedModel,
        (chunk) => {
          assistantContent += chunk;
          setSessions((prev) => {
            const s = prev[agentId];
            const msgs = [...s.messages];
            msgs[msgs.length - 1] = { role: "assistant", content: assistantContent };
            return { ...prev, [agentId]: { ...s, messages: msgs } };
          });
        },
        () => setIsStreaming(false),
        (err) => {
          assistantContent += `\n\n_Error: ${err}_`;
          setSessions((prev) => {
            const s = prev[agentId];
            const msgs = [...s.messages];
            msgs[msgs.length - 1] = { role: "assistant", content: assistantContent };
            return { ...prev, [agentId]: { ...s, messages: msgs } };
          });
        },
      );
      controllerRef.current = ctrl;
    },
    [selectedAgent, selectedModel, isStreaming, getSession],
  );

  const handleScenarioClick = useCallback(
    (prompt: string) => {
      if (isStreaming) return;
      handleSend(prompt);
    },
    [isStreaming, handleSend],
  );

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo" onClick={() => { setSelectedAgent(null); }} style={{ cursor: "pointer" }}>
          <span className="sidebar-logo-text">NetAIOps Agent Hub</span>
        </div>

        <div className="sidebar-section-title">Agents</div>
        <div className="sidebar-agent-list">
          {agents.map((a) => (
            <button
              key={a.id}
              className={`sidebar-agent ${selectedAgent?.id === a.id ? "active" : ""}`}
              onClick={() => handleSelectAgent(a)}
            >
              <AgentIcon agentId={a.id} size={22} className="sidebar-agent-icon" />
              <div className="sidebar-agent-info">
                <div className="sidebar-agent-name">{a.name}</div>
                <div className="sidebar-agent-desc">{a.description}</div>
              </div>
            </button>
          ))}
        </div>

        {selectedAgent && selectedAgent.scenarios.length > 0 && (
          <>
            <div className="sidebar-section-title">Scenarios</div>
            <div className="sidebar-scenario-list">
              {selectedAgent.scenarios.map((s) => (
                <button
                  key={s.id}
                  className="sidebar-scenario"
                  onClick={() => handleScenarioClick(s.prompt)}
                >
                  <span className="sidebar-scenario-arrow">▸</span>
                  {s.name}
                </button>
              ))}
            </div>
          </>
        )}
      </aside>

      {/* Main Area */}
      <main className="main-area">
        {selectedAgent ? (
          <ChatPage
            agent={selectedAgent}
            models={models}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            session={getSession(selectedAgent.id)}
            isStreaming={isStreaming}
            activeChaos={activeChaos}
            onActiveChaosChange={setActiveChaos}
            activeFaults={activeFaults}
            onActiveFaultsChange={setActiveFaults}
            onSend={handleSend}
            onNewConversation={handleNewConversation}
          />
        ) : (
          <div className="welcome-screen">
            <WelcomeLogo />
            <h1 className="welcome-title">NetAIOps Agent Hub</h1>
            <p className="welcome-subtitle">AI 기반 클라우드 운영 어시스턴트</p>
            <p className="welcome-hint">← 에이전트를 선택하여 대화를 시작하세요</p>
          </div>
        )}
      </main>
    </div>
  );
}
