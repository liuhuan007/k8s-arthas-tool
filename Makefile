.PHONY: install test lint run docker docker-run loadtest

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --tb=short

lint:
	flake8 --max-line-length=120 --ignore=E501,W503,E402,W504 .

run:
	python server.py

docker:
	docker build -t arthas-k8s-tool:latest .

docker-run:
	docker run -d --name arthas-tool -p 5001:5001 \
		-v ~/.kube:/root/.kube:ro \
		-v $(CURDIR)/profiler_output:/app/profiler_output \
		arthas-k8s-tool:latest

loadtest:
	locust -f tests/load/locustfile.py --config tests/load/locust.conf
