# Bank Application Portfolio (Django + LLM)

This project is a Django-based portfolio management prototype for a banking environment.

It demonstrates:
- Application portfolio modeling
- LLM integration (analysis, Q&A, Mermaid generation)
- Dashboard with portfolio metrics
- Integrations CRUD
- Mock data generation via LLM
- SQLite persistence

---

## 🏗 Architecture Overview

The application is structured as a modular Django project.

### Core components

- **Applications app**
  - `Application` model (core + satellite apps)
  - `Integration` model (inbound/outbound flows)
  - `TechDebtItem` model
- **Dashboard**
  - Aggregated portfolio metrics
  - Chart-based visualizations
- **LLM integration**
  - Portfolio analysis
  - Q&A mode
  - Mermaid diagram generation + validation
- **Seed command**
  - Generates realistic mock portfolio data via LLM
  - Stores normalized data in SQLite

---


## ⚙️ Setup

### 1. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
MUJ_OPENAI_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=30
LLM_MAX_TOKENS=800
```


### 4. Apply database migrations

```bash
python manage.py migrate
```

### 5. Seed mock portfolio data

```bash
python manage.py seed_portfolio
```

Recommended (wipe existing data first and generate new 40 applcations):

```bash
python manage.py seed_portfolio --wipe --apps 40
```

### 6. Run development server

```bash
python manage.py runserver
```

Open in browser:

```
http://127.0.0.1:8000/
```