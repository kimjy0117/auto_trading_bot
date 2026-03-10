import React from 'react';

const SESSION_CONFIG: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  PRE_MARKET: {
    label: '프리마켓',
    bg: 'bg-purple-500/15 border-purple-500/30',
    text: 'text-purple-300',
    dot: 'bg-purple-400',
  },
  REGULAR: {
    label: '정규장',
    bg: 'bg-blue-500/15 border-blue-500/30',
    text: 'text-blue-300',
    dot: 'bg-blue-400',
  },
  AFTER_MARKET: {
    label: '애프터마켓',
    bg: 'bg-orange-500/15 border-orange-500/30',
    text: 'text-orange-300',
    dot: 'bg-orange-400',
  },
  CLOSED: {
    label: '마감',
    bg: 'bg-gray-500/15 border-gray-500/30',
    text: 'text-gray-400',
    dot: 'bg-gray-500',
  },
};

interface SessionBadgeProps {
  session: string;
  size?: 'sm' | 'md' | 'lg';
  showDot?: boolean;
}

const SessionBadge: React.FC<SessionBadgeProps> = ({ session, size = 'sm', showDot = true }) => {
  const config = SESSION_CONFIG[session] ?? SESSION_CONFIG.CLOSED;

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-sm px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.bg} ${config.text} ${sizeClasses[size]}`}
    >
      {showDot && (
        <span className={`w-1.5 h-1.5 rounded-full ${config.dot} ${session !== 'CLOSED' ? 'animate-pulse' : ''}`} />
      )}
      {config.label}
    </span>
  );
};

export default SessionBadge;
