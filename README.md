<div align="center">

# 🏛️ Museum Curator Agent
### The Autonomous AI Archivist
**Discover. Analyze. Archive.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-BSD_3--Clause-green.svg)](LICENSE)
[![Powered By](https://img.shields.io/badge/AI-Google_ADK_%7C_Groq-purple)](https://github.com/google/project-id-here)
[![Deploy](https://img.shields.io/badge/Deploy-Render-black)](https://render.com)
[![Control](https://img.shields.io/badge/Control-Telegram-blue)](https://telegram.org)

[Features](#-key-features) • [Architecture](#-architecture) • [Deployment](#-deployment) • [The Squad](#-the-squad)

</div>

---

## 🚀 What is the Museum Curator Agent?

The **Museum Curator Agent** is a cloud-native, multi-agent system designed to reclaim digital heritage. It autonomously navigates global museum collections, identifies cultural artifacts, and aggregates them into a unified, open-access archive.

Unlike traditional scrapers that break when websites change, this agent uses **Computer Vision (Gemini 3 Flash)** and **Cognitive Agents (Llama 4)** to "see" and "read" museum pages like a human curator.

**It runs 24/7 on the Cloud (Render) and is controlled entirely via Telegram.**

> *"It doesn't just scrape. It discovers artifacts, researches their cultural context, and writes historical abstracts."*

## ✨ Key Features

* **📱 Mobile Command Center**: Zero dashboards to host. Start, stop, and monitor the agent directly from **Telegram**.
* **👁️ Cognitive Vision (SoM)**: Uses **Gemini 3 Flash** with "Set-of-Mark" tagging to extract metadata (Dimensions, Materials, Dates) from unstructured screenshots.
* **🧠 The "Shared Brain"**: Decouples logic from memory. The agent can crash or restart, and the **Neon (Postgres)** database remembers exactly where it left off.
* **🛡️ Free-Tier Optimized**: strict adherence to RPD (Requests Per Day) limits.
    * *Scout:* Llama 4 (Groq) for high-volume reading.
    * *Vision:* Gemini 3 (Google) for precision extraction.

## 🛠️ The Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Framework** | **Google ADK** | Agent orchestration & Tool use |
| **Orchestrator** | **Llama 4 Maverick** (Groq) | Decision making & Task delegation |
| **Vision** | **Gemini 3 Flash** | Image analysis & OCR |
| **Research** | **Gemini 2.5 Flash** | Cultural context search |
| **Browser** | **Playwright** (Headless) | Stealth navigation |
| **Memory** | **Neon** (Postgres) | Serverless state management |
| **Interface** | **Telegram Bot API** | Remote control UI |

## 🏗️ Architecture

This project implements a **"Squad" Architecture** managed by a central Orchestrator.

### 1. The Scout (Llama 4)
* **Role:** The Explorer.
* **Task:** Scans search result pages (HTML) to find deep links to specific objects.
* **Limit:** Optimized for 30k TPM (Tokens Per Minute).

### 2. The Visionary (Gemini 3)
* **Role:** The Extractor.
* **Task:** Visits the object page, takes a screenshot, and extracts precise JSON metadata.
* **Limit:** Conserves the 20 RPD (Requests Per Day) limit for high-value targets only.

### 3. The Historian (Gemini 2.5)
* **Role:** The Researcher.
* **Task:** Googles the object's title to find cultural context and writes a 50-word abstract.

## ⚡ Deployment

This agent is designed to run on the **Render Free Tier**.

### Prerequisites
* **Neon Account**: Create a free Postgres project.
* **Telegram Bot**: Create a bot via `@BotFather`.
* **Hugging Face Token**: For dataset uploads.

### Step 1: Clone & Configure
```bash
git clone https://github.com/Nwokike/museum-curator-agent.git
cd museum-curator-agent

```

### Step 2: Local Setup

Create a `.env` file:

```ini
DATABASE_URL=postgres://...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
TELEGRAM_TOKEN=12345:ABC...

```

### Step 3: Deploy to Render

1. Create a **New Web Service**.
2. Connect your repo.
3. **Build Command:** `./build.sh`
4. **Start Command:** `python bot.py`
5. Add your Environment Variables.

## 🎮 How to Use

Once deployed, open your Telegram Bot and send:

* `/start` - Wake up the system.
* `/status` - Check the Queue (Pending vs. Archived).
* `/run` - **Launch the Squad.** The agent will begin the Scout -> Vision -> Historian loop.
* `/stop` - **Emergency Brake.** The agent finishes the current item and sleeps.