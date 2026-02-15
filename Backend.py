from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from mitigation.city_infrastructure_network import mitigate

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Fallback OPTIONS handler in case middleware doesn't catch it
@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


class CityRequest(BaseModel):
    city: str


@app.post("/run_pipeline")
def run_pipeline(req: CityRequest):
    from main import receive
    analysis = receive(req.city)
    return {"status": "ok", "analysis": analysis}


@app.post("/mitigate")
def mitigate_pipeline():
    return mitigate()