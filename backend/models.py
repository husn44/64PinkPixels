from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ExtractedItem(BaseModel):
    vendor_name: str
    item_name: str
    filename: str = ""
    item_description: str = ""
    item_price: float
    quantity: float = 1.0
    unit: str
    normalized_unit: str
    normalized_quantity: float
    delivery_days: Optional[int] = None
    payment_terms: str = ""
    hidden_fees: list[str] = Field(default_factory=list)
    warranty: str = ""
    contact_info: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class QuoteRecord(BaseModel):
    id: str
    vendor_name: str
    item_name: str
    item_description: str
    item_price: float
    quantity: float
    unit: str
    normalized_unit: str
    normalized_quantity: float
    price_per_normalized_unit: float
    delivery_days: Optional[int] = None
    payment_terms: str
    hidden_fees: list[str]
    warranty: str
    contact_info: str
    timestamp: datetime
    raw_text_hash: str


class MarketBenchmark(BaseModel):
    item_name: str
    market_price_low: Optional[float] = None
    market_price_high: Optional[float] = None
    market_price_avg: Optional[float] = None
    source_snippets: list[str] = Field(default_factory=list)


class ReputationResult(BaseModel):
    vendor_name: str
    red_flags: list[str] = Field(default_factory=list)
    positive_notes: list[str] = Field(default_factory=list)
    source_snippets: list[str] = Field(default_factory=list)


class VendorAnalysis(BaseModel):
    vendor_name: str
    price_vs_market: str
    price_vs_history: str
    hidden_fee_alert: bool
    reputation_risk: str
    delivery_risk: str
    overall_score: float = Field(ge=0.0, le=10.0)
    summary: str


class CompetitiveMatrix(BaseModel):
    items_compared: list[str]
    vendors: list[str]
    analyses: list[VendorAnalysis]
    winner: str
    winner_justification: str


class SessionData(BaseModel):
    session_id: str
    extracted_items: list[ExtractedItem] = Field(default_factory=list)
    market_benchmarks: list[MarketBenchmark] = Field(default_factory=list)
    reputation_results: list[ReputationResult] = Field(default_factory=list)
    competitive_matrix: Optional[CompetitiveMatrix] = None
    acceptance_email: Optional[str] = None
    po_pdf_path: Optional[str] = None


class UploadResponse(BaseModel):
    session_id: str
    filenames: list[str]
    extracted_items: list[ExtractedItem]


class ResearchRequest(BaseModel):
    session_id: str


class ResearchResponse(BaseModel):
    market_benchmarks: list[MarketBenchmark]
    reputation_results: list[ReputationResult]


class AnalysisResponse(BaseModel):
    competitive_matrix: CompetitiveMatrix


class AcceptanceRequest(BaseModel):
    session_id: str
    vendor_name: str


class AcceptanceResponse(BaseModel):
    email_text: str
    po_pdf_path: str
