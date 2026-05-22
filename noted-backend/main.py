from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import signal
import sys
import asyncio

from config import settings
from api.websocket import websocket_router
from api.routes import api_router
from utils.logging import setup_logging
from database.connection import init_db, close_db

from api.websocket import manager
from services.model_manager import model_manager

# Setup logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await model_manager.initialize_models()
    await manager.initialize_audio_processor_async()  # Initialize audio processor after models are loaded
    yield
    # Shutdown
    print("Starting application shutdown...")
    
    await manager.shutdown()
    await model_manager.cleanup_models()
    await close_db()
    
    print("Application shutdown completed")


# Create FastAPI app
app = FastAPI(
    title="Noted Transcription Backend",
    description="Real-time audio transcription service for migrant service encounters",
    version="0.0.1",
    debug=settings.server.debug,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(websocket_router, prefix="/ws")
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return JSONResponse({
        "message": "Noted Transcription Backend",
        "status": "running",
        "version": "0.0.1"
    })

@app.get("/health")
async def health_check():
    # Simple health check without external service dependencies
    services_status = {
        "backend": "ready"
    }

    return JSONResponse({
        "status": "healthy",
        "services": services_status
    })

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, initiating graceful shutdown...")
        # The FastAPI lifespan context manager will handle the cleanup
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    setup_signal_handlers()
    print("Starting Noted Backend Server...")
    print(f"Server will be available at http://{settings.server.host}:{settings.server.port}")
    
    try:
        uvicorn.run(
            "main:app",
            host=settings.server.host,
            port=settings.server.port,
            reload=False,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, shutting down...")
    except Exception as e:
        print(f"\n Server error: {e}")
    finally:
        print(" Server shutdown complete")
