import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      console.error(`API Error [${error.response.status}]:`, error.response.data);
    } else if (error.request) {
      console.error('Network Error: 서버에 연결할 수 없습니다.');
    }
    return Promise.reject(error);
  },
);

// ── Health ──────────────────────────────────────────────────────
export interface HealthResponse {
  status: string;
  current_session: string;
  is_trading_day: boolean;
  uptime_seconds: number;
  db_ok: boolean;
  redis_ok: boolean;
  timestamp: string;
}

// ── Dashboard ───────────────────────────────────────────────────
export interface SessionPnL {
  pre_market: number;
  regular: number;
  after_market: number;
}

export interface DashboardSummary {
  current_session: string;
  total_pnl: number;
  session_pnl: SessionPnL;
  open_positions: number;
  today_trades: number;
  win_rate: number | null;
}

export interface DailyPnl {
  trade_date: string;
  realized_pnl: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  pre_market_pnl: number;
  regular_pnl: number;
  after_market_pnl: number;
  max_drawdown: number | null;
}

// 백엔드: { days: number, data: DailyPnl[] }
export interface DailyPnlResponse {
  days: number;
  data: DailyPnl[];
}

export interface SessionPerformance {
  session: string;
  total_sells: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  total_pnl: number;
  avg_pnl: number | null;
  avg_return_pct: number | null;
}

// 백엔드: { data: SessionPerformance[] }
export interface SessionPerformanceResponse {
  data: SessionPerformance[];
}

// ── Pagination ──────────────────────────────────────────────────
// 백엔드: { meta: { page, size, total, total_pages }, data: T[] }
export interface PaginationMeta {
  page: number;
  size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedResponse<T> {
  meta: PaginationMeta;
  data: T[];
}

// ── Analysis ────────────────────────────────────────────────────
export interface NewsItem {
  id: number;
  stock_code: string | null;
  stock_name: string | null;
  source: string;
  channel: string | null;
  raw_text: string;
  tier1_impact: string | null;
  tier1_direction: string | null;
  tier1_summary: string | null;
  tier1_confidence: number | null;
  tier2_action: string | null;
  tier2_rationale: string | null;
  escalated: boolean;
  created_at: string;
}

export interface ScoreItem {
  id: number;
  stock_code: string;
  stock_name: string | null;
  session: string;
  nxt_eligible: boolean | null;
  ai_score: number;
  investor_flow_score: number;
  technical_score: number;
  volume_score: number;
  market_env_score: number;
  total_score: number;
  hard_filter_passed: boolean;
  decision: string | null;
  decision_reason: string | null;
  created_at: string;
}

// ── Trades ──────────────────────────────────────────────────────
export interface TradeItem {
  id: number;
  stock_code: string;
  stock_name: string | null;
  action: string;
  exchange: string;
  session: string;
  price: number;
  quantity: number;
  amount: number;
  fee: number;
  buy_price: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  sell_reason: string | null;
  order_id: string | null;
  created_at: string;
}

export interface BestWorstTrade {
  id: number;
  stock_code: string;
  stock_name: string | null;
  pnl: number;
  pnl_pct: number | null;
  created_at: string;
}

export interface TradeStats {
  total_trades: number;
  total_sells: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  total_pnl: number;
  avg_pnl: number | null;
  best_trade: BestWorstTrade | null;
  worst_trade: BestWorstTrade | null;
  by_session: Array<{
    session: string;
    trades: number;
    wins: number;
    losses: number;
    pnl: number;
  }>;
}

// ── Positions ───────────────────────────────────────────────────
export interface PositionItem {
  id: number;
  stock_code: string;
  stock_name: string | null;
  exchange: string;
  session: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  atr_value: number | null;
  stop_loss_price: number | null;
  trailing_stop_price: number | null;
  highest_price: number | null;
  status: string;
  opened_at: string;
  closed_at: string | null;
}

// 백엔드: { total, total_unrealized_pnl, data: PositionItem[] }
export interface PositionsResponse {
  total: number;
  total_unrealized_pnl: number;
  data: PositionItem[];
}

// ── Account ──────────────────────────────────────────────────────
export interface AccountBalance {
  available_cash: number;
  total_evaluation: number;
  purchase_amount: number;
  eval_amount: number;
  eval_pnl: number;
  eval_pnl_pct: number | null;
  net_asset: number;
}

// ── Monthly PnL ──────────────────────────────────────────────────
export interface MonthlyPnl {
  year: number;
  month: number;
  realized_pnl: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  trading_days: number;
}

export interface MonthlyPnlResponse {
  year: number;
  data: MonthlyPnl[];
}

// ── API 함수 ────────────────────────────────────────────────────
export const fetchHealth = () => api.get<HealthResponse>('/health');
export const fetchDashboardSummary = () => api.get<DashboardSummary>('/dashboard/summary');
export const fetchDailyPnl = (days = 30) => api.get<DailyPnlResponse>(`/dashboard/daily-pnl?days=${days}`);
export const fetchMonthlyPnl = (year?: number) => api.get<MonthlyPnlResponse>(`/dashboard/monthly-pnl${year ? `?year=${year}` : ''}`);
export const fetchSessionPerformance = () => api.get<SessionPerformanceResponse>('/dashboard/session-performance');
export const fetchAccountBalance = () => api.get<AccountBalance>('/account/balance');
export const fetchNews = (page = 1, size = 20) => api.get<PaginatedResponse<NewsItem>>(`/analysis/news?page=${page}&size=${size}`);
export const fetchScores = (page = 1, size = 20) => api.get<PaginatedResponse<ScoreItem>>(`/analysis/scores?page=${page}&size=${size}`);
export const fetchTrades = (page = 1, size = 20) => api.get<PaginatedResponse<TradeItem>>(`/trades/?page=${page}&size=${size}`);
export const fetchTradeStats = () => api.get<TradeStats>('/trades/stats');
export const fetchPositions = () => api.get<PositionsResponse>('/positions/');
export const fetchPositionHistory = (page = 1, size = 20) => api.get<PaginatedResponse<PositionItem>>(`/positions/history?page=${page}&size=${size}`);

export default api;
