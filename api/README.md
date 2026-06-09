# spec-diff API

FastAPI backend for the spec-diff web interface.

## Running

```bash
# Development
uvicorn api.main:app --reload

# Production
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## Endpoints

### POST /compare

Upload two PDFs to start comparison.

```bash
curl -X POST "http://localhost:8000/compare" \
  -F "old_pdf=@old_version.pdf" \
  -F "new_pdf=@new_version.pdf"
```

Response:
```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Comparison started"
}
```

### GET /jobs/{job_id}

Check job status and progress.

```bash
curl "http://localhost:8000/jobs/{job_id}"
```

Response:
```json
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 0.5,
  "old_filename": "old.pdf",
  "new_filename": "new.pdf"
}
```

Status values: `queued`, `processing`, `complete`, `failed`

### GET /result/{job_id}

Get complete comparison result as JSON.

```bash
curl "http://localhost:8000/result/{job_id}"
```

### GET /export/{job_id}?format=html

Download report in specified format.

```bash
# HTML redline
curl "http://localhost:8000/export/{job_id}?format=html" -o report.html

# Word document
curl "http://localhost:8000/export/{job_id}?format=docx" -o report.docx

# JSON
curl "http://localhost:8000/export/{job_id}?format=json" -o report.json
```

### GET /health

Health check.

```bash
curl "http://localhost:8000/health"
```

## Configuration

Set in `config.toml`:

```toml
[api]
max_file_size = 104857600  # 100 MB
job_retention = 86400  # 24 hours
cors_origins = ["http://localhost:5173", "http://localhost:3000"]
```

## Security

- Binds to localhost only (127.0.0.1)
- CORS restricted to localhost origins
- File size limits enforced
- No external network calls from comparison engine
- Temporary files cleaned after job retention period

## Testing

```bash
pytest tests/test_api.py
```
