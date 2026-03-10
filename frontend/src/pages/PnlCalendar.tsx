import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  CalendarRange,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Trophy,
  BarChart3,
} from 'lucide-react';
import {
  fetchDailyPnl,
  fetchMonthlyPnl,
  type DailyPnl,
  type DailyPnlResponse,
  type MonthlyPnl,
  type MonthlyPnlResponse,
} from '../api/client';
import PnlDisplay from '../components/PnlDisplay';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const MONTH_NAMES = [
  '1월', '2월', '3월', '4월', '5월', '6월',
  '7월', '8월', '9월', '10월', '11월', '12월',
];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function getFirstDayOfWeek(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay();
}

function dateKey(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function getPnlBg(pnl: number, maxAbs: number): string {
  if (pnl === 0) return 'bg-gray-800/40';
  const ratio = Math.min(Math.abs(pnl) / (maxAbs || 1), 1);
  const alpha = 0.15 + ratio * 0.65;
  if (pnl > 0) return `rgba(34,197,94,${alpha.toFixed(2)})`;
  return `rgba(239,68,68,${alpha.toFixed(2)})`;
}

function formatCompact(value: number): string {
  const abs = Math.abs(value);
  const sign = value >= 0 ? '+' : '-';
  if (abs >= 1_000_000) return `${sign}${(abs / 10_000).toFixed(0)}만`;
  if (abs >= 10_000) return `${sign}${(abs / 10_000).toFixed(1)}만`;
  if (abs > 0) return `${sign}${(abs / 1_000).toFixed(0)}천`;
  return '0';
}

const PnlCalendar: React.FC = () => {
  const now = new Date();
  const [viewMode, setViewMode] = useState<'daily' | 'monthly'>('daily');
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [dailyData, setDailyData] = useState<DailyPnl[]>([]);
  const [monthlyData, setMonthlyData] = useState<MonthlyPnl[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<DailyPnl | null>(null);

  const loadDailyData = useCallback(async () => {
    try {
      const res = await fetchDailyPnl(365);
      setDailyData((res.data as DailyPnlResponse).data ?? []);
    } catch (err) {
      console.error('Daily PnL load error:', err);
    }
  }, []);

  const loadMonthlyData = useCallback(async (y: number) => {
    try {
      const res = await fetchMonthlyPnl(y);
      setMonthlyData((res.data as MonthlyPnlResponse).data ?? []);
    } catch (err) {
      console.error('Monthly PnL load error:', err);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadDailyData(), loadMonthlyData(year)]).finally(() =>
      setLoading(false),
    );
  }, [loadDailyData, loadMonthlyData, year]);

  const dailyMap = useMemo(() => {
    const map: Record<string, DailyPnl> = {};
    for (const d of dailyData) {
      map[d.trade_date] = d;
    }
    return map;
  }, [dailyData]);

  const monthlyMap = useMemo(() => {
    const map: Record<number, MonthlyPnl> = {};
    for (const m of monthlyData) {
      map[m.month] = m;
    }
    return map;
  }, [monthlyData]);

  const currentMonthDays = useMemo(() => {
    const daysInMonth = getDaysInMonth(year, month);
    const firstDay = getFirstDayOfWeek(year, month);
    const days: Array<{ day: number; pnl: DailyPnl | null }> = [];

    for (let i = 0; i < firstDay; i++) {
      days.push({ day: 0, pnl: null });
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const key = dateKey(year, month, d);
      days.push({ day: d, pnl: dailyMap[key] ?? null });
    }
    return days;
  }, [year, month, dailyMap]);

  const monthStats = useMemo(() => {
    const items = currentMonthDays.filter((d) => d.pnl);
    const totalPnl = items.reduce((s, d) => s + (d.pnl?.realized_pnl ?? 0), 0);
    const totalTrades = items.reduce((s, d) => s + (d.pnl?.total_trades ?? 0), 0);
    const wins = items.reduce((s, d) => s + (d.pnl?.wins ?? 0), 0);
    const losses = items.reduce((s, d) => s + (d.pnl?.losses ?? 0), 0);
    const sellCount = wins + losses;
    const winRate = sellCount > 0 ? (wins / sellCount) * 100 : null;
    const maxAbs = Math.max(
      ...items.map((d) => Math.abs(d.pnl?.realized_pnl ?? 0)),
      1,
    );
    return { totalPnl, totalTrades, wins, losses, winRate, tradingDays: items.length, maxAbs };
  }, [currentMonthDays]);

  const yearStats = useMemo(() => {
    const totalPnl = monthlyData.reduce((s, m) => s + m.realized_pnl, 0);
    const totalTrades = monthlyData.reduce((s, m) => s + m.total_trades, 0);
    const wins = monthlyData.reduce((s, m) => s + m.wins, 0);
    const losses = monthlyData.reduce((s, m) => s + m.losses, 0);
    const sellCount = wins + losses;
    const winRate = sellCount > 0 ? (wins / sellCount) * 100 : null;
    const maxAbs = Math.max(
      ...monthlyData.map((m) => Math.abs(m.realized_pnl)),
      1,
    );
    return { totalPnl, totalTrades, wins, losses, winRate, maxAbs };
  }, [monthlyData]);

  const prevMonth = () => {
    if (month === 1) {
      setMonth(12);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
    setSelectedDay(null);
  };

  const nextMonth = () => {
    if (month === 12) {
      setMonth(1);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
    setSelectedDay(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-brand-400 animate-spin" />
          <p className="text-gray-400 text-sm">데이터 로딩 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">손익 캘린더</h1>
          <p className="text-sm text-gray-500 mt-1">일별 / 월별 투자 수익을 한눈에</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 bg-gray-800/40 p-1 rounded-xl">
            <button
              onClick={() => setViewMode('daily')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'daily'
                  ? 'bg-gray-700 text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <CalendarDays className="w-4 h-4" />
              일별
            </button>
            <button
              onClick={() => setViewMode('monthly')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'monthly'
                  ? 'bg-gray-700 text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <CalendarRange className="w-4 h-4" />
              월별
            </button>
          </div>
        </div>
      </div>

      {viewMode === 'daily' ? (
        <>
          {/* Month navigation */}
          <div className="flex items-center justify-between">
            <button
              onClick={prevMonth}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <h2 className="text-lg font-bold text-white">
              {year}년 {month}월
            </h2>
            <button
              onClick={nextMonth}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Monthly summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard
              label="이번 달 손익"
              value={<PnlDisplay value={monthStats.totalPnl} size="lg" showIcon />}
              icon={monthStats.totalPnl >= 0 ? TrendingUp : TrendingDown}
              iconColor={monthStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
              iconBg={monthStats.totalPnl >= 0 ? 'from-emerald-500/20 to-teal-500/20' : 'from-red-500/20 to-pink-500/20'}
            />
            <SummaryCard
              label="거래일"
              value={<span className="text-xl font-bold text-white">{monthStats.tradingDays}일</span>}
              icon={CalendarDays}
              iconColor="text-blue-400"
              iconBg="from-blue-500/20 to-cyan-500/20"
            />
            <SummaryCard
              label="총 거래"
              value={<span className="text-xl font-bold text-white">{monthStats.totalTrades}건</span>}
              icon={BarChart3}
              iconColor="text-purple-400"
              iconBg="from-purple-500/20 to-violet-500/20"
            />
            <SummaryCard
              label="승률"
              value={
                <span className="text-xl font-bold text-white">
                  {monthStats.winRate != null ? `${monthStats.winRate.toFixed(1)}%` : '-'}
                </span>
              }
              icon={Trophy}
              iconColor="text-amber-400"
              iconBg="from-amber-500/20 to-orange-500/20"
            />
          </div>

          {/* Calendar grid */}
          <div className="card">
            {/* Weekday headers */}
            <div className="grid grid-cols-7 gap-1 mb-2">
              {WEEKDAYS.map((w, i) => (
                <div
                  key={w}
                  className={`text-center text-xs font-semibold py-1 ${
                    i === 0 ? 'text-red-400' : i === 6 ? 'text-blue-400' : 'text-gray-500'
                  }`}
                >
                  {w}
                </div>
              ))}
            </div>

            {/* Day cells */}
            <div className="grid grid-cols-7 gap-1">
              {currentMonthDays.map((cell, idx) => {
                if (cell.day === 0) {
                  return <div key={`empty-${idx}`} className="aspect-square" />;
                }

                const pnl = cell.pnl?.realized_pnl ?? 0;
                const hasTrade = cell.pnl != null;
                const bgColor = hasTrade ? getPnlBg(pnl, monthStats.maxAbs) : undefined;
                const isSelected =
                  selectedDay?.trade_date === dateKey(year, month, cell.day);
                const dayOfWeek = (getFirstDayOfWeek(year, month) + cell.day - 1) % 7;

                return (
                  <button
                    key={cell.day}
                    onClick={() => setSelectedDay(cell.pnl)}
                    className={`
                      aspect-square rounded-lg p-1 flex flex-col items-center justify-center
                      transition-all duration-150 relative
                      ${hasTrade ? 'cursor-pointer hover:ring-2 hover:ring-brand-400/60' : 'cursor-default'}
                      ${isSelected ? 'ring-2 ring-brand-400' : ''}
                      ${!hasTrade ? 'bg-gray-800/20' : ''}
                    `}
                    style={hasTrade ? { backgroundColor: bgColor } : undefined}
                  >
                    <span
                      className={`text-xs leading-none ${
                        dayOfWeek === 0
                          ? 'text-red-400/70'
                          : dayOfWeek === 6
                            ? 'text-blue-400/70'
                            : 'text-gray-500'
                      }`}
                    >
                      {cell.day}
                    </span>
                    {hasTrade && (
                      <span
                        className={`text-[10px] font-bold mt-0.5 leading-none ${
                          pnl > 0 ? 'text-emerald-300' : pnl < 0 ? 'text-red-300' : 'text-gray-400'
                        }`}
                      >
                        {formatCompact(pnl)}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Color legend */}
            <div className="flex items-center justify-center gap-4 mt-4 pt-3 border-t border-gray-700/30">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(239,68,68,0.6)' }} />
                <span className="text-[11px] text-gray-500">손실</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm bg-gray-800/40" />
                <span className="text-[11px] text-gray-500">거래없음</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(34,197,94,0.6)' }} />
                <span className="text-[11px] text-gray-500">수익</span>
              </div>
            </div>
          </div>

          {/* Selected day detail */}
          {selectedDay && (
            <div className="card animate-in fade-in slide-in-from-bottom-2">
              <h3 className="text-sm font-semibold text-gray-300 mb-3">
                {selectedDay.trade_date} 상세
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-gray-500">실현 손익</p>
                  <PnlDisplay value={selectedDay.realized_pnl} size="md" showIcon />
                </div>
                <div>
                  <p className="text-xs text-gray-500">거래 수</p>
                  <p className="text-base font-bold text-white">{selectedDay.total_trades}건</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">승/패</p>
                  <p className="text-base font-bold text-white">
                    <span className="text-emerald-400">{selectedDay.wins}</span>
                    <span className="text-gray-500"> / </span>
                    <span className="text-red-400">{selectedDay.losses}</span>
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">승률</p>
                  <p className="text-base font-bold text-white">
                    {selectedDay.win_rate != null ? `${selectedDay.win_rate.toFixed(1)}%` : '-'}
                  </p>
                </div>
              </div>
              {/* Session breakdown */}
              <div className="mt-3 pt-3 border-t border-gray-700/30 grid grid-cols-3 gap-3">
                <div>
                  <p className="text-[11px] text-gray-500">프리마켓</p>
                  <PnlDisplay value={selectedDay.pre_market_pnl} size="sm" showSign />
                </div>
                <div>
                  <p className="text-[11px] text-gray-500">정규장</p>
                  <PnlDisplay value={selectedDay.regular_pnl} size="sm" showSign />
                </div>
                <div>
                  <p className="text-[11px] text-gray-500">애프터마켓</p>
                  <PnlDisplay value={selectedDay.after_market_pnl} size="sm" showSign />
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        /* ── Monthly View ── */
        <>
          {/* Year navigation */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => setYear((y) => y - 1)}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <h2 className="text-lg font-bold text-white">{year}년</h2>
            <button
              onClick={() => setYear((y) => y + 1)}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Year summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard
              label="연간 손익"
              value={<PnlDisplay value={yearStats.totalPnl} size="lg" showIcon />}
              icon={yearStats.totalPnl >= 0 ? TrendingUp : TrendingDown}
              iconColor={yearStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
              iconBg={yearStats.totalPnl >= 0 ? 'from-emerald-500/20 to-teal-500/20' : 'from-red-500/20 to-pink-500/20'}
            />
            <SummaryCard
              label="총 거래"
              value={<span className="text-xl font-bold text-white">{yearStats.totalTrades}건</span>}
              icon={BarChart3}
              iconColor="text-blue-400"
              iconBg="from-blue-500/20 to-cyan-500/20"
            />
            <SummaryCard
              label="승/패"
              value={
                <span className="text-xl font-bold text-white">
                  <span className="text-emerald-400">{yearStats.wins}</span>
                  <span className="text-gray-500"> / </span>
                  <span className="text-red-400">{yearStats.losses}</span>
                </span>
              }
              icon={Trophy}
              iconColor="text-purple-400"
              iconBg="from-purple-500/20 to-violet-500/20"
            />
            <SummaryCard
              label="승률"
              value={
                <span className="text-xl font-bold text-white">
                  {yearStats.winRate != null ? `${yearStats.winRate.toFixed(1)}%` : '-'}
                </span>
              }
              icon={Trophy}
              iconColor="text-amber-400"
              iconBg="from-amber-500/20 to-orange-500/20"
            />
          </div>

          {/* Monthly grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
              const data = monthlyMap[m];
              const pnl = data?.realized_pnl ?? 0;
              const hasTrade = data != null;
              const bgColor = hasTrade ? getPnlBg(pnl, yearStats.maxAbs) : undefined;

              return (
                <button
                  key={m}
                  onClick={() => {
                    setMonth(m);
                    setViewMode('daily');
                    setSelectedDay(null);
                  }}
                  className={`
                    card !p-4 text-left transition-all duration-200
                    hover:ring-2 hover:ring-brand-400/50 cursor-pointer
                    ${!hasTrade ? 'opacity-50' : ''}
                  `}
                  style={hasTrade ? { backgroundColor: bgColor } : undefined}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-gray-300">{MONTH_NAMES[m - 1]}</span>
                    {hasTrade && (
                      <span className="text-[10px] text-gray-500">{data.trading_days}일</span>
                    )}
                  </div>
                  {hasTrade ? (
                    <>
                      <PnlDisplay value={pnl} size="md" showIcon showSign />
                      <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-400">
                        <span>{data.total_trades}건</span>
                        <span className="text-gray-600">|</span>
                        <span>
                          {data.win_rate != null ? `${data.win_rate.toFixed(0)}%` : '-'}
                        </span>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-gray-600 mt-1">거래 없음</p>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

const SummaryCard: React.FC<{
  label: string;
  value: React.ReactNode;
  icon: React.FC<{ className?: string }>;
  iconColor: string;
  iconBg: string;
}> = ({ label, value, icon: Icon, iconColor, iconBg }) => (
  <div className="card">
    <div className="flex items-start justify-between">
      <div className="space-y-1.5">
        <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">{label}</p>
        {value}
      </div>
      <div className={`p-2 rounded-xl bg-gradient-to-br ${iconBg}`}>
        <Icon className={`w-4 h-4 ${iconColor}`} />
      </div>
    </div>
  </div>
);

export default PnlCalendar;
