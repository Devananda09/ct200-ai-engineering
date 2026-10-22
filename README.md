# CT-200 AI Engineering Assignment

A FastAPI-based document ingestion and retrieval system for versioned CT-200 Home Blood Pressure Monitor manuals.

## Features

- PDF text extraction with PyMuPDF
- Section and subsection hierarchy reconstruction
- Versioned manual ingestion (v1 and v2)
- SHA-256 content hashing
- v1 → v2 change detection
- Section/node browsing APIs
- Keyword-based document search
- Version-pinned node selection
- Test-idea generation from selected manual content
- Docker support
- Automated tests with pytest

## Project Structure

```text
ct200-ai-engineering/
├── app/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   └── services/
├── parser/
│   ├── models.py
│   ├── pdf_parser.py
│   └── hierarchy.py
├── data/
│   ├── ct200_manual.pdf
│   └── ct200_manual_v2.pdf
├── scripts/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example

