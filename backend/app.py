import json
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="BA Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/b58d1e06-0934-48af-be9f-3bf82d6bcd24"


class MessageRequest(BaseModel):
    message: str


class PredictionRequest(BaseModel):
    question: str


class MessageResponse(BaseModel):
    status: str
    reply: str


class ProjectPayload(BaseModel):
    project: dict[str, str]
    overview: dict[str, object]
    discovery: dict[str, object]
    functional_requirements: list[dict[str, object]]
    missing_fields: list[str]
    next_question: str


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/message", response_model=MessageResponse)
def receive_message(payload: MessageRequest) -> MessageResponse:
    return MessageResponse(
        status="received",
        reply=f"Received: {payload.message}",
    )


@app.post("/api/project")
def save_project(payload: ProjectPayload) -> dict[str, object]:
    return {"status": "saved", "data": payload.model_dump()}


@app.post("/api/predict")
def predict(payload: PredictionRequest) -> dict[str, object]:
    body = json.dumps({"question": payload.question}).encode("utf-8")
    request = urllib.request.Request(
        PREDICTION_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
            try:
                parsed = json.loads(raw_body)
            except json.JSONDecodeError:
                parsed = {"raw": raw_body}
            return {"status": "success", "data": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise HTTPException(status_code=exc.code, detail={"message": "Prediction service error", "details": detail}) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLError):
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, context=context, timeout=30) as response:
                raw_body = response.read().decode("utf-8")
                try:
                    parsed = json.loads(raw_body)
                except json.JSONDecodeError:
                    parsed = {"raw": raw_body}
                return {"status": "success", "data": parsed}
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=502, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
