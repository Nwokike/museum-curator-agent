#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install Python Dependencies
pip install -r requirements.txt

# 2. Install Playwright Browsers (Chromium only to save space)
playwright install chromium