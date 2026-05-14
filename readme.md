# Prerequisites

## Node.js and npm
This project requires Node.js and npm for the UI components.
1. Download the installer from [nodejs.org](https://nodejs.org/).
2. Run the installer (the LTS version is recommended).
3. Verify the installation by running `node -v` and `npm -v` in your terminal.

# Simulation terminal
python -m venv .venv312
.\.venv312\Scripts\activate
pip install -r requirements.txt
python server.py

# UI / control terminal
cd ui
npm install
npm run dev

# CrewAI
Create a .env file with the following content:

```env
# Choose provider: openai, google, groq, ollama, or lmstudio
MODEL_PROVIDER=groq

# OpenAI Settings - Get API Key at: https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL_NAME=gpt-4o

# Google Gemini Settings - Get API Key at: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_MODEL_NAME=gemini-1.5-pro

# Groq Settings - Get API Key at: https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL_NAME=llama3-70b-8192

# Local Models (Ollama / LM Studio)
OLLAMA_MODEL_NAME=gemma
OLLAMA_BASE_URL=http://localhost:11434
LMSTUDIO_BASE_URL=http://localhost:1234/v1
```
