import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Agent, Model, Message } from "../types";
import ChaosPanel from "./ChaosPanel";
import FaultPanel from "./FaultPanel";
import AgentIcon from "./AgentIcon";

interface Session {
  id: string;
  messages: Message[];
}

interface Props {
  agent: Agent;
  models: Model[];
  selectedModel: string;
  onModelChange: (id: string) => void;
  session: Session;
  isStreaming: boolean;
  activeChaos: string[];
  onActiveChaosChange: (chaos: string[]) => void;
  activeFaults: string[];
  onActiveFaultsChange: (faults: string[]) => void;
  onSend: (text: string) => void;
  onNewConversation: () => void;
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <div className="typing-dot" />
      <div className="typing-dot" />
      <div className="typing-dot" />
    </div>
  );
}

export default function ChatPage({
  agent,
  models,
  selectedModel,
  onModelChange,
  session,
  isStreaming,
  activeChaos,
  onActiveChaosChange,
  activeFaults,
  onActiveFaultsChange,
  onSend,
  onNewConversation,
}: Props) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesAreaRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.messages]);

  // Auto-resize textarea
  const adjustTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  }, []);

  useEffect(() => {
    adjustTextarea();
  }, [input, adjustTextarea]);

  // Focus input on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    onSend(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isIncident = agent.id === "incident";
  const isIstio = agent.id === "istio";
  const isEmpty = session.messages.length === 0;

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-info">
          <div className="chat-header-title">
            <AgentIcon agentId={agent.id} size={18} className="chat-header-agent-icon" />
            {agent.name}
          </div>
        </div>
        <div className="chat-header-controls">
          {isIncident && (
            <ChaosPanel
              activeChaos={activeChaos}
              onActiveChaosChange={onActiveChaosChange}
            />
          )}
          {isIstio && (
            <FaultPanel
              activeFaults={activeFaults}
              onActiveFaultsChange={onActiveFaultsChange}
            />
          )}
          <select
            className="model-select"
            value={selectedModel}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <button className="header-btn" onClick={onNewConversation}>
            + New Chat
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="messages-area" ref={messagesAreaRef}>
        {isEmpty ? (
          <div className="messages-empty">
            <div className="messages-empty-icon"><AgentIcon agentId={agent.id} size={40} /></div>
            <div className="messages-empty-text">{agent.name}</div>
            <div className="messages-empty-hint">{agent.description}</div>
          </div>
        ) : (
          <>
            {session.messages.map((msg, i) => {
              const isLastAssistant =
                msg.role === "assistant" && i === session.messages.length - 1;
              return (
                <div key={i} className="message">
                  <div className={`message-avatar ${msg.role}`}>
                    {msg.role === "user" ? "U" : <AgentIcon agentId={agent.id} size={18} />}
                  </div>
                  <div className="message-content">
                    {msg.role === "assistant" && msg.content === "" && isStreaming ? (
                      <TypingIndicator />
                    ) : (
                      <>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                        {isLastAssistant && isStreaming && (
                          <TypingIndicator />
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="chat-bottom">
        <div className="chat-input-container">
          <div className="chat-input-wrapper">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={agent.placeholder}
              rows={1}
              disabled={isStreaming}
            />
            <button
              className="send-button"
              onClick={handleSubmit}
              disabled={!input.trim() || isStreaming}
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
