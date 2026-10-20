.PHONY: test lint bench assets

test:
	python3 -m unittest discover -s tests -v

lint:
	python3 -m compileall -q hermes_cache_engine scripts tests

bench:
	python3 scripts/cee_bench.py --days 7

assets:
	python3 scripts/make_assets.py docs/measured-100d.json
