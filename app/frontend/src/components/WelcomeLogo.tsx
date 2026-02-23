export default function WelcomeLogo() {
  return (
    <div className="welcome-logo">
      <svg viewBox="0 0 120 120" className="welcome-logo-svg">
        <defs>
          <linearGradient id="wl-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>

        {/* Outer circle */}
        <circle cx="60" cy="60" r="56" fill="none" stroke="url(#wl-grad)" strokeWidth="1.5" opacity="0.2" />

        {/* Hex network */}
        <g stroke="url(#wl-grad)" strokeWidth="1" fill="none" opacity="0.3">
          <line x1="60" y1="28" x2="88" y2="44" />
          <line x1="60" y1="28" x2="32" y2="44" />
          <line x1="88" y1="44" x2="88" y2="76" />
          <line x1="32" y1="44" x2="32" y2="76" />
          <line x1="88" y1="76" x2="60" y2="92" />
          <line x1="32" y1="76" x2="60" y2="92" />
          {/* Spokes to center */}
          <line x1="60" y1="28" x2="60" y2="60" />
          <line x1="88" y1="44" x2="60" y2="60" />
          <line x1="32" y1="44" x2="60" y2="60" />
          <line x1="88" y1="76" x2="60" y2="60" />
          <line x1="32" y1="76" x2="60" y2="60" />
          <line x1="60" y1="92" x2="60" y2="60" />
        </g>

        {/* Outer nodes */}
        <circle cx="60" cy="28" r="4" fill="url(#wl-grad)" opacity="0.6" />
        <circle cx="88" cy="44" r="3.5" fill="url(#wl-grad)" opacity="0.5" />
        <circle cx="32" cy="44" r="3.5" fill="url(#wl-grad)" opacity="0.5" />
        <circle cx="88" cy="76" r="3.5" fill="url(#wl-grad)" opacity="0.5" />
        <circle cx="32" cy="76" r="3.5" fill="url(#wl-grad)" opacity="0.5" />
        <circle cx="60" cy="92" r="4" fill="url(#wl-grad)" opacity="0.6" />

        {/* Center hub */}
        <circle cx="60" cy="60" r="14" fill="#eff6ff" stroke="url(#wl-grad)" strokeWidth="1.5" />
        <circle cx="60" cy="60" r="9" fill="url(#wl-grad)" />
        <text x="60" y="64" textAnchor="middle" fill="white" fontSize="8" fontWeight="700" fontFamily="-apple-system, BlinkMacSystemFont, sans-serif" letterSpacing="0.5">AI</text>
      </svg>
    </div>
  );
}
