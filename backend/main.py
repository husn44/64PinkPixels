import uuid
import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from backend.config import settings
from backend.models import (
    SessionData,
    ExtractedItem,
    QuoteRecord,
    UploadResponse,
    ResearchRequest,
    ResearchResponse,
    AnalysisResponse,
    AcceptanceRequest,
    AcceptanceResponse,
)
from backend import database, pdf_parser, ai_service, search_service, po_generator

logger = logging.getLogger(__name__)

sessions: dict[str, SessionData] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.QUOTES_DIR.mkdir(parents=True, exist_ok=True)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Adversarial Procurement Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/config/check")
async def check_config():
    missing = settings.validate_required()
    return {"valid": len(missing) == 0, "missing": missing}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_pdfs(files: list[UploadFile] = File(...)):
    missing = settings.validate_required()
    if missing:
        raise HTTPException(400, f"Missing config: {', '.join(missing)}")

    session_id = str(uuid.uuid4())
    session = SessionData(session_id=session_id)
    filenames = []
    errors = []

    for upload in files:
        file_bytes = await upload.read()
        if not upload.filename:
            continue
        filenames.append(upload.filename)

        try:
            raw_text, text_hash = pdf_parser.parse_pdf_bytes(file_bytes, upload.filename)
        except Exception as e:
            logger.error(f"PDF parse error for {upload.filename}: {e}")
            errors.append(f"{upload.filename}: PDF parsing failed ({e})")
            continue

        try:
            extracted_items = await ai_service.extract_quote_data(raw_text, filename=upload.filename)
        except Exception as e:
            logger.error(f"AI extraction error for {upload.filename}: {e}")
            errors.append(f"{upload.filename}: AI extraction failed ({e})")
            continue

        for extracted in extracted_items:
            price_per_unit = extracted.item_price / max(extracted.normalized_quantity, 1)
            record = QuoteRecord(
                id=str(uuid.uuid4()),
                vendor_name=extracted.vendor_name,
                item_name=extracted.item_name,
                item_description=extracted.item_description,
                item_price=extracted.item_price,
                quantity=extracted.quantity,
                unit=extracted.unit,
                normalized_unit=extracted.normalized_unit,
                normalized_quantity=extracted.normalized_quantity,
                price_per_normalized_unit=round(price_per_unit, 4),
                delivery_days=extracted.delivery_days,
                payment_terms=extracted.payment_terms,
                hidden_fees=extracted.hidden_fees,
                warranty=extracted.warranty,
                contact_info=extracted.contact_info,
                timestamp=datetime.now(timezone.utc),
                raw_text_hash=text_hash,
            )

            try:
                await database.append_quote(record)
            except Exception as e:
                logger.error(f"Database save error for {upload.filename}: {e}")
                errors.append(f"{upload.filename}: database save failed ({e})")

            session.extracted_items.append(extracted)

    if not session.extracted_items and errors:
        raise HTTPException(500, f"All uploads failed: {'; '.join(errors)}")

    sessions[session_id] = session
    return UploadResponse(
        session_id=session_id,
        filenames=filenames,
        extracted_items=session.extracted_items,
    )


@app.post("/api/research", response_model=ResearchResponse)
async def run_research(request: ResearchRequest):
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    benchmarks, reputations = await search_service.research_all(
        session.extracted_items
    )
    session.market_benchmarks = benchmarks
    session.reputation_results = reputations
    return ResearchResponse(
        market_benchmarks=benchmarks,
        reputation_results=reputations,
    )


@app.post("/api/analyze", response_model=AnalysisResponse)
async def run_analysis(request: ResearchRequest):
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    try:
        item_names = list({item.item_name for item in session.extracted_items})
        # Query history once for all items instead of one-by-one
        all_history = await database.get_all_history()
        history_records = [r for r in all_history if any(
            name.lower() in r.item_name.lower() for name in item_names
        )]
        # Deduplicate by id
        seen = set()
        unique_history = []
        for r in history_records:
            if r.id not in seen:
                seen.add(r.id)
                unique_history.append(r)

        matrix = await ai_service.analyze_quotes_vs_research(
            extracted_items=session.extracted_items,
            benchmarks=session.market_benchmarks,
            reputations=session.reputation_results,
            history_records=unique_history,
        )
        session.competitive_matrix = matrix
        return AnalysisResponse(competitive_matrix=matrix)
    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        raise HTTPException(500, f"Analysis failed: {e}")


@app.post("/api/accept", response_model=AcceptanceResponse)
async def accept_vendor(request: AcceptanceRequest):
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.competitive_matrix:
        raise HTTPException(400, "Run analysis first")

    selected_items = []
    req_name = request.vendor_name.lower().strip()
    # Try exact match first
    for item in session.extracted_items:
        if item.vendor_name.lower().strip() == req_name:
            selected_items.append(item)
    # Fallback: check if either name contains the other (handles prefixes/suffixes)
    if not selected_items:
        for item in session.extracted_items:
            item_name = item.vendor_name.lower().strip()
            if item_name in req_name or req_name in item_name:
                selected_items.append(item)
    if not selected_items:
        raise HTTPException(404, f"Vendor '{request.vendor_name}' not found in session")

    email_text = await ai_service.draft_acceptance_email(
        vendor_name=request.vendor_name,
        extracted_items=selected_items,
        competitive_matrix=session.competitive_matrix,
    )

    po_path = po_generator.generate_po_pdf(
        vendor_name=request.vendor_name,
        extracted_items=selected_items,
    )

    session.acceptance_email = email_text
    session.po_pdf_path = po_path

    return AcceptanceResponse(email_text=email_text, po_pdf_path=po_path)


@app.get("/api/history")
async def get_history(item_name: str | None = None, vendor_name: str | None = None):
    records = await database.query_history(item_name=item_name, vendor_name=vendor_name)
    return [r.model_dump(mode="json") for r in records]


@app.delete("/api/history/{record_id}")
async def delete_history(record_id: str):
    deleted = await database.delete_quote(record_id)
    if not deleted:
        raise HTTPException(404, "Record not found")
    return {"deleted": True}


@app.get("/api/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    session = sessions.get(session_id)
    if not session or not session.po_pdf_path:
        raise HTTPException(404, "File not found")

    filepath = session.po_pdf_path
    if not os.path.exists(filepath):
        raise HTTPException(404, "PDF file not found on disk")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=os.path.basename(filepath),
    )
