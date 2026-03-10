import React, { useEffect, useState, useCallback } from 'react';
import { Wallet, PiggyBank, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';
import { fetchAccountBalance, type AccountBalance } from '../api/client';
import PnlDisplay from './PnlDisplay';

interface Props {
  compact?: boolean;
}

const formatKRW = (value: number): string => {
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `${(value / 10_000).toFixed(0)}만`;
  return value.toLocaleString('ko-KR');
};

const AccountBalanceCard: React.FC<Props> = ({ compact = false }) => {
  const [balance, setBalance] = useState<AccountBalance | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetchAccountBalance();
      setBalance(res.data);
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  if (error && !balance) return null;
  if (!balance) return null;

  const investRatio =
    balance.total_evaluation > 0
      ? ((balance.purchase_amount / balance.total_evaluation) * 100)
      : 0;

  if (compact) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500/20 to-blue-500/20">
            <Wallet className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <p className="text-xs text-gray-500 font-medium">총 자산</p>
            <p className="text-lg font-bold text-white">
              ₩{formatKRW(balance.total_evaluation)}
            </p>
          </div>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-500">예수금</span>
          <span className="text-gray-300 font-mono">₩{formatKRW(balance.available_cash)}</span>
        </div>
        <div className="flex items-center justify-between text-xs mt-1">
          <span className="text-gray-500">평가손익</span>
          <PnlDisplay value={balance.eval_pnl} size="sm" showSign />
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <Wallet className="w-4 h-4 text-indigo-400" />
        <h3 className="text-sm font-semibold text-gray-300">내 계좌</h3>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <DollarSign className="w-3.5 h-3.5 text-indigo-400" />
            <p className="text-[11px] text-gray-500 font-medium">총평가</p>
          </div>
          <p className="text-lg font-bold text-white">₩{formatKRW(balance.total_evaluation)}</p>
        </div>
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <PiggyBank className="w-3.5 h-3.5 text-cyan-400" />
            <p className="text-[11px] text-gray-500 font-medium">예수금</p>
          </div>
          <p className="text-lg font-bold text-white">₩{formatKRW(balance.available_cash)}</p>
        </div>
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <Wallet className="w-3.5 h-3.5 text-purple-400" />
            <p className="text-[11px] text-gray-500 font-medium">투자금액</p>
          </div>
          <p className="text-lg font-bold text-white">₩{formatKRW(balance.purchase_amount)}</p>
        </div>
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            {balance.eval_pnl >= 0 ? (
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-red-400" />
            )}
            <p className="text-[11px] text-gray-500 font-medium">평가손익</p>
          </div>
          <div className="flex items-center gap-2">
            <PnlDisplay value={balance.eval_pnl} size="lg" showIcon={false} showSign />
            {balance.eval_pnl_pct != null && (
              <span
                className={`text-xs ${
                  balance.eval_pnl_pct >= 0 ? 'text-emerald-500' : 'text-red-500'
                }`}
              >
                ({balance.eval_pnl_pct >= 0 ? '+' : ''}{balance.eval_pnl_pct.toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Investment ratio bar */}
      <div>
        <div className="flex items-center justify-between text-[11px] text-gray-500 mb-1.5">
          <span>투자 비율</span>
          <span>{investRatio.toFixed(1)}%</span>
        </div>
        <div className="h-2 bg-gray-700/40 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 bg-gradient-to-r from-indigo-500 to-purple-500"
            style={{ width: `${Math.min(investRatio, 100)}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-gray-600 mt-1">
          <span>예수금 ₩{formatKRW(balance.available_cash)}</span>
          <span>투자 ₩{formatKRW(balance.purchase_amount)}</span>
        </div>
      </div>
    </div>
  );
};

export default AccountBalanceCard;
