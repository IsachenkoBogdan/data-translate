.PHONY: help test config-show translate evaluate reformat inspect-source benchmark-judge \
	translate-airdialog translate-faithdial translate-weblinx \
	evaluate-airdialog evaluate-faithdial evaluate-weblinx \
	inspect-globalwoz reformat-globalwoz evaluate-globalwoz benchmark-judge-default

UV ?= uv
CLI := $(UV) run data-translate
CONFIG_ROOT ?= conf
DATASET ?=
RUN ?=
WORKFLOW ?=
SET ?=

dataset_arg = $(if $(strip $(DATASET)),--dataset $(DATASET),)
run_arg = $(if $(strip $(RUN)),--run $(RUN),)
set_args = $(foreach item,$(SET),--set $(item))

help:
	@printf '%s\n' \
	'Common targets:' \
	'  make test' \
	'  make translate DATASET=faithdial' \
	'  make evaluate DATASET=faithdial' \
	'  make inspect-source DATASET=globalwoz RUN=ff' \
	'  make reformat DATASET=globalwoz RUN=ff' \
	'  make benchmark-judge RUN=translation_judge' \
	'' \
	'Shortcuts:' \
	'  make translate-airdialog' \
	'  make translate-faithdial' \
	'  make translate-weblinx' \
	'  make inspect-globalwoz' \
	'  make reformat-globalwoz' \
	'' \
	'Optional variables:' \
	'  DATASET=<dataset_id>' \
	'  RUN=<run_preset>' \
	'  SET="runtime.concurrency=8 evaluation.seed=7"' \
	'  CONFIG_ROOT=conf'

test:
	$(UV) run pytest -q

config-show:
	@test -n "$(WORKFLOW)" || (echo "WORKFLOW is required, e.g. make config-show WORKFLOW=translate DATASET=faithdial" && exit 1)
	$(CLI) config-show --workflow $(WORKFLOW) $(dataset_arg) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)

translate:
	@test -n "$(DATASET)" || (echo "DATASET is required, e.g. make translate DATASET=faithdial" && exit 1)
	$(CLI) translate --dataset $(DATASET) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)

evaluate:
	@test -n "$(DATASET)" || (echo "DATASET is required, e.g. make evaluate DATASET=faithdial" && exit 1)
	$(CLI) evaluate --dataset $(DATASET) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)

reformat:
	@test -n "$(DATASET)" || (echo "DATASET is required, e.g. make reformat DATASET=globalwoz RUN=ff" && exit 1)
	$(CLI) reformat --dataset $(DATASET) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)

inspect-source:
	@test -n "$(DATASET)" || (echo "DATASET is required, e.g. make inspect-source DATASET=globalwoz RUN=ff" && exit 1)
	$(CLI) inspect-source --dataset $(DATASET) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)

benchmark-judge:
	$(CLI) benchmark-judge $(dataset_arg) $(run_arg) --config-root $(CONFIG_ROOT) $(set_args)
