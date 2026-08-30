FROM apache/beam_python3.13_sdk:2.75.0

ENV FLEX_TEMPLATE_PYTHON_PY_FILE=/opt/pipeline/beam_entrypoint.py \
    FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE=/opt/pipeline/requirements-dataflow.txt \
    DATAFLOW_ADDITIONAL_EXPERIMENTS=enable_portable_runner

WORKDIR /opt/pipeline
COPY src/alfabetizacao_pipeline/streaming ./alfabetizacao_pipeline/streaming
COPY schemas/events ./schemas/events

USER 65532:65532

ENTRYPOINT ["/opt/apache/beam/boot"]
