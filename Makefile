.PHONY: help test config-show translate evaluate reformat inspect-source benchmark-judge check-translation upload-datasets upload-datasets-push \
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
MAX_ROWS_PER_SPLIT ?=
UPLOAD ?=

dataset_arg = $(if $(strip $(DATASET)),--dataset $(DATASET),)
run_arg = $(if $(strip $(RUN)),--run $(RUN),)
max_rows_arg = $(if $(strip $(MAX_ROWS_PER_SPLIT)),--max-rows-per-split $(MAX_ROWS_PER_SPLIT),)
set_args = $(foreach item,$(SET),--set $(item))
upload_args = $(if $(strip $(UPLOAD)),--upload $(UPLOAD),--all)

help:
	@printf '%s\n' \
	'Common targets:' \
	'  make test' \
	'  make translate DATASET=faithdial' \
	'  make evaluate DATASET=faithdial' \
	'  make check-translation DATASET=faithdial' \
	'  make upload-datasets UPLOAD=daily_dialog_fr' \
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
	'  MAX_ROWS_PER_SPLIT=<row_limit_for_check_translation>' \
	'  UPLOAD=<upload_id_from_conf_uploads>' \
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

check-translation:
	@test -n "$(DATASET)" || (echo "DATASET is required, e.g. make check-translation DATASET=faithdial" && exit 1)
	$(CLI) check-translation --dataset $(DATASET) $(run_arg) --config-root $(CONFIG_ROOT) $(max_rows_arg) $(set_args)

upload-datasets:
	$(CLI) upload-datasets $(upload_args) --config-root $(CONFIG_ROOT)

upload-datasets-push:
	$(CLI) upload-datasets $(upload_args) --config-root $(CONFIG_ROOT) --push --yes
