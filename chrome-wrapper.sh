#!/bin/bash
# Injects --no-sandbox so Chrome runs inside Docker without touching Python code
exec /usr/bin/google-chrome-real --no-sandbox --disable-dev-shm-usage --disable-gpu "$@"
