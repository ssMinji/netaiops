interface Props {
  agentId: string;
  size?: number;
  className?: string;
}

function K8sIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      {/* Hexagon */}
      <path d="M12 2l8.5 5v10L12 22l-8.5-5V7L12 2z" />
      {/* Wheel spokes */}
      <circle cx="12" cy="12" r="3" />
      <line x1="12" y1="9" x2="12" y2="5" />
      <line x1="14.6" y1="10.5" x2="17.8" y2="8.5" />
      <line x1="14.6" y1="13.5" x2="17.8" y2="15.5" />
      <line x1="12" y1="15" x2="12" y2="19" />
      <line x1="9.4" y1="13.5" x2="6.2" y2="15.5" />
      <line x1="9.4" y1="10.5" x2="6.2" y2="8.5" />
    </svg>
  );
}

function IncidentIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      {/* Shield */}
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      {/* Pulse line */}
      <polyline points="8 12 10 12 11 9 13 15 14 12 16 12" />
    </svg>
  );
}

function IstioIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      {/* Mesh nodes */}
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="6" r="2" />
      <circle cx="12" cy="12" r="2" />
      <circle cx="5" cy="18" r="2" />
      <circle cx="19" cy="18" r="2" />
      {/* Connections */}
      <line x1="7" y1="6" x2="10" y2="11" />
      <line x1="17" y1="6" x2="14" y2="11" />
      <line x1="7" y1="18" x2="10" y2="13" />
      <line x1="17" y1="18" x2="14" y2="13" />
      <line x1="7" y1="7" x2="17" y2="17" opacity="0.3" />
      <line x1="17" y1="7" x2="7" y2="17" opacity="0.3" />
    </svg>
  );
}

function DefaultIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </svg>
  );
}

export default function AgentIcon({ agentId, size = 20, className }: Props) {
  const iconMap: Record<string, React.ReactNode> = {
    k8s: <K8sIcon size={size} />,
    incident: <IncidentIcon size={size} />,
    istio: <IstioIcon size={size} />,
  };

  return (
    <span className={className} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
      {iconMap[agentId] ?? <DefaultIcon size={size} />}
    </span>
  );
}
