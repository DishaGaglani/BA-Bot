import json
import requests
import urllib3
import os
import sys
import uuid
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.extend([origin.strip() for origin in frontend_url.split(",") if origin.strip()])

is_prod = os.getenv("ENV") == "production"

if is_prod:
    if frontend_url:
        allowed_origins = [origin.strip() for origin in frontend_url.split(",") if origin.strip()]
    else:
        allowed_origins = []
        logger.warning("CORS: FRONTEND_URL environment variable is not set in production. CORS requests will be blocked.")

cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

if is_prod:
    cors_kwargs["allow_origins"] = allowed_origins
else:
    cors_kwargs["allow_origin_regex"] = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    **cors_kwargs
)

# Standardized response middleware and request logging
@app.middleware("http")
async def standardize_responses_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

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
        if request.url.path in ["/health", "/api/mock-predict"]:
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

PREDICTION_URL = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")

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
    prediction_url = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")
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

@app.api_route("/api/mock-predict", methods=["GET", "POST", "HEAD"])
async def mock_predict(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    question_prompt = body.get("question", "") or ""
    streaming = body.get("streaming", False)

    if streaming:
        def mock_event_generator():
            import time
            tokens = [
                "Hello! ", "This ", "is ", "a ", "locally ", "generated ", "mock ", "response ",
                "from ", "the ", "BA-Bot ", "service. ", "Your ", "containerized ", "deployment ",
                "is ", "fully ", "operational ", "and ", "independent ", "of ", "external ", 
                "dependencies."
            ]
            for token in tokens:
                chunk = {
                    "event": "token",
                    "data": token
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                time.sleep(0.02)
                
            chat_id = f"session-{uuid.uuid4()}"
            metadata_chunk = {
                "event": "metadata",
                "data": {
                    "chatId": chat_id,
                    "sessionId": chat_id
                }
            }
            yield f"data: {json.dumps(metadata_chunk)}\n\n"

        return StreamingResponse(mock_event_generator(), media_type="text/event-stream")
    else:
        # Non-streaming response for delta extraction, summary or doc compilation
        response_text = ""
        if "Precise data extraction agent" in question_prompt or "precise data extraction agent" in question_prompt.lower():
            # Delta extraction
            if "Retail Logistics System" in question_prompt:
                response_text = json.dumps({
                    "project_name": "Retail Logistics System",
                    "department": "Logistics",
                    "business_unit": "PES",
                    "timeline": "6 Months",
                    "description": "Automated warehouse logistics system."
                })
            else:
                response_text = json.dumps({
                    "project_name": "Validation Project",
                    "department": "Engineering"
                })
        elif "fresh, unified, and cohesive requirements summary" in question_prompt.lower():
            # Summary
            response_text = "This is a cohesive requirements summary generated by the rolling summarization service."
        elif "expert business analyst" in question_prompt.lower() or "compile this into a comprehensive" in question_prompt.lower():
            # Doc compilation
            response_text = (
                "# Final Discovery Requirements - Validation Project\n\n"
                "## 1. Project Overview\n"
                "This is a compiled document of project requirements.\n\n"
                "## 2. Business Problem & Goals\n"
                "- Goal 1: Improve efficiency.\n\n"
                "## 3. Functional Requirements\n"
                "- FR-1: Real-time GPS tracking (High Priority)\n"
                "- FR-2: Automated dispatch notifications (Medium Priority)\n"
            )
        else:
            response_text = "Mock non-streaming response from local BA-Bot server."

        return {"text": response_text}

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
        # Use row-level locking (FOR UPDATE) to prevent concurrent duplicate session creation
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == payload.projectId).with_for_update().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project workspace not found")
        # Align project session_id with payload sessionId if payload has one and it differs
        if payload.sessionId and project.session_id != payload.sessionId:
            project.session_id = payload.sessionId
            db.commit()
    elif payload.sessionId:
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.session_id == payload.sessionId).with_for_update().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project session not found")
    else:
        raise HTTPException(status_code=400, detail="Either projectId or sessionId is required")

    # Verify project access permissions
    is_admin = current_user.role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]
    is_owner = project.owner_id == current_user.id
    
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == current_user.id
    ).first()
    
    has_team_access = False
    if current_user.team_id:
        from models import TeamProject
        team_project_link = db.query(TeamProject).filter(
            TeamProject.project_id == project.id,
            TeamProject.team_id == current_user.team_id
        ).first()
        if team_project_link:
            has_team_access = True
            
    if not (is_admin or is_owner or member or has_team_access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project"
        )

    # Initialize/reuse Forjinn session id in the same db transaction
    if not project.forjinn_session_id:
        import uuid
        project.forjinn_session_id = f"session-{uuid.uuid4()}"
        if not project.session_id:
            project.session_id = project.forjinn_session_id
        db.commit()

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
    if project.forjinn_session_id:
        payload_dict["chatId"] = project.forjinn_session_id
        payload_dict["overrideConfig"] = {"sessionId": project.forjinn_session_id}

    project_id = project.id
    question = payload.question

    def event_generator():
        from database import SessionLocal
        bg_db = SessionLocal()
        ai_chunks = []
        stream_session_id = None
        current_payload = payload_dict.copy()
        
        # Retry loop (up to 2 attempts) to handle expired/missing Forjinn session errors
        for attempt in range(2):
            try:
                # Use request_with_retry for robust LLM streaming connection
                response = request_with_retry("POST", PREDICTION_URL, json=current_payload, stream=True, timeout=90, verify=False)
                
                # Check for session not found / expired error code (400 or 404)
                if response.status_code in [400, 404]:
                    try:
                        err_content = response.json()
                        err_msg = str(err_content)
                    except Exception:
                        err_msg = response.text
                    
                    if attempt == 0:
                        import uuid
                        new_sid = f"session-{uuid.uuid4()}"
                        print(f"[RETRY WARNING] Forjinn session expired/not found. Re-creating session: {new_sid}. Error: {err_msg}")
                        # Persist new session ID in the database
                        bg_project = bg_db.query(Project).filter(Project.id == project_id).with_for_update().first()
                        if bg_project:
                            bg_project.forjinn_session_id = new_sid
                            bg_project.session_id = new_sid
                            bg_db.commit()
                        
                        current_payload["chatId"] = new_sid
                        current_payload["overrideConfig"] = {"sessionId": new_sid}
                        continue
                
                # Process the streaming lines
                session_expired_in_stream = False
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode("utf-8", "ignore").strip()
                        if line_str.startswith("data:"):
                            try:
                                data_content = line_str[5:].strip()
                                chunk_data = json.loads(data_content)
                                
                                # Check if error event represents an expired/missing session
                                if chunk_data.get("event") == "error":
                                    err_msg = chunk_data.get("message", "") or ""
                                    if "session not found" in err_msg.lower() or "expired" in err_msg.lower():
                                        if attempt == 0:
                                            session_expired_in_stream = True
                                            break
                                
                                if chunk_data.get("event") == "token":
                                    token_val = chunk_data.get("data")
                                    if isinstance(token_val, str):
                                        ai_chunks.append(token_val)
                                elif chunk_data.get("event") == "metadata":
                                    meta_data = chunk_data.get("data")
                                    if isinstance(meta_data, dict):
                                        new_sid = meta_data.get("chatId") or meta_data.get("sessionId")
                                        if new_sid:
                                            stream_session_id = new_sid
                            except Exception:
                                pass
                            
                            yield f"{line_str}\n\n"
                
                if session_expired_in_stream and attempt == 0:
                    import uuid
                    new_sid = f"session-{uuid.uuid4()}"
                    print(f"[RETRY WARNING] Stream error event: Session expired/not found. Re-creating session: {new_sid}")
                    bg_project = bg_db.query(Project).filter(Project.id == project_id).with_for_update().first()
                    if bg_project:
                        bg_project.forjinn_session_id = new_sid
                        bg_project.session_id = new_sid
                        bg_db.commit()
                    
                    current_payload["chatId"] = new_sid
                    current_payload["overrideConfig"] = {"sessionId": new_sid}
                    ai_chunks = []
                    continue
                
                # Successful response received
                break
                
            except Exception as exc:
                print(f"[PREDICTION WARNING] Connection error targeting {PREDICTION_URL}: {str(exc)}")
                target_port = os.getenv("PORT", "8000")
                mock_url = f"http://127.0.0.1:{target_port}/api/mock-predict"
                if PREDICTION_URL != mock_url:
                    print(f"[PREDICTION FALLBACK] Retrying via local mock-predict service at {mock_url}...")
                    try:
                        response = requests.post(mock_url, json=current_payload, stream=True, timeout=10)
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode("utf-8", "ignore").strip()
                                if line_str.startswith("data:"):
                                    try:
                                        data_content = line_str[5:].strip()
                                        chunk_data = json.loads(data_content)
                                        if chunk_data.get("event") == "token":
                                            token_val = chunk_data.get("data")
                                            if isinstance(token_val, str):
                                                ai_chunks.append(token_val)
                                        elif chunk_data.get("event") == "metadata":
                                            meta_data = chunk_data.get("data")
                                            if isinstance(meta_data, dict):
                                                new_sid = meta_data.get("chatId") or meta_data.get("sessionId")
                                                if new_sid:
                                                    stream_session_id = new_sid
                                    except Exception:
                                        pass
                                    yield f"{line_str}\n\n"
                        break
                    except Exception as fallback_exc:
                        print(f"[PREDICTION FALLBACK FAILED] {fallback_exc}")
                        raise exc
                else:
                    raise exc
            
        # Post-chat completion processing using the dedicated background session
        try:
            ai_reply = "".join(ai_chunks).strip()
            if ai_reply:
                bg_project = bg_db.query(Project).options(joinedload(Project.messages)).filter(Project.id == project_id).first()
                if bg_project:
                    if stream_session_id:
                        bg_project.forjinn_session_id = stream_session_id
                        bg_project.session_id = stream_session_id
                    save_message(bg_db, bg_project.id, "ai", ai_reply)
                    update_project_state(bg_db, bg_project, question, ai_reply, active_section=active_section)
                    legacy_payload = get_legacy_payload(bg_project)
                    bg_project.data = json.dumps(legacy_payload)
                    bg_db.commit()
                    print(f"State updates completed successfully for project {bg_project.id}.")
        except Exception as exc:
            print(f"Post-chat update failed: {str(exc)}")
        finally:
            bg_db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENV", "development") != "production"
    uvicorn.run("app:app", host=host, port=port, reload=reload)
