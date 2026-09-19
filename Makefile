.PHONY: start-backend start-frontend install-backend install-frontend

# Backend: FastAPI on http://localhost:8000 (future: https://api.xyz)
# --reload watches Python + .env so code and config changes pick up automatically
start-backend:
	cd backend && ../venv/bin/uvicorn app.main:app --reload \
		--reload-include '*.py' \
		--reload-include '.env' \
		--reload-include '../.env' \
		--host 0.0.0.0 --port 8000

# Frontend: React (Vite) on http://localhost:5173 (future: https://app.xyz)
# Vite HMR is enabled by default via npm run dev
start-frontend:
	cd frontend && npm run dev

install-backend:
	test -d venv || python3 -m venv venv
	./venv/bin/pip install -r backend/requirements.txt

install-frontend:
	cd frontend && npm install
