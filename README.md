# ProcureIQ: AI-Powered Vendor and Procurement Agent

## Pitching Video

[Watch our pitching video here](https://drive.google.com/file/d/1outZDbIjyPA2_UGMa_Mpi4hLLDEILFoP/view?usp=drivesdk) 

## Document (PRD,QATD,SAD)

Can be found in the `docs/` folder.

---

## Overview

An AI-powered procurement assistant that helps organizations make smarter, more cost-effective purchasing decisions. Upload vendor quote PDFs, and the system will automatically extract, normalize, research, and adversarially analyze every quote to find reason not to choose each vendor before recommending the best deal.

Built with **GLM on Z AI (ilmu-glm-5.1)** as the core AI engine for data extraction, competitive analysis, market price estimation, vendor reputation assessment, and acceptance email drafting.

---

## Features

- **Smart PDF Extraction** — Upload vendor quote PDFs and AI automatically extracts item details, prices, quantities, delivery terms, hidden fees, and warranty info
- **Unit Normalization** — Automatically normalizes units (ml to L, cm to m, g to kg) for fair comparison across vendors
- **Market Price Research** — Searches Shopee, Lazada, and the web for Malaysian market prices, with GLM fallback estimation
- **Vendor Reputation Check** — Scrapes reviews and complaints, with GLM knowledge-based assessment as fallback
- **Adversarial Analysis** — AI-powered competitive matrix that scores each vendor on price, risk, hidden fees, delivery, and reputation
- **Deal Closing** — One-click vendor acceptance with auto-generated professional email and Purchase Order PDF
- **Price History** — Tracks all past quotes in a cloud database (JSONBin) for historical price comparison

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit |
| Backend | FastAPI + Uvicorn |
| AI Engine | GLM on Z AI (ilmu-glm-5.1) |
| Database | JSONBin.io (cloud JSON storage) |
| PDF Parsing | pdfplumber |
| PDF Generation | ReportLab |
| Web Scraping | DuckDuckGo + BeautifulSoup4 |

---

## How GLM on Z AI is Used

GLM is the critical AI component powering every intelligent function in the system:

1. **Quote Data Extraction** — Parses unstructured PDF text into structured vendor/item data with normalized units
2. **Market Price Estimation** — Estimates Malaysian market prices when web search results are insufficient
3. **Vendor Reputation Assessment** — Identifies red flags and positive notes from search results or its own knowledge
4. **Adversarial Competitive Analysis** — Compares all vendors against market benchmarks, historical prices, and reputation data to produce scores and a winner recommendation
5. **Acceptance Email Drafting** — Generates professional procurement acceptance emails with all item details

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/husn44/64PinkPixels.git
cd ProcureIQ
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

The `.env` file is not included with API keys for security purposes.

Put your own keys, edit `.env`:

```
JSONBIN_API_KEY=your_jsonbin_api_key
JSONBIN_BIN_ID=
GLM_API_KEY=your_glm_api_key
GLM_BASE_URL=https://api.ilmu.ai/v1
GLM_MODEL_NAME=ilmu-glm-5.1
```

- **JSONBin API Key**: Get one at [jsonbin.io](https://jsonbin.io)
- **GLM API Key**: Provided by Z AI platform

### 4. Run the Application

```bash
python run.py
```

This starts both servers:
- **Frontend**: http://localhost:8501
- **Backend**: http://localhost:8000/docs

> **Sample Quotes**: Sample vendor quote PDFs can be found in the `sample_quotes/` folder.

---

## How to Use

### Step 1: Upload Vendor Quotes
Upload one or more PDF quote files from different vendors. The AI will extract and normalize all line items.

### Step 2: Review Extracted Data
Review the extracted items — vendor name, price, quantity, normalized unit, unit price, delivery, and payment terms. Check confidence scores and hidden fee alerts.

### Step 3: Adversarial Research
The system searches Shopee, Lazada, and the web for market prices and vendor reputations. GLM provides estimates when search data is unavailable.

### Step 4: Competitive Matrix
AI generates an adversarial analysis scoring each vendor on:
- Price vs Market / Price vs History
- Hidden Fee Detection
- Reputation Risk
- Delivery Risk
- Overall Score (0-10)

A winner is recommended with justification.

### Step 5: Close the Deal
Select a vendor to auto-generate:
- Professional acceptance email (editable)
- Purchase Order PDF with line items, tax, and terms

---

## Project Structure

```
ProcureIQ/
├── run.py                  # Entry point — starts both servers
├── requirements.txt        # Python dependencies
├── .env                    # API keys (included for judging)
├── backend/
│   ├── main.py             # FastAPI endpoints
│   ├── config.py           # Settings & env variables
│   ├── models.py           # Pydantic data models
│   ├── ai_service.py       # GLM AI integration
│   ├── database.py         # JSONBin cloud database
│   ├── pdf_parser.py       # PDF text extraction
│   ├── search_service.py   # Web scraping & research
│   └── po_generator.py     # Purchase Order PDF generation
├── frontend/
│   └── app.py              # Streamlit UI
├── sample_quotes/          # Sample vendor quote PDFs for testing
└── data/                   # Generated PO files (auto-created)
```

---

## Team

**No.64 pink pixels**

---

## License

This project is developed for the  UMHackathon competition.
