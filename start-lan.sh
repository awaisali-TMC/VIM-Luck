#!/bin/sh
# Start VIM-Luck on the office network (backend :8000, frontend :5173).
# Local-only helper for this Linux box; not part of the product.
# SSL_CERT_FILE makes Python trust the Fortinet proxy CA (system bundle),
# without which every Gemini call fails with CERTIFICATE_VERIFY_FAILED.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

(cd backend && exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACK=$!
(cd frontend && exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT
# Ports 5173/8000 are blocked between office network segments, so laptops reach the
# app through a PuTTY SSH tunnel (L5173 -> localhost:5173, L8000 -> localhost:8000)
# and the frontend calls the API at http://localhost:8000 (frontend/.env.local).
echo "Open on your laptop (with the PuTTY tunnel connected): http://localhost:5173"
echo "Supplier portal: http://localhost:5173/supplier/   — Ctrl+C stops both"
wait
