FROM gcr.io/dataflow-templates-base/python313-template-launcher-base@sha256:3b739eee1143263b8f4740beb0b18a28e511533ebb8b1577bd3fdf2b05bd223d

ENV FLEX_TEMPLATE_PYTHON_PY_FILE=/opt/pipeline/beam_entrypoint.py \
    FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE=/opt/pipeline/requirements-dataflow.txt \
    DATAFLOW_ADDITIONAL_EXPERIMENTS=enable_portable_runner

WORKDIR /opt/pipeline
COPY containers/dataflow/beam_entrypoint.py ./beam_entrypoint.py
COPY containers/dataflow/requirements-dataflow.txt ./requirements-dataflow.txt
COPY src/alfabetizacao_pipeline ./alfabetizacao_pipeline

RUN python -m pip install --no-cache-dir -r requirements-dataflow.txt

ENV PYTHONPATH=/opt/pipeline
