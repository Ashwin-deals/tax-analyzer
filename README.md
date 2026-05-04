# Bank Statement GST & TDS Classifier

A modular Python tool that reads a bank statement `.xlsx` file and automatically classifies every transaction as **GST**, **TDS**, or **NORMAL**, then exports separate Excel files for each category.

---

## Project Structure

```
tax-analyzer/
├── data/
│   ├── input/              ← place your bank_statement.xlsx here
│   └── output/             ← generated files land here
├── scripts/
│   └── generate_sample_data.py   ← create test data
├── src/
│   ├── __init__.py
│   ├── main.py             ← CLI entry point
│   ├── loader.py           ← Excel loading + header detection
│   ├── classifier.py       ← keyword-based classification logic
│   ├── processor.py        ← orchestrates classify + split
│   └── exporter.py         ← writes formatted Excel output
├── utils/
│   ├── __init__.py
│   ├── constants.py        ← all keywords and config
│   └── helpers.py          ← shared utility functions
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Generate sample data (optional)
```bash
python scripts/generate_sample_data.py
```

### 3. Run the classifier
```bash
# Using the default path  (data/input/bank_statement.xlsx)
python -m src.main

# Custom file path
python -m src.main path/to/my_statement.xlsx

# Custom output directory
python -m src.main --output-dir results/

# Verbose / debug mode
python -m src.main -v

# Skip summary sheet
python -m src.main --no-summary
```

---

## Output Files

| File | Contents |
|------|----------|
| `gst_transactions.xlsx` | All GST / merchant transactions |
| `tds_transactions.xlsx` | All TDS / income-tax transactions |
| `normal_transactions.xlsx` | All unclassified transactions |
| `classification_summary.xlsx` | Count + total amounts per category |

All files include colour-coded headers:  
🟠 Amber = TDS &nbsp; 🟢 Green = GST &nbsp; 🔵 Blue = NORMAL

---

## Classification Logic

Priority order: **TDS > GST > NORMAL**

### TDS Keywords
`tds`, `tax deducted`, `income tax`, `it refund`, section codes `192`–`206`, `tcs`, …

### GST Keywords
`gst`, `cgst`, `sgst`, `igst`, `utgst`, `invoice`, `service tax`, `gst challan`, …

### Merchant / POS (→ GST)
`card pmt`, `pos`, `cms_`, `swiggy`, `zomato`, `amazon`, `flipkart`, `razorpay`, …

---

## Extending the Tool

### Add new keywords
Edit `utils/constants.py` — append to `TDS_KEYWORDS`, `GST_KEYWORDS`, or `MERCHANT_KEYWORDS`.

### Support a new bank format
The loader automatically detects the header row. If your bank uses a non-standard column name for the narration, add it to `DESCRIPTION_COLUMN_CANDIDATES` in `constants.py`.

### Add ML-based classification
Replace or augment `classify_transaction()` in `src/classifier.py` with a model call — the rest of the pipeline stays unchanged.

---

## Requirements

- Python 3.10+
- pandas ≥ 2.0
- openpyxl ≥ 3.1
