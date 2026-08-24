.PHONY: dev test cov lint format migrate logs logs-tunnel backup status restart push install-dev

PYTHON = .venv/bin/python
PIP    = .venv/bin/pip

dev:
	ENHANCE_MOCK=1 TEST_ENDPOINT_ENABLED=1 $(PYTHON) flask_ingress.py

test:
	$(PYTHON) -m pytest tests/ -v

cov:
	$(PYTHON) -m pytest tests/ --cov=app --cov-report=html --cov-fail-under=80
	@echo "Coverage report: htmlcov/index.html"

lint:
	$(PYTHON) -m ruff check app/ tests/
	$(PYTHON) -m mypy app/ --ignore-missing-imports

format:
	$(PYTHON) -m ruff format app/ tests/

migrate:
	VAULT_ROOT=$$(sudo grep "^VAULT_ROOT=" /etc/pensieve.env 2>/dev/null | cut -d= -f2-) $(PYTHON) -m app.migrate

logs:
	sudo journalctl -fu pensieve-flask

logs-tunnel:
	sudo journalctl -fu pensieve-tunnel

backup:
	deploy/backup.sh

status:
	@systemctl is-active pensieve-flask pensieve-tunnel 2>/dev/null || true
	@sudo journalctl -u pensieve-flask -n 5 --no-pager 2>/dev/null || true

restart:
	sudo systemctl restart pensieve-flask pensieve-tunnel

push:
	git add -A && git commit -m "chore: update" && git push

install-dev:
	$(PIP) install -r requirements.txt -r requirements-dev.txt -q