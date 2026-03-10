from backend.routers.health import router as health_router
from backend.routers.dashboard import router as dashboard_router
from backend.routers.analysis_log import router as analysis_router
from backend.routers.trades import router as trades_router
from backend.routers.positions import router as positions_router
from backend.routers.account import router as account_router

__all__ = [
    "health_router",
    "dashboard_router",
    "analysis_router",
    "trades_router",
    "positions_router",
    "account_router",
]
