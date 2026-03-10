from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.redis_client import get_redis
from backend.services.kis_api import KISApi
from backend.utils.logger import logger

router = APIRouter(prefix="/api/account", tags=["account"])

_CACHE_KEY = "account:balance"
_CACHE_TTL = 60  # 1분


class AccountBalance(BaseModel):
    available_cash: int = 0
    total_evaluation: int = 0
    purchase_amount: int = 0
    eval_amount: int = 0
    eval_pnl: int = 0
    eval_pnl_pct: Optional[float] = None
    net_asset: int = 0


@router.get("/balance", response_model=AccountBalance)
async def account_balance():
    r = await get_redis()
    cached = await r.get(_CACHE_KEY)
    if cached:
        return AccountBalance(**json.loads(cached))

    kis = KISApi()
    try:
        result = await kis.get_balance()
    except Exception as exc:
        logger.error(f"KIS 잔고 조회 실패: {exc}")
        fallback = await r.get(f"{_CACHE_KEY}:last")
        if fallback:
            return AccountBalance(**json.loads(fallback))
        return AccountBalance()
    finally:
        await kis.close()

    output2 = result.get("output2", [{}])
    summary = output2[0] if output2 else {}

    purchase = int(summary.get("pchs_amt_smtl_amt", 0))
    eval_amt = int(summary.get("evlu_amt_smtl_amt", 0))
    eval_pnl = int(summary.get("evlu_pfls_smtl_amt", 0))
    eval_pnl_pct = round(eval_pnl / purchase * 100, 2) if purchase > 0 else None

    balance = AccountBalance(
        available_cash=int(summary.get("dnca_tot_amt", 0)),
        total_evaluation=int(summary.get("tot_evlu_amt", 0)),
        purchase_amount=purchase,
        eval_amount=eval_amt,
        eval_pnl=eval_pnl,
        eval_pnl_pct=eval_pnl_pct,
        net_asset=int(summary.get("nass_amt", 0)),
    )

    payload = balance.model_dump_json()
    await r.setex(_CACHE_KEY, _CACHE_TTL, payload)
    await r.set(f"{_CACHE_KEY}:last", payload)

    return balance
