import React, { useEffect, useState } from 'react';
import { Newspaper, BarChart3, RefreshCw } from 'lucide-react';
import {
  fetchNews,
  fetchScores,
  type NewsItem,
  type ScoreItem,
  type PaginatedResponse,
} from '../api/client';
import SessionBadge from '../components/SessionBadge';
import Pagination from '../components/Pagination';

const IMPACT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  HIGH: { bg: 'bg-red-500/15 border-red-500/30', text: 'text-red-400', label: '높음' },
  MEDIUM: { bg: 'bg-yellow-500/15 border-yellow-500/30', text: 'text-yellow-400', label: '보통' },
  LOW: { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-400', label: '낮음' },
  NONE: { bg: 'bg-gray-500/15 border-gray-500/30', text: 'text-gray-500', label: '없음' },
};

const DECISION_STYLES: Record<string, { bg: string; text: string }> = {
  BUY: { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-400' },
  SKIP: { bg: 'bg-gray-500/15 border-gray-500/30', text: 'text-gray-500' },
  WATCH: { bg: 'bg-yellow-500/15 border-yellow-500/30', text: 'text-yellow-400' },
};

const formatTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const AnalysisLog: React.FC = () => {
  const [newsData, setNewsData] = useState<PaginatedResponse<NewsItem> | null>(null);
  const [scoresData, setScoresData] = useState<PaginatedResponse<ScoreItem> | null>(null);
  const [newsPage, setNewsPage] = useState(1);
  const [scoresPage, setScoresPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);

  const loadNews = async (page: number) => {
    try {
      const res = await fetchNews(page, 20);
      setNewsData(res.data);
    } catch (err) {
      console.error('News load error:', err);
    }
  };

  const loadScores = async (page: number) => {
    try {
      const res = await fetchScores(page, 20);
      setScoresData(res.data);
    } catch (err) {
      console.error('Scores load error:', err);
    }
  };

  useEffect(() => {
    Promise.all([loadNews(1), loadScores(1)]).finally(() => setLoading(false));
  }, []);

  const handleNewsPage = (page: number) => {
    setNewsPage(page);
    loadNews(page);
  };

  const handleScoresPage = (page: number) => {
    setScoresPage(page);
    loadScores(page);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  const TABS = [
    { label: '뉴스 분석', icon: Newspaper },
    { label: '시그널 스코어', icon: BarChart3 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">분석 로그</h1>
        <p className="text-sm text-gray-500 mt-1">AI 뉴스 분석 및 시그널 스코어 기록</p>
      </div>

      <div className="flex gap-1 bg-gray-800/40 p-1 rounded-xl w-fit">
        {TABS.map(({ label, icon: Icon }, idx) => (
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
          </button>
        ))}
      </div>

      <div>
        {activeTab === 0 && (
            <div className="card overflow-hidden !p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700/50">
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">시간</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">소스</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">종목</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">요약</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">영향도</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">방향</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Tier2</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/50">
                    {newsData?.data.map((item) => {
                      const impact = IMPACT_STYLES[item.tier1_impact ?? 'NONE'] ?? IMPACT_STYLES.NONE;
                      return (
                        <tr key={item.id} className="hover:bg-gray-800/30 transition-colors">
                          <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                            {formatTime(item.created_at)}
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-gray-300 text-xs font-medium">{item.source}</span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              <span className="text-white font-medium">{item.stock_code ?? '-'}</span>
                              {item.stock_name && (
                                <span className="text-gray-500 text-xs">{item.stock_name}</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 max-w-xs">
                            <p className="text-gray-300 text-xs truncate">{item.tier1_summary ?? '-'}</p>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${impact.bg} ${impact.text}`}>
                              {impact.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`text-xs font-medium ${item.tier1_direction === 'POSITIVE' ? 'text-emerald-400' : item.tier1_direction === 'NEGATIVE' ? 'text-red-400' : 'text-gray-400'}`}>
                              {item.tier1_direction === 'POSITIVE' ? '▲ 호재' : item.tier1_direction === 'NEGATIVE' ? '▼ 악재' : '- 중립'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className="text-xs text-gray-400">{item.tier2_action ?? '-'}</span>
                          </td>
                        </tr>
                      );
                    })}
                    {(!newsData?.data || newsData.data.length === 0) && (
                      <tr>
                        <td colSpan={7} className="px-4 py-12 text-center text-gray-500">
                          <Newspaper className="w-8 h-8 mx-auto mb-2 opacity-40" />
                          분석된 뉴스가 없습니다
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {newsData && (
                <div className="px-4 py-3 border-t border-gray-700/50">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-500">전체 {newsData.meta.total}건</span>
                    <Pagination
                      page={newsPage}
                      totalPages={newsData.meta.total_pages}
                      onPageChange={handleNewsPage}
                    />
                  </div>
                </div>
              )}
            </div>
        )}
        {activeTab === 1 && (
            <div className="card overflow-hidden !p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700/50">
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">시간</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">종목</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">세션</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">스코어 구성</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">종합 점수</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">판단</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/50">
                    {scoresData?.data.map((item) => {
                      const decision = DECISION_STYLES[item.decision ?? 'WATCH'] ?? DECISION_STYLES.WATCH;
                      const scoreColor =
                        item.total_score >= 70
                          ? 'bg-emerald-500'
                          : item.total_score >= 40
                            ? 'bg-yellow-500'
                            : 'bg-red-500';
                      return (
                        <tr key={item.id} className="hover:bg-gray-800/30 transition-colors">
                          <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                            {formatTime(item.created_at)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              <span className="text-white font-medium">{item.stock_code}</span>
                              {item.stock_name && (
                                <span className="text-gray-500 text-xs">{item.stock_name}</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <SessionBadge session={item.session} />
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3 text-xs">
                              <span className="text-gray-400">
                                AI <span className="text-gray-300 font-medium">{item.ai_score.toFixed(0)}</span>
                              </span>
                              <span className="text-gray-400">
                                기술 <span className="text-gray-300 font-medium">{item.technical_score.toFixed(0)}</span>
                              </span>
                              <span className="text-gray-400">
                                거래량 <span className="text-gray-300 font-medium">{item.volume_score.toFixed(0)}</span>
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-center gap-2">
                              <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${scoreColor} transition-all duration-300`}
                                  style={{ width: `${Math.min(item.total_score, 100)}%` }}
                                />
                              </div>
                              <span className="text-xs text-gray-300 font-medium w-8 text-right">
                                {item.total_score.toFixed(0)}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${decision.bg} ${decision.text}`}>
                              {item.decision ?? '-'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                    {(!scoresData?.data || scoresData.data.length === 0) && (
                      <tr>
                        <td colSpan={6} className="px-4 py-12 text-center text-gray-500">
                          <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-40" />
                          스코어 데이터가 없습니다
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {scoresData && (
                <div className="px-4 py-3 border-t border-gray-700/50">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-500">전체 {scoresData.meta.total}건</span>
                    <Pagination
                      page={scoresPage}
                      totalPages={scoresData.meta.total_pages}
                      onPageChange={handleScoresPage}
                    />
                  </div>
                </div>
              )}
            </div>
        )}
      </div>
    </div>
  );
};

export default AnalysisLog;
