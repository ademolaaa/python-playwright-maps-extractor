# Python Playwright Business & Maps Extractor

Structured asynchronous data extraction pipeline built with **Python**, **Playwright**, **phonenumbers**, and **Pandas**.

## Features
- Async Playwright scrolling and card extraction across regional business queries
- Automatic E.164 phone number validation and formatting
- Domain sanitization and Pandas multi-key deduplication (`Business Name` + `Address` + `Phone`)
- Clean RFC-4180 `.csv` and `.xlsx` export ready for CRM ingestion

## Usage
```bash
pip install -r requirements.txt
playwright install chromium
python extractor.py --query "Commercial Contractors" --location "New York, NY" --limit 100 --out leads.csv
```
