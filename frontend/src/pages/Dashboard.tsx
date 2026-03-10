import React, { useEffect, useState, useCallback } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  TrendingUp,
  ArrowLeftRight,
  Briefcase,
  Target,
  RefreshCw,
  Sun,
  Sunrise,
  Moon,
} from 'lucide-react';
import {
  fetchDashboardSummary,
  fetchDailyPnl,
  fetchSessionPerformance,
  type DashboardSummary,
  type DailyPnl,
  type SessionPerformance,
  type DailyPnlResponse,
  type SessionPerformanceResponse,
} from '../api/client';
import SessionBadge from '../components/SessionBadge';
import PnlDisplay from '../components/PnlDisplay';
import AccountBalanceCard from '../components/AccountBalanceCard';

const SESSION_COLORS: Record<string, string> = {
  PRE_MARKET: '#a78bfa',
  REGULAR: '#60a5fa',
  AFTER_MARKET: '#fb923c',
};

const SESSION_LABELS: Record<string, string> = {
  PRE_MARKET: '프리마켓',
  REGULAR: '정규장',
  AFTER_MARKET: '애프터마켓',
};

const SESSION_ICONS: Record<string, React.ReactNode> = {
  PRE_MARKET: <Sunrise className="w-4 h-4 text-purple-400" />,
  REGULAR: <Sun className="w-4 h-4 text-blue-400" />,
  AFTER_MARKET: <Moon className="w-4 h-4 text-orange-400" />,
};

const Dashboard: React.FC = () => {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [dailyPnl, setDailyPnl] = useState<DailyPnl[]>([]);
  const [sessionPerf, setSessionPerf] = useState<SessionPerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const loadData = useCallback(async () => {
    try {
      const [summaryRes, dailyRes, sessionRes] = await Promise.all([
        fetchDashboardSummary(),
        fetchDailyPnl(30),
        fetchSessionPerformance(),
      ]);
      setSummary(summaryRes.data);
      setDailyPnl((dailyRes.data as DailyPnlResponse).data ?? []);
      setSessionPerf((sessionRes.data as SessionPerformanceResponse).data ?? []);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

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

  const summaryCards = [
    {
      label: '총 손익',
      value: summary?.total_pnl ?? 0,
      icon: TrendingUp,
      iconBg: 'from-emerald-500/20 to-teal-500/20',
      iconColor: 'text-emerald-400',
      isPnl: true,
    },
    {
      label: '오늘 거래',
      value: summary?.today_trades ?? 0,
      icon: ArrowLeftRight,
      iconBg: 'from-blue-500/20 to-cyan-500/20',
      iconColor: 'text-blue-400',
      isPnl: false,
    },
    {
      label: '오픈 포지션',
      value: summary?.open_positions ?? 0,
      icon: Briefcase,
      iconBg: 'from-purple-500/20 to-violet-500/20',
      iconColor: 'text-purple-400',
      isPnl: false,
    },
    {
      label: '승률',
      value: summary?.win_rate ?? 0,
      icon: Target,
      iconBg: 'from-amber-500/20 to-orange-500/20',
      iconColor: 'text-amber-400',
      isPnl: false,
      isPercent: true,
    },
  ];

  const sessionPnlData = [
    { session: 'PRE_MARKET', pnl: summary?.session_pnl?.pre_market ?? 0 },
    { session: 'REGULAR', pnl: summary?.session_pnl?.regular ?? 0 },
    { session: 'AFTER_MARKET', pnl: summary?.session_pnl?.after_market ?? 0 },
  ];

  const maxSessionPnl = Math.max(...sessionPnlData.map((d) => Math.abs(d.pnl)), 1);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">대시보드</h1>
          <p className="text-sm text-gray-500 mt-1">
            마지막 갱신: {lastRefresh.toLocaleTimeString('ko-KR')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {summary && <SessionBadge session={summary.current_session} size="lg" />}
          <button
            onClick={loadData}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Account Balance */}
      <AccountBalanceCard />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((card) => (
          <div key={card.label} className="card group">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{card.label}</p>
                {card.isPnl ? (
                  <PnlDisplay value={card.value} size="lg" showIcon />
                ) : card.isPercent ? (
                  <p className="text-2xl font-bold text-white">{card.value.toFixed(1)}%</p>
                ) : (
                  <p className="text-2xl font-bold text-white">{card.value}</p>
                )}
              </div>
              <div className={`p-2.5 rounded-xl bg-gradient-to-br ${card.iconBg}`}>
                <card.icon className={`w-5 h-5 ${card.iconColor}`} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Session PnL Breakdown */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">세션별 손익</h3>
        <div className="space-y-3">
          {sessionPnlData.map((item) => {
            const pct = maxSessionPnl > 0 ? (Math.abs(item.pnl) / maxSessionPnl) * 100 : 0;
            const isPositive = item.pnl >= 0;
            return (
              <div key={item.session} className="flex items-center gap-3">
                <div className="flex items-center gap-2 w-28 flex-shrink-0">
                  {SESSION_ICONS[item.session]}
                  <span className="text-sm text-gray-400">{SESSION_LABELS[item.session]}</span>
                </div>
                <div className="flex-1 h-6 bg-gray-700/40 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{
                      width: `${Math.max(pct, 2)}%`,
                      backgroundColor: isPositive
                        ? SESSION_COLORS[item.session]
                        : '#ef4444',
                      opacity: 0.7,
                    }}
                  />
                </div>
                <div className="w-32 text-right flex-shrink-0">
                  <PnlDisplay value={item.pnl} size="sm" showSign />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily PnL Chart */}
        <div className="card lg:col-span-2">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">일별 손익 (최근 30일)</h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dailyPnl} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <defs>
                  <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="50%" stopColor="#6366f1" stopOpacity={0.1} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="trade_date"
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  tickFormatter={(v: string) => {
                    const d = new Date(v);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                  }}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  tickFormatter={(v: number) =>
                    Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(0)}만` : v.toString()
                  }
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#e5e7eb',
                  }}
                  formatter={(value: number) => [`₩${value.toLocaleString('ko-KR')}`, '손익']}
                  labelFormatter={(label: string) => `날짜: ${label}`}
                />
                <Area
                  type="monotone"
                  dataKey="realized_pnl"
                  stroke="#6366f1"
                  strokeWidth={2}
                  fill="url(#pnlGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: '#818cf8', stroke: '#6366f1', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Session Performance */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">세션별 성과</h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={sessionPerf.map((s) => ({
                  ...s,
                  name: SESSION_LABELS[s.session] ?? s.session,
                }))}
                margin={{ top: 5, right: 5, left: -10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#e5e7eb',
                  }}
                  formatter={(value: number) => [`${value.toFixed(1)}%`, '승률']}
                />
                <Bar dataKey="win_rate" radius={[6, 6, 0, 0]} maxBarSize={48}>
                  {sessionPerf.map((entry) => (
                    <Cell
                      key={entry.session}
                      fill={SESSION_COLORS[entry.session] ?? '#6b7280'}
                      fillOpacity={0.8}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Legend */}
          <div className="mt-3 space-y-2">
            {sessionPerf.map((s) => (
              <div key={s.session} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <SessionBadge session={s.session} size="sm" showDot={false} />
                </div>
                <span className="text-gray-400">
                  {s.wins}승 {s.losses}패 · {s.total_sells}건
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
