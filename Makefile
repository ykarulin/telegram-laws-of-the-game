.PHONY: help install test test-cov run run-dev run-testing run-prod docker-build docker-up docker-down clean sync-documents list-documents reset-embeddings reset-embeddings-dev reset-embeddings-testing reset-embeddings-prod

help:
	@echo "Football Rules Expert Bot - Available commands:"
	@echo ""
	@echo "Setup & Testing:"
	@echo "  make install        - Install dependencies in venv"
	@echo "  make test           - Run tests"
	@echo "  make test-cov       - Run tests with coverage report"
	@echo ""
	@echo "Local Run (using ENVIRONMENT env var):"
	@echo "  make run            - Run bot (uses .env.development by default)"
	@echo "  make run-dev        - Run bot in development mode"
	@echo "  make run-testing    - Run bot in testing mode"
	@echo "  make run-prod       - Run bot in production mode"
	@echo ""
	@echo "Document Management:"
	@echo "  make sync-documents              - Upload & index documents (dev environment)"
	@echo "  make sync-documents-dev          - Upload & index documents (development)"
	@echo "  make sync-documents-testing      - Upload & index documents (testing)"
	@echo "  make sync-documents-prod         - Upload & index documents (production)"
	@echo "  make list-documents              - List all indexed documents (dev environment)"
	@echo "  make list-documents-dev          - List all indexed documents (development)"
	@echo "  make list-documents-testing      - List all indexed documents (testing)"
	@echo "  make list-documents-prod         - List all indexed documents (production)"
	@echo ""
	@echo "Database Reset & Re-embedding:"
	@echo "  make reset-embeddings            - Clean DB & move indexed→upload, then re-sync (dev)"
	@echo "  make reset-embeddings-dev        - Clean DB & re-sync embeddings (development)"
	@echo "  make reset-embeddings-testing    - Clean DB & re-sync embeddings (testing)"
	@echo "  make reset-embeddings-prod       - Clean DB & re-sync embeddings (production)"
	@echo "  ** WARNING: This deletes all document records and embeddings! **"
	@echo ""
	@echo "Docker Services (PostgreSQL + Qdrant):"
	@echo "  make docker-up      - Start services in background"
	@echo "  make docker-down    - Stop services (data persists)"
	@echo "  make docker-logs    - View all service logs (live)"
	@echo "  make docker-logs-qdrant   - View Qdrant logs only"
	@echo "  make docker-logs-postgres - View PostgreSQL logs only"
	@echo ""
	@echo "Other:"
	@echo "  make clean          - Remove generated files and caches"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make docker-up              # Start services once"
	@echo "  2. make run-dev                # Run bot (in another terminal)"
	@echo "  3. <Ctrl+C>                    # Stop bot"
	@echo "  4. make docker-down            # Stop services"
	@echo ""
	@echo "Document Workflow:"
	@echo "  1. Place PDF/TXT/MD in knowledgebase/upload/"
	@echo "  2. make sync-documents         # Auto-upload & index"
	@echo "  3. Chat with bot on Telegram   # Bot uses indexed documents"

install:
	python3 -m venv venv
	bash -c 'source venv/bin/activate && pip install -r requirements.txt'

test:
	bash -c 'source venv/bin/activate && python -m pytest tests/ -v'

test-cov:
	bash -c 'source venv/bin/activate && python -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing'

run:
	bash -c 'source venv/bin/activate && ENVIRONMENT=development python -m src.main'

run-dev:
	bash -c 'source venv/bin/activate && ENVIRONMENT=development python -m src.main'

run-testing:
	bash -c 'source venv/bin/activate && ENVIRONMENT=testing python -m src.main'

run-prod:
	bash -c 'source venv/bin/activate && ENVIRONMENT=production python -m src.main'

docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "Services started: PostgreSQL and Qdrant"
	@echo "Verify: curl http://localhost:6333/health"

docker-down:
	docker compose down
	@echo "Services stopped. Data persists in Docker volumes."

docker-logs:
	docker compose logs -f

docker-logs-qdrant:
	docker compose logs -f qdrant

docker-logs-postgres:
	docker compose logs -f postgres

sync-documents:
	bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -m src.cli.document_sync'

sync-documents-dev:
	bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -m src.cli.document_sync'

sync-documents-testing:
	bash -c 'source venv/bin/activate && set -a && source .env.testing && set +a && python -m src.cli.document_sync'

sync-documents-prod:
	bash -c 'source venv/bin/activate && set -a && source .env.production && set +a && python -m src.cli.document_sync'

list-documents:
	bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -m src.cli list'

list-documents-dev:
	bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -m src.cli list'

list-documents-testing:
	bash -c 'source venv/bin/activate && set -a && source .env.testing && set +a && python -m src.cli list'

list-documents-prod:
	bash -c 'source venv/bin/activate && set -a && source .env.production && set +a && python -m src.cli list'

clean:
	rm -rf venv .pytest_cache htmlcov .coverage __pycache__ tests/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

reset-embeddings: reset-embeddings-dev

reset-embeddings-dev:
	@echo "⚠️  WARNING: This will delete ALL document records and embeddings from development environment!"
	@echo "This will:"
	@echo "  1. Delete all documents from PostgreSQL (development database)"
	@echo "  2. Clear all embeddings from Qdrant"
	@echo "  3. Move all files from knowledgebase/indexed → knowledgebase/upload"
	@echo "  4. Reset sync state file"
	@echo "  5. Re-run document sync to re-embed with new model"
	@echo ""
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -c "from src.cli.document_commands import DocumentCLI; from src.config import Config; cli = DocumentCLI(Config.from_env()); cli.delete_all_documents(force=True); cli.close()"'; \
		find knowledgebase/indexed -type f -not -name ".DS_Store" -not -name ".gitkeep" | xargs -I {} mv {} knowledgebase/upload/ 2>/dev/null || echo "No indexed files to move"; \
		rm -f knowledgebase/.sync_state.development.json; \
		echo "✅ Databases cleared and files moved."; \
		echo "🔄 Re-syncing documents with new embeddings..."; \
		bash -c 'source venv/bin/activate && set -a && source .env.development && set +a && python -m src.cli.document_sync'; \
		echo "✅ Re-embedding complete!"; \
	else \
		echo "❌ Cancelled."; \
	fi

reset-embeddings-testing:
	@echo "⚠️  WARNING: This will delete ALL document records and embeddings from testing environment!"
	@echo "This will:"
	@echo "  1. Delete all documents from PostgreSQL (testing database)"
	@echo "  2. Clear all embeddings from Qdrant"
	@echo "  3. Move all files from knowledgebase/indexed → knowledgebase/upload"
	@echo "  4. Reset sync state file"
	@echo "  5. Re-run document sync to re-embed with new model"
	@echo ""
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		bash -c 'source venv/bin/activate && set -a && source .env.testing && set +a && python -c "from src.cli.document_commands import DocumentCLI; from src.config import Config; cli = DocumentCLI(Config.from_env()); cli.delete_all_documents(force=True); cli.close()"'; \
		find knowledgebase/indexed -type f -not -name ".DS_Store" -not -name ".gitkeep" | xargs -I {} mv {} knowledgebase/upload/ 2>/dev/null || echo "No indexed files to move"; \
		rm -f knowledgebase/.sync_state.testing.json; \
		echo "✅ Databases cleared and files moved."; \
		echo "🔄 Re-syncing documents with new embeddings..."; \
		bash -c 'source venv/bin/activate && set -a && source .env.testing && set +a && python -m src.cli.document_sync'; \
		echo "✅ Re-embedding complete!"; \
	else \
		echo "❌ Cancelled."; \
	fi

reset-embeddings-prod:
	@echo "⚠️  WARNING: This will delete ALL document records and embeddings from PRODUCTION environment!"
	@echo "This will:"
	@echo "  1. Delete all documents from PostgreSQL (production database)"
	@echo "  2. Clear all embeddings from Qdrant"
	@echo "  3. Move all files from knowledgebase/indexed → knowledgebase/upload"
	@echo "  4. Reset sync state file"
	@echo "  5. Re-run document sync to re-embed with new model"
	@echo ""
	@read -p "Type 'yes-prod' to confirm for PRODUCTION: " confirm; \
	if [ "$$confirm" = "yes-prod" ]; then \
		bash -c 'source venv/bin/activate && set -a && source .env.production && set +a && python -c "from src.cli.document_commands import DocumentCLI; from src.config import Config; cli = DocumentCLI(Config.from_env()); cli.delete_all_documents(force=True); cli.close()"'; \
		find knowledgebase/indexed -type f -not -name ".DS_Store" -not -name ".gitkeep" | xargs -I {} mv {} knowledgebase/upload/ 2>/dev/null || echo "No indexed files to move"; \
		rm -f knowledgebase/.sync_state.production.json; \
		echo "✅ Databases cleared and files moved."; \
		echo "🔄 Re-syncing documents with new embeddings..."; \
		bash -c 'source venv/bin/activate && set -a && source .env.production && set +a && python -m src.cli.document_sync'; \
		echo "✅ Re-embedding complete!"; \
	else \
		echo "❌ Cancelled."; \
	fi
