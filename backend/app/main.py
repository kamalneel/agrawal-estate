"""
Agrawal Estate Planner - Main Application Entry Point

A modular monolithic application for family estate and financial planning.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.scheduler import start_scheduler

logger = logging.getLogger(__name__)

# Import module routers
from app.modules.dashboard.router import router as dashboard_router
from app.modules.income.router import router as income_router
from app.modules.tax.router import router as tax_router
from app.modules.investments.router import router as investments_router
from app.modules.equity.router import router as equity_router
from app.modules.cash.router import router as cash_router
from app.modules.real_estate.router import router as real_estate_router
from app.modules.estate_planning.router import router as estate_planning_router
from app.modules.reports.router import router as reports_router
from app.modules.strategies.router import router as strategies_router
from app.modules.strategies.learning_router import router as learning_router
from app.modules.india_investments.router import router as india_investments_router
from app.modules.india_investments.mf_research_router import router as mf_research_router
from app.modules.plaid.router import router as plaid_router
from app.ingestion.router import router as ingestion_router
from app.core.auth_router import router as auth_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Family estate planning and financial management application",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    
    # CORS middleware for local network access
    # Use ["*"] if CORS_ALLOW_ALL is True (development), otherwise use explicit origins
    cors_origins = ["*"] if settings.CORS_ALLOW_ALL else settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register module routers
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["Dashboard"])
    app.include_router(income_router, prefix="/api/v1/income", tags=["Income"])
    app.include_router(tax_router, prefix="/api/v1/tax", tags=["Tax"])
    app.include_router(investments_router, prefix="/api/v1/investments", tags=["Investments"])
    app.include_router(equity_router, prefix="/api/v1/equity", tags=["Equity"])
    app.include_router(cash_router, prefix="/api/v1/cash", tags=["Cash"])
    app.include_router(real_estate_router, prefix="/api/v1/real-estate", tags=["Real Estate"])
    app.include_router(estate_planning_router, prefix="/api/v1/estate-planning", tags=["Estate Planning"])
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["Reports"])
    app.include_router(strategies_router, prefix="/api/v1/strategies", tags=["Strategies"])
    app.include_router(learning_router, prefix="/api/v1/strategies", tags=["Learning & RLHF"])
    app.include_router(india_investments_router, prefix="/api/v1/india-investments", tags=["India Investments"])
    app.include_router(mf_research_router, prefix="/api/v1/india-investments/mf-research", tags=["Mutual Fund Research"])
    app.include_router(plaid_router, prefix="/api/v1", tags=["Plaid"])
    app.include_router(ingestion_router, prefix="/api/v1/ingestion", tags=["Data Ingestion"])
    
    @app.get("/", tags=["Health"])
    async def root():
        """Root endpoint - health check."""
        return {
            "application": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running"
        }
    
    @app.get("/api/health", tags=["Health"])
    async def health_check():
        """API health check endpoint."""
        return {"status": "healthy"}
    
    @app.get("/api/cache/stats", tags=["Health"])
    async def cache_stats():
        """Get cache statistics for debugging."""
        from app.core.cache import get_cache_stats
        return get_cache_stats()
    
    @app.post("/api/cache/clear", tags=["Health"])
    async def clear_cache(prefix: str = None):
        """Clear cache entries. Optionally filter by prefix."""
        from app.core.cache import clear_cache
        count = clear_cache(prefix)
        return {"cleared": count, "prefix": prefix}
    
    # Start the recommendation scheduler (with delayed start for faster server response)
    @app.on_event("startup")
    async def startup_event():
        """Start background scheduler on app startup with delay for faster response."""
        import threading
        
        def delayed_scheduler_start():
            """Start scheduler after a short delay to let the server become responsive."""
            import time
            time.sleep(3)  # Wait 3 seconds before starting scheduler
            try:
                start_scheduler()
                logger.info("Background scheduler started after delay")
            except Exception as e:
                logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=delayed_scheduler_start, daemon=True)
        scheduler_thread.start()
        logger.info("Application startup complete - scheduler will start in background")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Stop background scheduler on app shutdown."""
        from app.core.scheduler import stop_scheduler
        try:
            stop_scheduler()
            logger.info("Application shutdown - scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

