.PHONY: install backend frontend selfcheck

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

selfcheck:
	cd backend && .venv/bin/python -m app.selfcheck
