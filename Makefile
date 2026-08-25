.PHONY: run test lint format typecheck check clean api-local ui-local

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

# ── Tu host qua Cloudflare Tunnel — xem docs/self-host-cloudflare.md ──
# Hai lenh nay chay o HAI terminal khac nhau, `api-local` truoc.
#
# Backend chay THANG tren may, khong bo vao container: endpoint
# /api/incidents/{key}/logs goi `docker logs`, nam trong container thi phai
# mount docker.sock vao moi thay duoc stack demo.
api-local:
	CORS_ORIGINS=https://035.emmetech.id.vn,http://localhost:8501 uvicorn src.main:app --host 127.0.0.1 --port 8000

# Phai dung o goc repo, khong phai trong ui/ — Streamlit doc .streamlit/config.toml
# theo thu muc dang dung.
#
# JIRA_BASE_URL phai truyen TAY: tien trinh Streamlit KHONG doc .env (chi backend
# doc, qua pydantic-settings). Thieu no thi war room hien nut xam
# "Chua dat JIRA_BASE_URL" thay vi nut mo phieu Jira.
ui-local:
	API_URL=http://localhost:8000 PROM_URL=http://localhost:9090 API_PUBLIC_URL=https://api-035.emmetech.id.vn PROM_PUBLIC_URL=https://prom-035.emmetech.id.vn JIRA_BASE_URL=https://jibinarybro.atlassian.net streamlit run ui/status_page.py

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
