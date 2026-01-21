.PHONY: dev test lint install clean

# Hot reload development server
dev:
	flask run --debug --port 5000

# Run tests
test:
	pytest -v

# Lint code
lint:
	ruff check .
	ruff format --check .

# Format code
format:
	ruff format .

# Install dependencies
install:
	pip install -r requirements.txt

# Clean cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
