"""
Data Collector for HFT Analytics — FastAPI placeholder.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Data Collector API",
    description="Real-time market data collection and analytics for HFT research.",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {"message": "Hello, HFT World!", "status": "alive"}


@app.get("/health")
async def health():
    return {"status": "healthy"}