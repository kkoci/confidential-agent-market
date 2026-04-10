from fastapi import FastAPI, Request

from api.routes.health import router as health_router
from api.routes.market import router as market_router
from api.services.payment import KitePaymentRequired, payment_required_response

app = FastAPI(
    title="Confidential Agent Negotiation Market",
    description=(
        "Decentralised OTC market where AI agents negotiate trade terms "
        "inside a Trusted Execution Environment (Intel TDX via Phala Cloud). "
        "All negotiation terms stay sealed until atomic on-chain settlement. "
        "No frontrunning. No MEV."
    ),
    version="0.1.0",
)


@app.exception_handler(KitePaymentRequired)
async def payment_required_handler(request: Request, exc: KitePaymentRequired):
    return payment_required_response(exc.resource_url, exc.description, exc.amount)


app.include_router(health_router)
app.include_router(market_router)
