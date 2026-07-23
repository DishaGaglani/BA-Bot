import json
import requests
import urllib3
import os
import sys
import uuid
import time
from fastapi import FastAPI, HTTPException, Depends, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from database import engine, SessionLocal
from utils.migrate import run_migration
from utils.prod_ready import validate_environment, setup_global_exception_handlers, logger, request_with_retry

# Run database migrations and seed default data on startup
run_migration()

# Validate environment variables on startup
validate_environment()

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

# Setup global exception handlers
setup_global_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standardized response middleware and request logging
@app.middleware("http")
async def standardize_responses_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    
    # Simple user identification check if token is supplied
    user_id = "anonymous"
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from auth.jwt import decode_access_token
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                user_id = payload["sub"]
        except Exception:
            pass
            
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        raise exc
        
    process_time = (time.time() - start_time) * 1000
    
    # Log trace information: Request ID, User ID, Endpoint, Response Time, Status Code
    logger.info(
        f"user_id={user_id} endpoint={request.url.path} status_code={response.status_code} response_time={process_time:.2f}ms",
        extra={"traceId": trace_id}
    )
    
    # Wrap successful JSON responses
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type and response.status_code < 400:
        if request.url.path == "/health":
            return response
            
        # Consume the response body stream
        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)
        
        try:
            body_json = json.loads(body_bytes)
            # Prevent double wrapping
            if isinstance(body_json, dict) and "success" in body_json and ("data" in body_json or "traceId" in body_json):
                new_bytes = body_bytes
            else:
                standard_body = {
                    "success": True,
                    "data": body_json,
                    "message": "Success"
                }
                new_bytes = json.dumps(standard_body).encode("utf-8")
        except Exception:
            new_bytes = body_bytes
            
        headers = dict(response.headers)
        if "content-length" in headers:
            del headers["content-length"]
            
        return Response(
            content=new_bytes,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json"
        )
        
    return response

# Include routers
app.include_router(auth.routes.router)
app.include_router(routes.projects.router)
app.include_router(routes.admin.router)

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf"

# Health check route
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
        
    ai_ok = False
    prediction_url = os.getenv("PREDICTION_URL", "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf")
    try:
        res = requests.head(prediction_url, timeout=5, verify=False)
        if res.status_code < 500:
            ai_ok = True
    except Exception:
        pass
        
    return {
        "status": "healthy" if (db_ok and ai_ok) else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "aiService": "reachable" if ai_ok else "unreachable",
        "version": "1.0.0",
        "environment": os.getenv("ENV", "development"),
        "timestamp": time.time()
    }

class MessageRequest(BaseModel):
    question: str
    projectId: int | None = None
    sessionId: str | None = None

@app.post("/api/predict")
def predict(
    payload: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Fetch project based on payload
    if payload.projectId:
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == payload.projectId).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project workspace not found")
    elif payload.sessionId:
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.session_id == payload.sessionId).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project session not found")
    else:
        raise HTTPException(status_code=400, detail="Either projectId or sessionId is required")

    # Check if project is locked
    if project.locked:
        raise HTTPException(status_code=403, detail="This project has been locked by an administrator and cannot be modified.")

    # 2. Save user message to database
    is_first_message = len(project.messages) == 0
    save_message(db, project.id, "user", payload.question)
    
    # 3. Trigger rolling summarization (every 10 active messages)
    check_and_summarize(db, project)
    
    # 4. Fetch optimized conversation history window
    active_history = get_active_messages(db, project.id, limit=5)
    
    # 5. Deterministic gap analysis & section targeting
    state = get_structured_state(project)
    gaps = analyze_gaps(state)
    active_section = gaps.get("current_section")
    
    # 6. Build optimized prompt
    optimized_prompt = build_optimized_prompt(
        project=project,
        gap_analysis=gaps,
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
            # Use request_with_retry for robust LLM streaming connection
            response = request_with_retry("POST", PREDICTION_URL, json=payload_dict, stream=True, timeout=90, verify=False)
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
                    update_project_state(bg_db, bg_project, question, ai_reply, active_section=active_section)
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
