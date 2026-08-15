# Token-Wizards — Government Legal Intelligence Assistant

## 1. Usecase Name
**Token-Wizards — Government Legal Intelligence Assistant (Law & LSGD Copilot)**

## 2. What the Agent Does
**Problem Statement:** Evaluating complex building permit applications and statutory queries requires extensive cross-referencing across various acts, rules, government orders, and judicial precedents. Manually processing these applications is time-consuming, prone to human error, and suffers from a lack of immediate access to centralized, up-to-date legal knowledge, leading to delayed decisions or legal liabilities.

**Solution:** The Token-Wizards AI Copilot is a specialized, deep-agentic legal intelligence system built specifically for the **Department of Town and Country Planning** under the Local Self Government Department (LSGD) in Kerala. The core objective is to help town planning and legal officers make accurate, legally sound decisions based on a centralized knowledge source provided by the administrator. 

The system automatically ingests user queries and uploaded documents (such as Form B-7 applications), dynamically searches relevant legal knowledge bases (Rules, Government Orders, and High Court Judgments), and orchestrates multiple domain-specific AI agents to produce a standardized, highly accurate 6-part legal draft opinion. This dramatically reduces evaluation time while ensuring strict adherence to the Kerala building rules and regulations.

## 3. Key Features
- **Deep Agent LangGraph Architecture**: Utilizes an advanced LangGraph workflow to intelligently route, plan, and synthesize responses.
- **Intelligent Query Routing**: The system determines if a query requires legal retrieval or is just conversational. It strictly refuses to answer out-of-scope, non-legal queries, ensuring the assistant remains focused on LSGD matters.
- **Prompt Injection Defense**: Implements a dedicated Guardrail node that actively screens inputs to survive prompt injection attacks and malicious attempts to bypass system constraints.
- **Planner Agent & Strategy Execution**: For legal queries, the Planner Agent decomposes the query, formulating a step-by-step strategy. It identifies exactly what sub-queries are needed and targets specific domains (Rules vs. GOs vs. Judgments).
- **Targeted & Conditional Retrieval**: It executes retrieval only for queries where it is strictly necessary, avoiding expensive and noisy vector searches for simple chitchat.
- **Domain-Targeted Agents**: Includes specialized evaluation agents for different legal categories:
  - **Statutory & Rule Agent** for rule compliance (e.g., Kerala Building Rules 2022).
  - **GO Supersession & Timeline Agent** for executive orders and tracking overrides.
  - **Judicial Precedent & Risk Agent** for evaluating legal liability based on High Court judgements.
- **Sufficiency Checking & Human-in-the-Loop (HITL)**: Before generating an opinion, the planner checks if it has sufficient parameters. If critical application data is missing, it intelligently pauses execution, invoking HITL to ask the legal officer for clarification before proceeding or attempting re-retrieval.
- **Standardized 6-Part Legal Output with Citations**: Guarantees structured outputs consisting of Issue Restatement, Applicable Provisions, Draft Analysis, Compliance Risk Flags, and a Mandatory Officer Disclaimer. Crucially, it provides highly traceable **Sources Used**, appending exact document links, page numbers, and clauses at the end of the response to support the agents' answers.
- **Intelligent Layout-Aware Parsing & Recursive Text Splitting**: The system parses PDFs page-by-page using regular expressions to dynamically detect and extract statutory headings, sections, rules, and case details. It then utilizes LangChain's `RecursiveCharacterTextSplitter` to chunk the parsed text into smaller, highly dense segments (e.g., 1000 characters). Finally, it attaches the structured metadata (document name, precise clause/rule numbers, supersession state) to *each* sub-chunk. This ensures embeddings are highly concentrated in semantic meaning without losing crucial layout context, making vector retrieval hyper-accurate.
- **Admin Knowledge Base Dashboard**: Built-in functionality for administrators to dynamically upload, categorize, and index new legal PDFs or JSON records.

## 4. How to Run It
Follow these steps to set up and run the system locally:

**Prerequisites**:
- Python 3.10+
- An API Key from Groq or OpenAI.

**Step-by-Step Instructions**:
1. **Clone the repository** and navigate to the project root:
   ```bash
   cd Token-Wizards
   ```
2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Mac/Linux:
   source .venv/bin/activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Configuration**:
   Create a `.env` file in the root directory (you can copy `.env.example`) and configure your LLM Provider and API key:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here
   # Or configure OpenAI if using GPT models
   ```
5. **Run the FastAPI Server**:
   Execute the application using Uvicorn:
   ```bash
   uvicorn app.main:app --reload
   ```
6. **Access the Application**:
   Open your browser and navigate to `http://localhost:8000`. You can log in using any dummy credentials (e.g., `admin_yash`) to access the interface.

## 5. Tech Stack Used

### Backend & Core Frameworks
- **Python & FastAPI**: Chosen as the core backend framework. FastAPI provides high-performance, asynchronous request handling, which is essential when streaming LLM responses and managing concurrent agent processes. It also auto-generates API documentation.
- **LangChain & LangGraph**: The backbone of the AI architecture. LangGraph was specifically chosen because it allows for creating complex, **stateful, multi-actor workflows**. This is critical for our Human-in-the-Loop (HITL) requirement, as LangGraph can pause execution, wait for user input, and resume the graph seamlessly.

### Search & Knowledge Retrieval
- **ChromaDB & BM25 (Hybrid Search)**: Used for the Knowledge Base retrieval. We combine dense vector search (ChromaDB for semantic meaning) with sparse keyword search (BM25 for exact rule numbers or GO references) using Reciprocal Rank Fusion (RRF). This hybrid approach is mandatory for legal use cases where both contextual meaning and exact terminology are equally important.

### State & Data Management
- **SQLite**: Used for LangGraph checkpointing (conversation state management) and document metadata tracking. Chosen for its lightweight, serverless nature, making local deployments and testing effortless without needing external database servers.

### Frontend
- **Vanilla HTML5, CSS3 & JavaScript**: Built without heavy frontend frameworks (like React or Angular) to maintain a zero-build-step, extremely lightweight, and blazing-fast dashboard. **Marked.js** is utilized to dynamically render the markdown outputs generated by the AI agents.

### LLMs & AI Models
- **Groq (Llama-3.1-8b-instant / Llama-3-70b-versatile)**: Serves as the primary inference engine. 
  - **Purpose**: Handles fast query routing, decomposition, and conversational (chit-chat) tasks. 
  - **Why this model?**: Multi-agent architectures require multiple, sometimes sequential, LLM calls. Groq's ultra-low latency inference ensures the system remains highly responsive, preventing users from waiting long periods for a multi-agent pipeline to finish.
- **OpenAI (GPT-4o / GPT-4o-mini)** *(Configurable Alternative)*:
  - **Purpose**: Used for the heavy-lifting legal analysis, drafting the final opinion, or acting as the Self-Reflective Legal Critic.
  - **Why this model?**: When dealing with highly nuanced legal precedents and complex statutory interpretations, GPT-4o provides state-of-the-art reasoning capabilities, ensuring the final legal draft is logically sound and factually grounded.
- **Embedding Model (`jinaai/jina-embeddings-v2-base-en`)**: Used by ChromaDB to vectorize document chunks.
  - **Purpose**: Creates dense vector embeddings of legal documents for semantic similarity searches.
  - **Why this model?**: It is a state-of-the-art open-source embedding model that supports a massive **8192 token context window** (unlike the default 256 tokens in standard MiniLM models). It ensures large chunks of legal text retain their full semantic meaning entirely locally, avoiding sensitive data transmission to external APIs while eliminating token costs.
- **Document Processing Tooling**: **PyPDF** and **pdfplumber** are used to parse complex legal PDFs, extracting not just text, but structured page numbers and layout data critical for accurate legal citations.

## 6. Data or Knowledge Base Used
The system is powered by a specifically curated **Mock Legal Corpus** modeled after the Kerala state legal framework. The `data/mock_corpus/` directory includes both PDF and pre-chunked JSON representations of:
- Statutory Acts & Rules (e.g., Kerala Building Rules 2022)
- Executive Government Orders (e.g., GO P 45 2024 LSGD, GO 22 2021 LSGD)
- Departmental Circulars (e.g., Circular 12 2025 ENV)
- High Court Judgments (e.g., WP(C) 1234/2023)
- Sample Application Forms (e.g., Form B-7 Building Permit Application)

The vector store auto-populates upon startup if it's empty, ensuring the AI agents have immediate access to context.

## 7. Limitations (if any)
- **Mock Data Scoped**: The system is highly tuned to the provided mock data. Expanding it to generic law beyond Kerala building rules may require modifying the system prompts or agents.
- **Frontend Prototype Features**: Profile settings and user creation functionalities are currently UI placeholders designed to demonstrate workflow, and do not connect to a robust backend authentication or user database layer.
