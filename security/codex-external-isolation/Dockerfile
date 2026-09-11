FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home --home-dir /opt/codex-isolation/runtime/user \
        --shell /usr/sbin/nologin isolator \
    && mkdir -p /opt/codex-isolation/runtime /opt/codex-isolation/results /etc/codex \
    && chown -R isolator:isolator /opt/codex-isolation

WORKDIR /opt/codex-isolation
COPY requirements.txt /opt/codex-isolation/requirements.txt
RUN pip install --no-cache-dir -r /opt/codex-isolation/requirements.txt

COPY config/config.toml /opt/codex-isolation/config/config.toml
COPY config/requirements.toml /opt/codex-isolation/config/requirements.toml
COPY config/requirements.toml /etc/codex/requirements.toml
COPY scripts/run_test0.py /opt/codex-isolation/scripts/run_test0.py

USER isolator:isolator
ENV HOME=/opt/codex-isolation/runtime/user \
    CODEX_HOME=/opt/codex-isolation/runtime/home \
    PATH="/usr/local/bin:${PATH}"

ENTRYPOINT ["python3", "/opt/codex-isolation/scripts/run_test0.py"]
