import React, { useEffect, useState, useCallback } from 'react';
import {
  ArrowLeftRight,
  TrendingUp,
  TrendingDown,
  Target,
  Trophy,
  XCircle,
  RefreshCw,
  Filter,
} from 'lucide-react';
import {
  fetchTrades,
  fetchTradeStats,
  type TradeItem,
  type TradeStats,
  type PaginatedResponse,
} from '../api/client';
import SessionBadge from '../components/SessionBadge';
import PnlDisplay from '../components/PnlDisplay';
import Pagination from '../components/Pagination';

const formatTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const formatKRW = (value: number) => `₩${value.toLocaleString('ko-KR')}`;

const Trades: React.FC = () => {
  const [tradesData, setTradesData] = useState<PaginatedResponse<TradeItem> | null>(null);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    action: '',
    session: '',
    exchange: '',
  });

  const loadTrades = useCallback(async (p: number) => {
    try {
      const res = await fetchTrades(p, 20);
      setTradesData(res.data);
    } catch (err) {
      console.error('Trades load error:', err);
    }
  }, []);

  useEffect(() => {
    Promise.all([
      loadTrades(1),
      fetchTradeStats().then((res) => setStats(res.data)),
    ]).finally(() => setLoading(false));
  }, [loadTrades]);

  const handlePage = (p: number) => {
    setPage(p);
    loadTrades(p);
  };

  const filteredItems = tradesData?.data.filter((t) => {
    if (filters.action && t.action !== filters.action) return false;
    if (filters.session && t.session !== filters.session) return false;
    if (filters.exchange && t.exchange !== filters.exchange) return false;
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  const statCards = stats
    ? [
        {
          label: '총 거래',
          value: stats.total_trades,
          suffix: '건',
          icon: ArrowLeftRight,
          color: 'text-blue-400',
          bg: 'from-blue-500/20 to-cyan-500/20',
        },
        {
          label: '승률',
          value: stats.win_rate ?? 0,
          suffix: '%',
          icon: Target,
          color: 'text-amber-400',
          bg: 'from-amber-500/20 to-orange-500/20',
          format: (v: number) => v.toFixed(1),
        },
        {
          label: '승리',
          value: stats.wins,
          suffix: '건',
          icon: Trophy,
          color: 'text-emerald-400',
          bg: 'from-emerald-500/20 to-teal-500/20',
        },
        {
          label: '패배',
          value: stats.losses,
          suffix: '건',
          icon: XCircle,
          color: 'text-red-400',
          bg: 'from-red-500/20 to-pink-500/20',
        },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">매매 내역</h1>
          <p className="text-sm text-gray-500 mt-1">전체 매매 기록 및 통계</p>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            showFilters ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          <Filter className="w-4 h-4" />
          필터
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map((card) => (
            <div key={card.label} className="card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-gray-500 font-medium">{card.label}</p>
                  <p className="text-xl font-bold text-white mt-1">
                    {card.format ? card.format(card.value) : card.value}
                    <span className="text-sm text-gray-400 ml-1">{card.suffix}</span>
                  </p>
                </div>
                <div className={`p-2 rounded-xl bg-gradient-to-br ${card.bg}`}>
                  <card.icon className={`w-4 h-4 ${card.color}`} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showFilters && (
        <div className="card flex flex-wrap items-center gap-3">
          <select
            value={filters.action}
            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm text-gray-200 outline-none focus:border-brand-500"
          >
            <option value="">전체 액션</option>
            <option value="BUY">매수</option>
            <option value="SELL">매도</option>
          </select>
          <select
            value={filters.session}
            onChange={(e) => setFilters({ ...filters, session: e.target.value })}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm text-gray-200 outline-none focus:border-brand-500"
          >
            <option value="">전체 세션</option>
            <option value="PRE_MARKET">프리마켓</option>
            <option value="REGULAR">정규장</option>
            <option value="AFTER_MARKET">애프터마켓</option>
          </select>
          <select
            value={filters.exchange}
            onChange={(e) => setFilters({ ...filters, exchange: e.target.value })}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm text-gray-200 outline-none focus:border-brand-500"
          >
            <option value="">전체 거래소</option>
            <option value="KRX">KRX</option>
            <option value="NXT">NXT</option>
            <option value="SOR">SOR</option>
          </select>
          <button
            onClick={() => setFilters({ action: '', session: '', exchange: '' })}
            className="px-3 py-1.5 text-xs text-gray-400 hover:text-white transition-colors"
          >
            초기화
          </button>
        </div>
      )}

      <div className="card overflow-hidden !p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700/50">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">시간</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">종목</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">액션</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">가격</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">수량</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">거래소</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">세션</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">손익</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">매도 사유</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {filteredItems?.map((trade) => (
                <tr key={trade.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                    {formatTime(trade.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className="text-white font-medium">{trade.stock_code}</span>
                      {trade.stock_name && (
                        <span className="text-gray-500 text-xs">{trade.stock_name}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border ${
                        trade.action === 'BUY'
                          ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                          : 'bg-red-500/15 border-red-500/30 text-red-400'
                      }`}
                    >
                      {trade.action === 'BUY' ? (
                        <TrendingUp className="w-3 h-3" />
                      ) : (
                        <TrendingDown className="w-3 h-3" />
                      )}
                      {trade.action === 'BUY' ? '매수' : '매도'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">
                    {formatKRW(trade.price)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">
                    {trade.quantity}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-xs text-gray-400 font-medium bg-gray-700/50 px-2 py-0.5 rounded">
                      {trade.exchange}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <SessionBadge session={trade.session} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {trade.pnl != null ? (
                      <PnlDisplay value={trade.pnl} size="sm" />
                    ) : (
                      <span className="text-gray-600 text-xs">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400 max-w-[120px] truncate">
                    {trade.sell_reason ?? '-'}
                  </td>
                </tr>
              ))}
              {(!filteredItems || filteredItems.length === 0) && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-gray-500">
                    <ArrowLeftRight className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    매매 기록이 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {tradesData && (
          <div className="px-4 py-3 border-t border-gray-700/50">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">전체 {tradesData.meta.total}건</span>
              <Pagination
                page={page}
                totalPages={tradesData.meta.total_pages}
                onPageChange={handlePage}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Trades;
