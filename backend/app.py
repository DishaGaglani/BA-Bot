import json
import requests
import urllib3
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from database import engine, SessionLocal
from utils.migrate import run_migration

# Run database migrations and seed default data on startup
run_migration()

# Import route handlers
import auth.routes
import routes.projects
import routes.admin
from dependencies.auth import get_current_user, get_db
from models import User, UserRole, Project, ProjectMember, ProjectMemberRole
from services.audit import log_action
from services.conversation_manager import save_message, get_active_messages
from services.summary_manager import check_and_summarize
from services.gap_analyzer import analyze_gaps
from services.project_state_manager import get_structured_state, update_project_state, get_legacy_payload
from services.prompt_builder import build_optimized_prompt, estimate_tokens

# Disable SSL Warnings for self-signed certificates or proxy contexts
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="BA Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.routes.router)
app.include_router(routes.projects.router)
app.include_router(routes.admin.router)

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf"


class MessageRequest(BaseModel):
    message: str


class PredictionRequest(BaseModel):
    question: str
    sessionId: str | None = None
    projectId: int | None = None


class MessageResponse(BaseModel):
    status: str
    reply: str


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/message", response_model=MessageResponse)
def receive_message(payload: MessageRequest) -> MessageResponse:
    return MessageResponse(
        status="received",
        reply=f"Received: {payload.message}",
    )


@app.post("/api/predict")
def predict(
    payload: PredictionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> StreamingResponse:
    # 1. Resolve and verify project access
    project = None
    
    if payload.projectId:
        # Check by projectId
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == payload.projectId).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        # Verify user has access to this project
        if current_user.role != UserRole.ADMIN:
            # Check owner
            if project.owner_id != current_user.id:
                # Check member
                member = db.query(ProjectMember).filter(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == current_user.id
                ).first()
                if not member:
                    log_action(
                        db=db,
                        user_id=current_user.id,
                        action="permission denied",
                        project_id=project.id,
                        metadata={"reason": "User tried to chat on project they do not belong to"}
                    )
                    raise HTTPException(status_code=403, detail="You do not have access to this project's chat")
                    
        # Verify sessionId matches project sessionId
        if payload.sessionId and project.session_id and payload.sessionId != project.session_id:
            log_action(
                db=db,
                user_id=current_user.id,
                action="permission denied",
                project_id=project.id,
                metadata={"reason": "Session ID mismatch for project chat request"}
            )
            raise HTTPException(status_code=403, detail="Session ID does not match this project")
            
    elif payload.sessionId:
        # Check by sessionId
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.session_id == payload.sessionId).first()
        if not project:
            raise HTTPException(status_code=403, detail="Invalid session reference")
            
        # Verify access
        if current_user.role != UserRole.ADMIN:
            if project.owner_id != current_user.id:
                member = db.query(ProjectMember).filter(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == current_user.id
                ).first()
                if not member:
                    log_action(
                        db=db,
                        user_id=current_user.id,
                        action="permission denied",
                        project_id=project.id,
                        metadata={"reason": "User tried to chat on session they do not belong to"}
                    )
                    raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=400, detail="Either projectId or sessionId is required")

    # 2. Save user message to database
    is_first_message = len(project.messages) == 0
    save_message(db, project.id, "user", payload.question)
    
    # 3. Trigger rolling summarization (every 15 active messages)
    check_and_summarize(db, project)
    
    # 4. Fetch optimized conversation history window
    active_history = get_active_messages(db, project.id, limit=5)
    
    # 5. Deterministic gap analysis & section targeting
    state = get_structured_state(project)
    gaps = analyze_gaps(state)
    
    # 6. Build optimized prompt
    optimized_prompt = build_optimized_prompt(
        state=state,
        gap_analysis=gaps,
        summary=project.summary,
        active_history=active_history,
        current_query=payload.question
    )
    
    # 7. Print size metrics
    prompt_size = len(optimized_prompt)
    summary_size = len(project.summary or "")
    state_size = len(project.structured_state or "")
    history_size = sum(len(m.text) for m in active_history)
    est_tokens = estimate_tokens(optimized_prompt)
    
    print("================== PROMPT SIZE LOGGING ==================")
    print(f"Project ID: {project.id}")
    print(f"Target Section Focus: {gaps.get('current_section')}")
    print(f"Input Token Estimate: ~{est_tokens}")
    print(f"Full Prompt Size: {prompt_size} chars")
    print(f"Conversation Summary Size: {summary_size} chars")
    print(f"Structured Project State Size: {state_size} chars")
    print(f"Active History Size: {history_size} chars")
    print("=========================================================")

    # 8. Log conversation started if first message
    if is_first_message:
        log_action(
            db=db,
            user_id=current_user.id,
            action="conversation started",
            project_id=project.id,
            metadata={"session_id": project.session_id}
        )

    # 9. Define prediction payload maintaining the session's chat ID
    payload_dict = {
        "question": optimized_prompt,
        "streaming": True
    }
    if project.session_id:
        payload_dict["chatId"] = project.session_id
        payload_dict["overrideConfig"] = {"sessionId": project.session_id}

    project_id = project.id
    question = payload.question

    def event_generator():
        from database import SessionLocal
        bg_db = SessionLocal()
        ai_chunks = []
        try:
            response = requests.post(PREDICTION_URL, json=payload_dict, stream=True, timeout=90, verify=False)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8", "ignore").strip()
                    if line_str.startswith("data:"):
                        yield f"{line_str}\n\n"
                        try:
                            data_content = line_str[5:].strip()
                            chunk_data = json.loads(data_content)
                            if chunk_data.get("event") == "token":
                                token_val = chunk_data.get("data")
                                if isinstance(token_val, str):
                                    ai_chunks.append(token_val)
                        except Exception:
                            pass
            
            # Post-chat completion processing using the dedicated background session
            ai_reply = "".join(ai_chunks).strip()
            if ai_reply:
                bg_project = bg_db.query(Project).options(joinedload(Project.messages)).filter(Project.id == project_id).first()
                if bg_project:
                    save_message(bg_db, bg_project.id, "ai", ai_reply)
                    update_project_state(bg_db, bg_project, question, ai_reply)
                    legacy_payload = get_legacy_payload(bg_project)
                    bg_project.data = json.dumps(legacy_payload)
                    bg_db.commit()
                    print(f"State updates completed successfully for project {bg_project.id}.")
                
        except Exception as exc:
            print(f"Error inside event_generator: {str(exc)}")
            err_data = json.dumps({"event": "error", "message": str(exc)})
            yield f"data: {err_data}\n\n"
        finally:
            bg_db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
