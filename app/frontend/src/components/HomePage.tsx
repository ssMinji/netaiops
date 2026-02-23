import type { Agent } from "../types";

interface Props {
  agents: Agent[];
  onSelectAgent: (agent: Agent) => void;
}

export default function HomePage({ agents, onSelectAgent }: Props) {
  return (
    <div className="home">
      <div className="home-header">
        <span className="home-logo">🤖</span>
        <h1 className="home-title">NetAIOps Agent Hub</h1>
        <p className="home-subtitle">AI 기반 클라우드 운영 어시스턴트</p>
      </div>

      <div className="agent-cards">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="agent-card"
            onClick={() => onSelectAgent(agent)}
          >
            <span className="agent-card-icon">{agent.icon}</span>
            <div className="agent-card-name">{agent.name}</div>
            <div className="agent-card-desc">{agent.description}</div>
            <div className="agent-card-arrow">
              시작하기 →
            </div>
          </div>
        ))}
      </div>

      <p className="home-hint">에이전트를 선택하여 대화를 시작하세요</p>
    </div>
  );
}
