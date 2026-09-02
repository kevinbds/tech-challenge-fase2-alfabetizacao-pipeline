FROM gcr.io/dataflow-templates-base/python313-template-launcher-base@sha256:3b739eee1143263b8f4740beb0b18a28e511533ebb8b1577bd3fdf2b05bd223d AS runtime

ENV FLEX_TEMPLATE_PYTHON_PY_FILE=/opt/pipeline/beam_entrypoint.py \
    DATAFLOW_ADDITIONAL_EXPERIMENTS=enable_portable_runner

WORKDIR /opt/pipeline
COPY containers/dataflow/beam_entrypoint.py ./beam_entrypoint.py
COPY containers/dataflow/requirements-dataflow.txt ./requirements-dataflow.txt
COPY containers/dataflow/requirements-overrides.txt ./requirements-overrides.txt
COPY src/alfabetizacao_pipeline ./alfabetizacao_pipeline

# Beam 2.75 ainda limita cryptography e httplib2 a versões anteriores às correções.
# Os overrides ficam isolados e o alvo de auditoria valida os conflitos de metadados conhecidos.
RUN python -m pip install --no-cache-dir -r requirements-dataflow.txt \
    && python -m pip install --no-cache-dir --no-deps -r requirements-overrides.txt \
    && python -m pip uninstall --yes nltk

ENV PYTHONPATH=/opt/pipeline

FROM runtime AS dataflow-dependency-audit
COPY containers/dataflow/check-dependency-overrides.sh /tmp/check-dependency-overrides.sh
RUN /bin/sh /tmp/check-dependency-overrides.sh \
    && python -m pip install --no-cache-dir pip-audit==2.9.0 \
    && python -m pip_audit --local

FROM runtime AS dataflow-template
ENTRYPOINT ["/opt/google/dataflow/python_template_launcher"]

FROM runtime AS dataflow-sdk
ENTRYPOINT ["/opt/apache/beam/boot"]
