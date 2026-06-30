.PHONY: app smoke scan scan-heart-rate scan-polar heart-rate check

PYTHON ?= python3
SCAN_TIMEOUT ?= 8
HEART_RATE_SCAN_TIMEOUT ?= 10
HEART_RATE_DURATION ?= 30
HEART_RATE_NAME ?= Polar

app:
	$(PYTHON) src/main.py

smoke:
	$(PYTHON) qt_smoke_test.py

scan:
	$(PYTHON) src/scan.py --timeout $(SCAN_TIMEOUT)

scan-heart-rate:
	$(PYTHON) src/scan.py --timeout $(SCAN_TIMEOUT) --heart-rate-only

scan-polar:
	$(PYTHON) src/scan.py --timeout $(SCAN_TIMEOUT) --name "$(HEART_RATE_NAME)"

heart-rate:
	$(PYTHON) src/heart_rate.py --name "$(HEART_RATE_NAME)" --scan-timeout $(HEART_RATE_SCAN_TIMEOUT) --duration $(HEART_RATE_DURATION)

check:
	$(PYTHON) -m py_compile qt_smoke_test.py src/main.py src/client.py src/scan.py src/heart_rate.py
