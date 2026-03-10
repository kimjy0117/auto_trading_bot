import React, { useEffect, useState, useCallback } from 'react';
import {
  Briefcase,
  History,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  AlertTriangle,
} from 'lucide-react';
import {
  fetchPositions,
  fetchPositionHistory,
  type PositionItem,
  type PositionsResponse,
  type PaginatedResponse,
} from '../api/client';
import SessionBadge from '../components/SessionBadge';
import PnlDisplay from '../components/PnlDisplay';
import Pagination from '../components/Pagination';
import AccountBalanceCard from '../components/AccountBalanceCard';

const formatTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatKRW = (value: number) => `₩${value.toLocaleString('ko-KR')}`;

const Positions: React.FC = () => {
  const [openData, setOpenData] = useState<PositionsResponse | null>(null);
  const [historyData, setHistoryData] = useState<PaginatedResponse<PositionItem> | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);

  const loadOpen = useCallback(async () => {
    try {
      const res = await fetchPositions();
      setOpenData(res.data);
    } catch (err) {
      console.error('Positions load error:', err);
    }
  }, []);

  const loadHistory = useCallback(async (page: number) => {
    try {
      const res = await fetchPositionHistory(page, 20);
      setHistoryData(res.data);
    } catch (err) {
      console.error('Position history load error:', err);
    }
  }, []);

  useEffect(() => {
    Promise.all([loadOpen(), loadHistory(1)]).finally(() => setLoading(false));
    const interval = setInterval(loadOpen, 30000);
    return () => clearInterval(interval);
  }, [loadOpen, loadHistory]);

  const handleHistoryPage = (p: number) => {
    setHistoryPage(p);
    loadHistory(p);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">포지션</h1>
          <p className="text-sm text-gray-500 mt-1">보유 중인 포지션 및 청산 내역</p>
        </div>
        <button
          onClick={() => { loadOpen(); loadHistory(historyPage); }}
          className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Account balance (compact) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AccountBalanceCard compact />

        {openData && openData.data.length > 0 && (
          <div className="card">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-3 rounded-xl bg-gradient-to-br ${openData.total_unrealized_pnl >= 0 ? 'from-emerald-500/20 to-teal-500/20' : 'from-red-500/20 to-pink-500/20'}`}>
                  {openData.total_unrealized_pnl >= 0 ? (
                    <TrendingUp className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <TrendingDown className="w-5 h-5 text-red-400" />
                  )}
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">총 미실현 손익</p>
                  <PnlDisplay value={openData.total_unrealized_pnl} size="lg" showIcon={false} />
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500">보유 종목</p>
                <p className="text-xl font-bold text-white">{openData.data.length}<span className="text-sm text-gray-400 ml-1">건</span></p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 탭 헤더 */}
      <div className="flex gap-1 bg-gray-800/40 p-1 rounded-xl w-fit">
        {[
          { label: '보유 중', icon: Briefcase, count: openData?.data.length ?? 0 },
          { label: '청산 내역', icon: History, count: historyData?.meta.total ?? 0 },
        ].map(({ label, icon: Icon, count }, idx) => (
          <button
            key={label}
            onClick={() => setActiveTab(idx)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 outline-none ${
              activeTab === idx
                ? 'bg-gray-700 text-white shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
            <span className="text-xs bg-gray-600/50 px-1.5 py-0.5 rounded-full">{count}</span>
          </button>
        ))}
      </div>

      {/* 탭 패널 */}
      {activeTab === 0 && (
        openData?.data.length === 0 ? (
          <div className="card text-center py-12">
            <Briefcase className="w-10 h-10 mx-auto mb-3 text-gray-600" />
            <p className="text-gray-500">보유 중인 포지션이 없습니다</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {openData?.data.map((pos) => (
              <PositionCard key={pos.id} position={pos} />
            ))}
          </div>
        )
      )}

      {activeTab === 1 && (
        <div className="card overflow-hidden !p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700/50">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">종목</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">수량</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">매수가</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">현재가</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">세션</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">기간</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {historyData?.data.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="text-white font-medium">{item.stock_code}</span>
                        {item.stock_name && (
                          <span className="text-gray-500 text-xs">{item.stock_name}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">{item.quantity}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">{formatKRW(item.avg_price)}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">{formatKRW(item.current_price)}</td>
                    <td className="px-4 py-3 text-center">
                      <SessionBadge session={item.session} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                      <div>{formatTime(item.opened_at)}</div>
                      {item.closed_at && (
                        <div className="text-gray-500">→ {formatTime(item.closed_at)}</div>
                      )}
                    </td>
                  </tr>
                ))}
                {(!historyData?.data || historyData.data.length === 0) && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-gray-500">
                      <History className="w-8 h-8 mx-auto mb-2 opacity-40" />
                      청산 내역이 없습니다
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {historyData && historyData.meta.total > 0 && (
            <div className="px-4 py-3 border-t border-gray-700/50">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">전체 {historyData.meta.total}건</span>
                <Pagination
                  page={historyPage}
                  totalPages={historyData.meta.total_pages}
                  onPageChange={handleHistoryPage}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const PositionCard: React.FC<{ position: PositionItem }> = ({ position: pos }) => {
  const pnlPct = pos.unrealized_pnl_pct ?? ((pos.current_price - pos.avg_price) / pos.avg_price * 100);
  const isProfit = pos.unrealized_pnl >= 0;

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">{pos.stock_code}</span>
          {pos.stock_name && <span className="text-sm text-gray-500">{pos.stock_name}</span>}
        </div>
        <SessionBadge session={pos.session} />
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <p className="text-xs text-gray-500">수량</p>
          <p className="text-sm font-semibold text-white">{pos.quantity}주</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">평균단가</p>
          <p className="text-sm font-semibold text-white font-mono">{formatKRW(pos.avg_price)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">현재가</p>
          <p className="text-sm font-semibold text-white font-mono">{formatKRW(pos.current_price)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">미실현 손익</p>
          <div className="flex items-center gap-1.5">
            <PnlDisplay value={pos.unrealized_pnl} size="sm" />
            <span className={`text-xs ${isProfit ? 'text-emerald-500' : 'text-red-500'}`}>
              ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
            </span>
          </div>
        </div>
      </div>

      {(pos.stop_loss_price != null || pos.trailing_stop_price != null) && (
        <div className="pt-3 border-t border-gray-700/30 flex items-center gap-4">
          {pos.stop_loss_price != null && (
            <div className="flex items-center gap-1.5 text-xs">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-gray-500">손절가</span>
              <span className="text-amber-400 font-mono font-medium">{formatKRW(pos.stop_loss_price)}</span>
            </div>
          )}
          {pos.trailing_stop_price != null && (
            <div className="flex items-center gap-1.5 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-gray-500">트레일링</span>
              <span className="text-orange-400 font-mono font-medium">{formatKRW(pos.trailing_stop_price)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Positions;
