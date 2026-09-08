# ai_course_3rd_homework
simple ReAct agent that uses SQL database created from www.seqme.eu wbesite and use STDIO MCP tool that access this database to answer customer question

# How to run:
1. on HPC, where llm, langflow, uv and dependencies are installed run:
langflow run \
    --host 127.0.0.1 \
    --port 7860
    
3. on HPC in different terminal:
ollama serve

4. tunnel on local pc:
ssh -L 7860:127.0.0.1:7860 metation@192.168.3.45

5. open in canary browser on local pc
http://127.0.0.1:7860

# How to build:
1. on HPC - install dependencies:
cd ~/seqme_service_advisor

uv venv .uv_venv

source .uv_venv/bin/activate

uv pip install langflow

uv pip install \
    requests \
    beautifulsoup4 \
    lxml \
    "mcp[cli]"
    
2. have ollama 
