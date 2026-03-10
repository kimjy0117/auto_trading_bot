import React, { useEffect, useState } from 'react';
import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import {
  LayoutDashboard,
  FileSearch,
  ArrowLeftRight,
  Briefcase,
  CalendarDays,
  Activity,
  Wifi,
  WifiOff,
  Bot,
} from 'lucide-react';
import { fetchHealth, type HealthResponse } from './api/client';
import SessionBadge from './components/SessionBadge';
import Dashboard from './pages/Dashboard';
import AnalysisLog from './pages/AnalysisLog';
import Trades from './pages/Trades';
import Positions from './pages/Positions';
import PnlCalendar from './pages/PnlCalendar';

const NAV_ITEMS = [
  { to: '/dashboard', label: '대시보드', icon: LayoutDashboard },
  { to: '/calendar', label: '손익 캘린더', icon: CalendarDays },
  { to: '/analysis', label: '분석 로그', icon: FileSearch },
  { to: '/trades', label: '매매 내역', icon: ArrowLeftRight },
  { to: '/positions', label: '포지션', icon: Briefcase },
];

const App: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetchHealth();
        setHealth(res.data);
        setConnected(true);
      } catch {
        setConnected(false);
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gray-900/80 backdrop-blur-xl border-r border-gray-800/60 flex flex-col">
        {/* Logo */}
        <div className="p-5 border-b border-gray-800/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center shadow-lg shadow-brand-500/25">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight">AI 자동매매</h1>
              <p className="text-[11px] text-gray-500 font-medium">Trading Dashboard</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-brand-600/15 text-brand-400 border border-brand-500/20 shadow-sm shadow-brand-500/10'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                }`
              }
            >
              <Icon className="w-[18px] h-[18px]" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Status */}
        <div className="p-4 border-t border-gray-800/60">
          <div className="flex items-center gap-2 text-xs">
            {connected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-400 font-medium">서버 연결됨</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-red-400" />
                <span className="text-red-400 font-medium">연결 끊김</span>
              </>
            )}
          </div>
          {health && (
            <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
              <Activity className="w-3 h-3" />
              <span>가동: {Math.floor(health.uptime_seconds / 3600)}시간 {Math.floor((health.uptime_seconds % 3600) / 60)}분</span>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 flex-shrink-0 bg-gray-900/50 backdrop-blur-xl border-b border-gray-800/60 flex items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-gray-300">한국 주식 AI 자동매매 시스템</h2>
          </div>
          <div className="flex items-center gap-4">
            {health && <SessionBadge session={health.current_session} size="md" />}
            {health?.is_trading_day && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                거래일
              </span>
            )}
            {health && !health.is_trading_day && (
              <span className="text-xs font-medium text-gray-500">비거래일</span>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-gray-950 p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/calendar" element={<PnlCalendar />} />
            <Route path="/analysis" element={<AnalysisLog />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/positions" element={<Positions />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export default App;
