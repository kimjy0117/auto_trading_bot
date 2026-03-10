-- ============================================================
-- AI 자동매매 시스템 — 전체 테이블 생성 스크립트 (MySQL 8.0)
-- 실행: mysql -u autotrading -p autotrading < scripts/create_tables.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS autotrading
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE autotrading;

-- ────────────────────────────────────────────────────────────
-- 1. news_analysis — AI 뉴스/공시 분석 결과 (Tier1 + Tier2)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_analysis (
    id               INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    stock_code       VARCHAR(20)   NULL                    COMMENT '종목코드 6자리 (미식별 시 NULL)',
    stock_name       VARCHAR(100)  NULL                    COMMENT '종목명',
    source           ENUM('TELEGRAM','DART','MANUAL') NOT NULL COMMENT '뉴스 출처 (텔레그램/DART공시/수동입력)',
    channel          VARCHAR(100)  NULL                    COMMENT '텔레그램 채널명',
    raw_text         TEXT          NOT NULL                COMMENT '원본 뉴스/공시 전문',

    -- Tier 1: GPT-4o mini 빠른 스크리닝
    tier1_impact     ENUM('HIGH','MEDIUM','LOW','NONE') NULL COMMENT 'Tier1 주가 영향도 (HIGH=에스컬레이션 대상)',
    tier1_direction  ENUM('POSITIVE','NEGATIVE','NEUTRAL') NULL COMMENT 'Tier1 방향성 (호재/악재/중립)',
    tier1_summary    TEXT          NULL                    COMMENT 'Tier1 한국어 1~2문장 요약',
    tier1_confidence FLOAT         NULL                    COMMENT 'Tier1 판단 확신도 (0.0~1.0)',
    tier1_model      VARCHAR(50)   NULL                    COMMENT 'Tier1 사용 모델명 (gpt-4o-mini)',
    tier1_tokens     INT           NULL                    COMMENT 'Tier1 소비 토큰 수',

    -- Tier 2: GPT-4o 정밀 분석 (impact=HIGH/MEDIUM인 경우에만 실행)
    tier2_action          ENUM('STRONG_BUY','BUY','HOLD','SELL','STRONG_SELL') NULL COMMENT 'Tier2 매매 액션 권고',
    tier2_rationale       TEXT          NULL               COMMENT 'Tier2 판단 근거 (2~3문장)',
    tier2_target_price    INT           NULL               COMMENT 'Tier2 목표가 (원)',
    tier2_stop_loss       INT           NULL               COMMENT 'Tier2 손절가 (원)',
    tier2_impact_duration VARCHAR(50)   NULL               COMMENT '뉴스 영향 지속 시간 (minutes/hours/days)',
    tier2_confidence      FLOAT         NULL               COMMENT 'Tier2 판단 확신도 (0.0~1.0)',
    tier2_model           VARCHAR(50)   NULL               COMMENT 'Tier2 사용 모델명 (gpt-4o)',
    tier2_tokens          INT           NULL               COMMENT 'Tier2 소비 토큰 수',

    escalated        TINYINT(1)    NOT NULL DEFAULT 0      COMMENT 'Tier2 분석 에스컬레이션 여부 (1=실행됨)',
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '레코드 생성 시각',

    PRIMARY KEY (id),
    INDEX idx_news_stock_code (stock_code),
    INDEX idx_news_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='텔레그램/DART 뉴스 AI 2-Tier 분석 결과 저장';

-- ────────────────────────────────────────────────────────────
-- 2. signal_scores — 세션별 가중 스코어링 결과
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_scores (
    id                  INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    stock_code          VARCHAR(20)   NOT NULL                COMMENT '종목코드 6자리',
    stock_name          VARCHAR(100)  NULL                    COMMENT '종목명',
    news_analysis_id    INT           NULL                    COMMENT '연결된 news_analysis.id (FK)',

    session             ENUM('PRE_MARKET','REGULAR','AFTER_MARKET') NOT NULL COMMENT '매매 세션 (프리마켓/정규장/애프터마켓)',
    nxt_eligible        TINYINT(1)    NULL                    COMMENT 'NXT 대체거래소 거래 가능 종목 여부',

    -- 세션별 가중치가 다르게 적용된 개별 점수 (각 0~100점)
    ai_score            FLOAT         NOT NULL DEFAULT 0      COMMENT 'AI 분석 점수 (정규장 30점/프리·애프터 40점 만점)',
    investor_flow_score FLOAT         NOT NULL DEFAULT 0      COMMENT '외국인·기관 수급 점수 (정규장 20점/프리·애프터 0점)',
    technical_score     FLOAT         NOT NULL DEFAULT 0      COMMENT '기술적 지표 점수 (정규장 25점/프리·애프터 20점)',
    volume_score        FLOAT         NOT NULL DEFAULT 0      COMMENT '거래량 점수 (정규장 15점/프리·애프터 25점)',
    market_env_score    FLOAT         NOT NULL DEFAULT 0      COMMENT '시장 환경 점수 (정규장 10점/프리·애프터 15점)',
    total_score         FLOAT         NOT NULL DEFAULT 0      COMMENT '가중 합산 종합 점수 (0~100점)',

    hard_filter_passed  TINYINT(1)    NOT NULL DEFAULT 0      COMMENT 'Hard 필터 통과 여부 (0=탈락, 1=통과)',
    hard_filter_reason  VARCHAR(200)  NULL                    COMMENT 'Hard 필터 탈락 사유',

    score_detail        JSON          NULL                    COMMENT '점수 산출 상세 내역 (가중치·원점수 JSON)',
    decision            ENUM('BUY','SKIP','WATCH') NULL       COMMENT '최종 매매 판단 (BUY/SKIP/WATCH)',
    decision_reason     TEXT          NULL                    COMMENT '판단 사유 (총점 또는 필터 탈락 이유)',

    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '레코드 생성 시각',

    PRIMARY KEY (id),
    INDEX idx_score_stock_code (stock_code),
    INDEX idx_score_news_id (news_analysis_id),
    INDEX idx_score_total (total_score),
    INDEX idx_score_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='세션별 차등 가중 스코어링 결과 (프리마켓≥80 / 정규장≥70 / 애프터≥85 매수)';

-- ────────────────────────────────────────────────────────────
-- 3. trades — 매매 기록 (매수/매도)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id               INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    stock_code       VARCHAR(20)   NOT NULL                COMMENT '종목코드 6자리',
    stock_name       VARCHAR(100)  NULL                    COMMENT '종목명',

    action           ENUM('BUY','SELL') NOT NULL           COMMENT '매매 구분 (매수/매도)',
    exchange         ENUM('KRX','NXT','SOR') NOT NULL DEFAULT 'SOR' COMMENT '체결 거래소 (KRX/NXT대체거래소/SOR최적라우팅)',
    session          ENUM('PRE_MARKET','REGULAR','CLOSING','AFTER_MARKET') NOT NULL COMMENT '체결 세션',

    price            INT           NOT NULL                COMMENT '체결 단가 (원)',
    quantity         INT           NOT NULL                COMMENT '체결 수량 (주)',
    amount           INT           NOT NULL                COMMENT '체결 금액 = price × quantity (원)',
    fee              INT           NOT NULL DEFAULT 0      COMMENT '수수료 (원)',

    -- 매도 시에만 채워지는 필드
    buy_price        INT           NULL                    COMMENT '매수 시 평균단가 (매도 레코드에만 기록)',
    pnl              INT           NULL                    COMMENT '실현 손익 = (price - buy_price) × quantity (원)',
    pnl_pct          FLOAT         NULL                    COMMENT '실현 손익률 (%, 소수점 2자리)',

    signal_score_id  INT           NULL                    COMMENT '매수 근거 signal_scores.id (FK)',
    sell_reason      ENUM('ATR_STOP','ATR_TRAILING','TIME_CUT','TARGET',
                          'MANUAL','DAILY_CLEANUP','RISK_LIMIT') NULL COMMENT '매도 사유',
    memo             TEXT          NULL                    COMMENT '기타 메모',
    order_id         VARCHAR(50)   NULL                    COMMENT 'KIS 주문번호 (ODNO)',

    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '체결 시각',

    PRIMARY KEY (id),
    INDEX idx_trade_stock_code (stock_code),
    INDEX idx_trade_signal_id (signal_score_id),
    INDEX idx_trade_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='전체 매수·매도 체결 기록 (세션·거래소·PnL 포함)';

-- ────────────────────────────────────────────────────────────
-- 4. positions — 포지션 관리 (보유/청산)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id                  INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    stock_code          VARCHAR(20)   NOT NULL                COMMENT '종목코드 6자리',
    stock_name          VARCHAR(100)  NULL                    COMMENT '종목명',

    exchange            ENUM('KRX','NXT','SOR') NOT NULL DEFAULT 'SOR' COMMENT '매수 거래소',
    session             ENUM('PRE_MARKET','REGULAR','AFTER_MARKET') NOT NULL COMMENT '최초 매수 세션',

    quantity            INT           NOT NULL                COMMENT '보유 수량 (주)',
    avg_price           INT           NOT NULL                COMMENT '평균 매수 단가 (원)',
    current_price       INT           NOT NULL DEFAULT 0      COMMENT '현재가 (실시간 갱신, 원)',
    unrealized_pnl      INT           NOT NULL DEFAULT 0      COMMENT '평가 손익 = (current - avg) × qty (원)',
    unrealized_pnl_pct  FLOAT         NOT NULL DEFAULT 0      COMMENT '평가 손익률 (%)',

    -- ATR 기반 EXIT 기준값
    atr_value           FLOAT         NULL                    COMMENT 'ATR(14) 값 — 손절·트레일링 계산 기준',
    stop_loss_price     INT           NULL                    COMMENT '고정 손절가 = avg - ATR × stop_multiplier (원)',
    trailing_stop_price INT           NULL                    COMMENT '트레일링 스톱가 = 최고가 - ATR × trailing_multiplier (원)',
    highest_price       INT           NULL                    COMMENT '보유 중 최고 도달 가격 (트레일링 기준, 원)',

    signal_score_id     INT           NULL                    COMMENT '매수 근거 signal_scores.id (FK)',
    buy_trade_id        INT           NULL                    COMMENT '매수 체결 trades.id (FK)',
    status              ENUM('OPEN','CLOSED') NOT NULL DEFAULT 'OPEN' COMMENT '포지션 상태 (보유중/청산완료)',

    opened_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '매수(포지션 오픈) 시각',
    closed_at           DATETIME      NULL                    COMMENT '매도(포지션 청산) 시각',

    PRIMARY KEY (id),
    INDEX idx_pos_stock_code (stock_code),
    INDEX idx_pos_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='보유 포지션 및 ATR EXIT 기준값 관리';

-- ────────────────────────────────────────────────────────────
-- 5. market_snapshots — 시장 데이터 스냅샷 (기술지표 + 수급)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_snapshots (
    id               INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    stock_code       VARCHAR(20)   NOT NULL                COMMENT '종목코드 6자리',

    current_price    INT           NULL                    COMMENT '현재가 (원)',
    change_pct       FLOAT         NULL                    COMMENT '전일 대비 등락률 (%)',
    volume           INT           NULL                    COMMENT '당일 거래량 (주)',
    volume_ratio     FLOAT         NULL                    COMMENT '거래량 비율 = 현재거래량 / 평균거래량',

    -- 기술적 지표 (TA-Lib 계산값)
    rsi_14           FLOAT         NULL                    COMMENT 'RSI(14) — 과매수>70, 과매도<30',
    macd             FLOAT         NULL                    COMMENT 'MACD 라인 (12일EMA - 26일EMA)',
    macd_signal      FLOAT         NULL                    COMMENT 'MACD 시그널 라인 (MACD 9일EMA)',
    ma_5             FLOAT         NULL                    COMMENT '5일 이동평균선',
    ma_20            FLOAT         NULL                    COMMENT '20일 이동평균선',
    ma_60            FLOAT         NULL                    COMMENT '60일 이동평균선',
    atr_14           FLOAT         NULL                    COMMENT 'ATR(14) — 손절가 계산에 사용',
    bb_upper         FLOAT         NULL                    COMMENT '볼린저밴드 상단 (20일 MA + 2σ)',
    bb_lower         FLOAT         NULL                    COMMENT '볼린저밴드 하단 (20일 MA - 2σ)',

    -- 외국인·기관 수급 (정규장에서만 수집)
    foreign_net      INT           NULL                    COMMENT '외국인 순매수 금액 (원, 음수=순매도)',
    institution_net  INT           NULL                    COMMENT '기관 순매수 금액 (원, 음수=순매도)',

    orderbook        JSON          NULL                    COMMENT '호가창 스냅샷 (매도5단계·매수5단계 JSON)',

    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '스냅샷 기록 시각',

    PRIMARY KEY (id),
    INDEX idx_snap_stock_code (stock_code),
    INDEX idx_snap_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='실시간 시세·기술지표·수급·호가 스냅샷';

-- ────────────────────────────────────────────────────────────
-- 6. strategy_params — 전략 파라미터 키-값 저장소
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS strategy_params (
    id               INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    param_key        VARCHAR(100)  NOT NULL                COMMENT '파라미터 키 (고유값, snake_case)',
    param_value      TEXT          NULL                    COMMENT '단순 문자열 파라미터 값',
    param_json       JSON          NULL                    COMMENT 'JSON 구조 파라미터 값 (세션별 파라미터 등)',
    description      VARCHAR(500)  NULL                    COMMENT '파라미터 설명',
    updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정 시각',

    PRIMARY KEY (id),
    UNIQUE KEY uq_param_key (param_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='전략 파라미터 키-값 저장소 (DB에서 동적 변경 가능)';

-- ────────────────────────────────────────────────────────────
-- 7. daily_summary — 일일 PnL 정산 (장 마감 후 1행씩)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_summary (
    id               INT           NOT NULL AUTO_INCREMENT  COMMENT '자동 증가 기본키',
    trade_date       DATE          NOT NULL                COMMENT '거래일 (YYYY-MM-DD)',
    total_trades     INT           NOT NULL DEFAULT 0      COMMENT '당일 총 매매 건수 (매수+매도)',
    wins             INT           NOT NULL DEFAULT 0      COMMENT '당일 수익 매도 건수',
    losses           INT           NOT NULL DEFAULT 0      COMMENT '당일 손실 매도 건수',
    win_rate         FLOAT         NULL                    COMMENT '당일 승률 = wins / (wins+losses) × 100 (%)',
    realized_pnl     INT           NOT NULL DEFAULT 0      COMMENT '당일 실현 손익 합계 (원)',
    pre_market_pnl   INT           NOT NULL DEFAULT 0      COMMENT '프리마켓 세션 실현 손익 (원)',
    regular_pnl      INT           NOT NULL DEFAULT 0      COMMENT '정규장 세션 실현 손익 (원)',
    after_market_pnl INT           NOT NULL DEFAULT 0      COMMENT '애프터마켓 세션 실현 손익 (원)',
    max_drawdown     FLOAT         NULL                    COMMENT '당일 최대 낙폭 (%, 장중 최고점 대비)',

    PRIMARY KEY (id),
    UNIQUE KEY uq_trade_date (trade_date),
    INDEX idx_summary_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='일일 거래 정산 요약 (20:05 daily_cleanup.py 에서 자동 생성)';

-- ────────────────────────────────────────────────────────────
-- 8. 기본 전략 파라미터 초기 데이터 삽입
-- ────────────────────────────────────────────────────────────
INSERT IGNORE INTO strategy_params (param_key, param_value, param_json, description) VALUES
('buy_score_threshold_pre',  '80',  NULL, '프리마켓 매수 스코어 임계값'),
('buy_score_threshold_reg',  '70',  NULL, '정규장 매수 스코어 임계값'),
('buy_score_threshold_aft',  '85',  NULL, '애프터마켓 매수 스코어 임계값'),
('max_daily_loss',           '50000', NULL, '일일 최대 손실 한도(원)'),
('cooldown_minutes',         '30',  NULL, '매도 후 동일 종목 쿨다운(분)'),
('max_position_count',       '3',   NULL, '정규장 최대 동시 포지션 수'),
('scoring_weights_regular',  NULL,
    '{"ai":30,"flow":20,"tech":25,"volume":15,"market":10}',
    '정규장 스코어링 가중치'),
('scoring_weights_extended', NULL,
    '{"ai":40,"flow":0,"tech":20,"volume":25,"market":15}',
    '프리/애프터마켓 스코어링 가중치'),
('session_params_pre', NULL,
    '{"exchange":"NXT","buy_score_threshold":80,"max_position_pct":10,"max_concurrent_positions":1,"atr_stop_multiplier":2.5,"atr_trailing_multiplier":1.5,"nxt_only":true,"use_investor_flow":false,"volume_min_ratio":200}',
    '프리마켓 세션 파라미터'),
('session_params_regular', NULL,
    '{"exchange":"SOR","buy_score_threshold":70,"max_position_pct":20,"max_concurrent_positions":3,"atr_stop_multiplier":2.0,"atr_trailing_multiplier":1.0,"nxt_only":false,"use_investor_flow":true,"volume_min_ratio":300}',
    '정규장 세션 파라미터'),
('session_params_after', NULL,
    '{"exchange":"NXT","buy_score_threshold":85,"max_position_pct":8,"max_concurrent_positions":1,"atr_stop_multiplier":3.0,"atr_trailing_multiplier":2.0,"nxt_only":true,"use_investor_flow":false,"volume_min_ratio":150}',
    '애프터마켓 세션 파라미터');
