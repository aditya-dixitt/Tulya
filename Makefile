PY ?= python3
.PHONY: demo data pipeline select report panels clean api static-demo

demo: data pipeline select report          ## full reproduce, start to finish

data:
	$(PY) data/generate.py

pipeline:
	$(PY) engine/pipeline.py --split dev
	$(PY) engine/pipeline.py --split val
	$(PY) engine/pipeline.py --split test

select:
	$(PY) eval/select.py

report:
	$(PY) eval/report.py

panels:
	$(PY) demo.py panels

search:
	$(PY) demo.py search "$(Q)"

api:                                       ## steward review console at http://localhost:8000
	$(PY) api/app.py

static-demo:                               ## a shareable, no-server copy: reports/steward_console_demo.html
	$(PY) api/export_static_demo.py

clean:
	rm -f data/out/* RESULTS.md reports/*.png
