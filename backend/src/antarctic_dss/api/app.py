from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from antarctic_dss.api.routes_voyage import router as voyage_router
from antarctic_dss.api.routes_data import router as data_router

def create_app() -> FastAPI:
    app = FastAPI(
        title='Antarctic Voyage Decision Support System',
        description='AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System. Departure-time-aware predictive Antarctic voyage planning.',
        version='0.1.0',
    )
    
    # CORS for Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        # Any local port: Next.js silently moves to 3001+ when 3000 is taken.
        allow_origin_regex=r'http://(localhost|127\.0\.0\.1)(:\d+)?',
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    
    app.include_router(voyage_router, prefix='/api/voyage', tags=['Voyage Planning'])
    app.include_router(data_router, prefix='/api', tags=['Data & Environment'])
    
    @app.get('/health')
    async def health():
        return {'status': 'healthy', 'service': 'antarctic-dss'}
    
    return app

app = create_app()
