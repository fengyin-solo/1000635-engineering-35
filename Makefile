.PHONY: install backend frontend check

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

check:
	cd backend && .venv/bin/python -m app.selfcheck
