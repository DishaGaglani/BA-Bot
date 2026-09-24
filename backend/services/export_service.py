"""Builds the exported requirements documents (DOCX / PDF).

Used by the background `export` job and by the legacy synchronous
GET /api/projects/{id}/export endpoint, so both produce identical files.
"""
import io
import json
import os
import sys

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project
from services.project_state_manager import get_structured_state
from utils.export import parse_markdown_to_pdf

PREDICTION_URL = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"


class UnsupportedFormat(ValueError):
    pass


def normalize_format(fmt: str) -> str:
    """Returns 'docx' or 'pdf'. 'word' is accepted as an alias for 'docx'."""
    value = (fmt or "").strip().lower()
    if value in ("docx", "word"):
        return "docx"
    if value == "pdf":
        return "pdf"
    raise UnsupportedFormat("Invalid format. Supported: docx, pdf")


def export_filename(project_name: str, fmt: str) -> str:
    slug = project_name.replace(" ", "_")
    if fmt == "docx":
        return f"{slug}_Requirement_Discovery_Form.docx"
    return f"{slug}_Requirements.pdf"


def media_type_for(fmt: str) -> str:
    return DOCX_MEDIA_TYPE if fmt == "docx" else PDF_MEDIA_TYPE


def generate_export(project: Project, fmt: str, *, allow_fallback: bool = True) -> tuple[io.BytesIO, str, str]:
    """Returns (file_stream, filename, media_type).

    With allow_fallback=True (the historical behaviour) an unreachable or empty LLM
    still yields a document, with missing sections rendered as [MISSING] or a raw
    state dump. With allow_fallback=False an LLM failure raises instead, so the job
    queue can retry it; the queue passes True only on the final attempt.
    """
    fmt = normalize_format(fmt)
    project_name = project.name
    state = get_structured_state(project)

    if fmt == "docx":
        from services.fdr_summary import generate_fdr_json
        from utils.fdr_docx import build_fdr_docx

        fdr_data = generate_fdr_json(project, raise_on_error=not allow_fallback)
        if not fdr_data.get("project_name"):
            fdr_data["project_name"] = project_name
        return build_fdr_docx(fdr_data), export_filename(project_name, fmt), DOCX_MEDIA_TYPE

    prompt = (
        f"The requirements interview discovery workshop is complete for project '{project_name}'.\n\n"
        "Here is the final gathered Project Requirements State gathered during the interview:\n"
        f"{json.dumps(state, indent=2)}\n\n"
        "Please generate and compile the final, detailed, and polished Requirements Discovery Document (FDR) "
        "containing all project information, overview, stakeholders, business problem, business goals, timeline, functional requirements, and constraints. "
        "Format the output using clear Markdown headings, bullet points, and numbered lists."
    )
    payload = {"question": prompt, "streaming": False}

    try:
        from utils.prod_ready import request_with_retry
        response = request_with_retry("POST", PREDICTION_URL, json=payload, timeout=30, verify=False)
        res_data = response.json()

        document_text = res_data.get("text")
        if not document_text:
            output_obj = res_data.get("output")
            if isinstance(output_obj, dict):
                document_text = output_obj.get("content", "")
            elif isinstance(output_obj, str):
                document_text = output_obj
            else:
                document_text = ""
        if not document_text and not allow_fallback:
            raise RuntimeError("LLM returned an empty document")
    except Exception as e:
        if not allow_fallback:
            raise
        print(f"[EXPORT WARNING] Failed to connect to {PREDICTION_URL}: {str(e)}. Falling back to local generation...")
        target_port = os.getenv("PORT", "8000")
        mock_url = f"http://127.0.0.1:{target_port}/api/mock-predict"
        try:
            res_mock = requests.post(mock_url, json=payload, timeout=10)
            mock_data = res_mock.json()
            document_text = mock_data.get("text")
        except Exception:
            document_text = None

        if not document_text:
            document_text = f"# Final Discovery Requirements (FDR)\n\n## Project: {project_name}\n\n### Requirements Overview\n" + json.dumps(state, indent=2)

    return parse_markdown_to_pdf(document_text), export_filename(project_name, fmt), PDF_MEDIA_TYPE
