import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface PnlDisplayProps {
  value: number;
  showIcon?: boolean;
  showSign?: boolean;
  size?: 'sm' | 'md' | 'lg';
  currency?: boolean;
  percent?: boolean;
}

const formatKRW = (value: number): string => {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}백만`;
  }
  if (abs >= 10_000) {
    return `${(value / 10_000).toFixed(1)}만`;
  }
  return value.toLocaleString('ko-KR');
};

const PnlDisplay: React.FC<PnlDisplayProps> = ({
  value,
  showIcon = false,
  showSign = true,
  size = 'md',
  currency = true,
  percent = false,
}) => {
  const isPositive = value > 0;
  const isNegative = value < 0;

  const colorClass = isPositive
    ? 'text-emerald-400'
    : isNegative
      ? 'text-red-400'
      : 'text-gray-400';

  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg font-semibold',
  };

  const Icon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus;

  const displayValue = percent
    ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
    : `${showSign && value > 0 ? '+' : ''}${currency ? '₩' : ''}${formatKRW(value)}`;

  return (
    <span className={`inline-flex items-center gap-1 ${colorClass} ${sizeClasses[size]}`}>
      {showIcon && <Icon className="w-4 h-4" />}
      {displayValue}
    </span>
  );
};

export default PnlDisplay;
