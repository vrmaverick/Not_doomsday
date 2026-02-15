from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class CityRequest(BaseModel):
    city: str

@app.post("/run_pipeline")
def run_pipeline(req: CityRequest):
    # import your existing function
    from main import receive  # your Not_Doomsday main pipeline
    analysis = receive(req.city)  # returns dict
    return {"status": "ok", "analysis": analysis}
