PY ?= python3
.PHONY: demo data pipeline select report panels clean api static-demo test erp-demo catalogue verify

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

tulya:						## the TULYA console: reports/tulya_console.html
	python3 tulya/build.py

static-demo:                               ## a shareable, no-server copy: reports/steward_console_demo.html
	$(PY) api/export_static_demo.py

test:                                      ## the whole suite; make test T=erp for one module
	$(PY) tests/run_all.py $(T)

erp-demo:                                  ## SAP extract -> match -> approve -> national codes -> write-back
	$(PY) erp/run_roundtrip.py --cpse $(or $(CPSE),IOCL) --limit $(or $(LIMIT),3000) --fresh

catalogue:                                 ## export the national catalogue a CPSE receives
	$(PY) erp/export_catalogue.py

verify:                                    ## re-run the locked holdout and prove it still reproduces
	$(PY) eval/verify.py

clean:
	rm -f data/out/* RESULTS.md reports/*.png
	rm -rf data/erp/*/ data/erp/outbound
