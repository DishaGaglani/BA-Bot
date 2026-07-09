import json
import ssl
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import engine, SessionLocal
import models

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="BA Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/b40934a1-9758-4ce7-b938-781a4f74723a"


class MessageRequest(BaseModel):
    message: str


class PredictionRequest(BaseModel):
    question: str
    sessionId: str | None = None


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


@app.get("/api/project")
def get_project(db: Session = Depends(get_db)) -> dict[str, object] | None:
    db_project = db.query(models.Project).first()
    if db_project:
        return json.loads(db_project.data)
    return None


@app.post("/api/project")
def save_project(payload: ProjectPayload, db: Session = Depends(get_db)) -> dict[str, object]:
    db_project = db.query(models.Project).first()
    project_data_json = json.dumps(payload.model_dump())
    if db_project:
        db_project.data = project_data_json
    else:
        db_project = models.Project(data=project_data_json)
        db.add(db_project)
    db.commit()
    return {"status": "saved", "data": payload.model_dump()}


@app.post("/api/predict")
def predict(payload: PredictionRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    db_project = db.query(models.Project).first()
    context_prefix = ""
    if db_project:
        try:
            project_data = json.loads(db_project.data)
            proj_info = project_data.get("project", {})
            if proj_info and proj_info.get("name"):
                context_prefix = (
                    f"[Project Context - Name: {proj_info.get('name')}, "
                    f"Department: {proj_info.get('department')}, "
                    f"Sponsor: {proj_info.get('sponsor')}, "
                    f"Business Unit: {proj_info.get('business_unit')}, "
                    f"Expected Completion: {proj_info.get('expected_completion')}]\n"
                )
        except Exception:
            pass

    question = payload.question
    if not payload.sessionId and context_prefix:
        question = f"{context_prefix}User query: {payload.question}"

    payload_dict = {"question": question, "streaming": True}
    if payload.sessionId:
        payload_dict["overrideConfig"] = {"sessionId": payload.sessionId}
    body = json.dumps(payload_dict).encode("utf-8")
    
    request = urllib.request.Request(
        PREDICTION_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    def event_generator():
        try:
            try:
                response = urllib.request.urlopen(request, timeout=30)
            except urllib.error.URLError as exc:
                try:
                    context = ssl._create_unverified_context()
                    response = urllib.request.urlopen(request, context=context, timeout=30)
                except Exception:
                    raise exc

            with response:
                for line in response:
                    line_str = line.decode("utf-8", "ignore").strip()
                    if line_str.startswith("data:"):
                        yield f"{line_str}\n\n"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            err_data = json.dumps({"event": "error", "message": "Prediction service error", "details": detail})
            yield f"data: {err_data}\n\n"
        except Exception as exc:
            err_data = json.dumps({"event": "error", "message": str(exc)})
            yield f"data: {err_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
