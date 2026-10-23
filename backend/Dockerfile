# SAP_SDK=on  (default) — production. Copies the licensed NW RFC SDK and builds
#             PyRFC against it, so the image can talk to a real SAP system.
# SAP_SDK=off           — demo/local. No SDK, no PyRFC. Needed because the SDK is
#             git-ignored and lives in a GCS bucket, so a laptop build has no
#             copy of it. Only usable with SAP_MODE=fake at runtime.
#
# The default keeps cloudbuild.yaml's `docker build … backend` byte-identical to
# before — it passes no build-arg, so production still gets the SDK image.
# Docker only builds stages in the target's dependency chain, so with
# SAP_SDK=off the sap-on stage below (and its failing COPY) never runs.
#
#   docker build --build-arg SAP_SDK=off -t <registry>/vim-internal-backend:<tag> backend
ARG SAP_SDK=on

FROM python:3.12-slim AS base

# Avoid interactive prompts, ensure stdout is unbuffered
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── SAP NW RFC SDK (Linux) + PyRFC ────────────────────────────────
# The extracted Linux SDK lives at backend/nwrfcsdk-linux/ (git-ignored,
# uploaded to Cloud Build only). PyRFC needs it at build AND runtime.
FROM base AS sap-on
COPY nwrfcsdk-linux /opt/nwrfcsdk
ENV SAPNWRFC_HOME=/opt/nwrfcsdk \
    LD_LIBRARY_PATH=/opt/nwrfcsdk/lib \
    SAP_NWRFC_SDK_PATH=/opt/nwrfcsdk
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir cython pyrfc==3.3.1 \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ── No SDK ────────────────────────────────────────────────────────
# Nothing to add. pyrfc is imported inside SAPConnectorPyRFC.connect(), not at
# module scope, so the app still imports cleanly — a live RFC call is the only
# thing that fails, and it fails with a message saying why.
FROM base AS sap-off

# ── Final ─────────────────────────────────────────────────────────
FROM sap-${SAP_SDK} AS final

# Copy application code
COPY . .
# The SDK copy inside /app isn't needed (it lives at /opt/nwrfcsdk)
RUN rm -rf /app/nwrfcsdk-linux

# Cloud Run injects PORT (default 8080). Bind to it.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
