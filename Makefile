.PHONY: help install install-backend install-frontend run run-backend run-frontend test test-backend test-frontend clean docker-build docker-run docker-stop

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install Python backend dependencies
	@echo "Installing Python dependencies..."
	python -m venv venv
	. venv/bin/activate && pip install -r requirements.txt

install-frontend: ## Install Node.js frontend dependencies
	@echo "Installing Node.js dependencies..."
	cd UI && npm install

run: run-backend run-frontend ## Run both backend and frontend

run-backend: ## Run FastAPI backend server
	@echo "Starting FastAPI backend..."
	cd server && uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-frontend: ## Run React frontend development server
	@echo "Starting React frontend..."
	cd UI && npm run dev

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	@echo "Running backend tests..."
	cd server && python -m pytest

test-frontend: ## Run frontend tests
	@echo "Running frontend tests..."
	cd UI && npm test

clean: ## Clean up generated files
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf UI/dist UI/build UI/.vite
	rm -rf server/data server/chroma_db

docker-build: ## Build Docker images
	@echo "Building Docker images..."
	docker-compose build

docker-run: ## Run application with Docker
	@echo "Starting application with Docker..."
	docker-compose up -d

docker-stop: ## Stop Docker containers
	@echo "Stopping Docker containers..."
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f

setup: install ## Setup the entire project
	@echo "Setting up Analyst Helper..."
	@echo "1. Copy env.example to .env and configure your OpenAI API key"
	@echo "2. Run 'make run-backend' to start the backend"
	@echo "3. Run 'make run-frontend' to start the frontend"
	@echo "4. Open http://localhost:5173 in your browser" 