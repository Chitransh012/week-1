import os
import sys
import json
import glob as glob_module
from openai import OpenAI
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone
load_dotenv()

import tools.files as files
import tools.papers as papers
import tools.web as web

WORKSPACE_ROOT=os.path.abspath(os.environ.get("WORKSPACE_ROOT","."))
SESSION_DIRS=os.path.join(WORKSPACE_ROOT,".agent/sessions")
AGENTS_PATHS = ("AGENTS.md", ".agent/AGENTS.md")
MAX_ITERATIONS=10
MAX_READ_CHARS=12_000


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
MODEL = "openrouter/free"

BASE_PROMPT = "You are Research Desk, a helpful research assistant."
   
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file with pagination line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "default": 1},
                    "read_lines": {"type": "integer", "default": 200},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a research file entirely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Surgically modify specific files using replace, delete, or append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "operation": {"type": "string", "enum": ["replace", "delete", "append"]},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["path", "operation", "start_line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List or glob available repository files under the sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "pattern": {"type": "string", "default": "*"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "paper_search",
            "description": "Search indexed academic literature on Hugging Face Papers for snippets and arXiv IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The target keyword research phrase"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_paper",
            "description": "Fetches high-level metadata catalog properties and parsed markdown text fields for an arXiv paper.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arxiv_id": {"type": "string", "description": "The normalized identifier code string or complete link URL"}
                },
                "required": ["arxiv_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Queries the live open web with Serper Google index matches for technical facts and documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 5}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Downloads full text pages from web link URLs and filters noise out into clear layout copy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"],
            },
        },
    }
]

def create_session()->str:
    os.makedirs(SESSION_DIRS,exist_ok=True)
    session_id=uuid.uuid4().hex[:8]
    return session_id

def save_session(session_id:str,messages:list,title:str="Untitled")->None:
    os.makedirs(SESSION_DIRS,exist_ok=True)
    path=os.path.join(SESSION_DIRS,f"{session_id}.json")
    session_data={"id":session_id,"title":title,"updated_at": datetime.now(timezone.utc).isoformat(),"messages":messages}
    with open(path,"w",encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)

def load_session(session_id:str)->dict:
    path=os.path.join(SESSION_DIRS,f"{session_id}.json")
    if not os.path.exists(path):
        return {"error":f"file not found"}
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)


class Agent:
    def __init__(self, workspace: str = ".", session_id: str | None = None):
        self.workspace = os.path.abspath(workspace)
        if session_id:
            try:
                data=load_session(session_id)
                self.session_id=data["id"]
                self.messages=data["messages"]
            except Exception:
                self.session_id=create_session()
                self.messages=[{"role":"system","content":build_system_prompt()}]
        else:
            self.session_id=create_session()
            self.messages=[{"role":"system","content":build_system_prompt()}]
    def chat(self,user_message:str)->str:
        self.messages.append({"role":"user","content":user_message})
        answer=self._run_loop()
        save_session(self.session_id,self.messages)
        return answer
    def run_once(self,prompt:str)->str:
        return self.chat(prompt)
    def _run_loop(self)->str:
        for _ in range(MAX_ITERATIONS):
            response=client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=TOOLS
            )
            msg=response.choices[0].message
            self.messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [t.model_dump() for t in msg.tool_calls] if msg.tool_calls else None
            })
            if not msg.tool_calls:
                return msg.content or""
            for tool_call in msg.tool_calls:
                self._emit("tool_call", name=tool_call.function.name)
                result_str = self.dispatch(tool_call)
                self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": result_str
                        })
        return "Error: Maximum iteration loop budget exceeded."
    
    def dispatch(self,tool_call)->str:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except Exception:
            return json.dumps({"error": "Failed to extract valid json arguments."})
            
        if name == "read_file":
            res = files.read_file(args.get("path"), args.get("start_line", 1), args.get("read_lines", 200))
        elif name == "write_file":
            res = files.write_file(args.get("path"), args.get("content", ""))
        elif name == "edit_file":
            res = files.edit_file(
                args.get("path"), args.get("operation"), args.get("start_line"),
                args.get("end_line"), args.get("content")
            )
        elif name == "list_files":
            res = files.list_files(args.get("path", "."), args.get("pattern", "*"))
        elif name == "paper_search":
            res = papers.paper_search(args.get("query"))
        elif name == "read_paper":
            res = papers.read_paper(args.get("arxiv_id"))
        elif name == "web_search":
            res = web.web_search(args.get("query"), args.get("num_results", 5))
        elif name == "web_fetch":
            res = web.fetch_for_agent(args.get("url"))
        else:
            res = {"error": f"Tool '{name}' not found."}
            
        return json.dumps(res)
    
    def _emit(self, event: str, **data) -> None:
        """Override in subclasses for UI updates."""
        pass

class REPLAgent(Agent):

    def run(self) -> None:
        print(f"Research Desk [{self.session_id}] — /quit to exit")
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_input or user_input in ("/quit", "/exit"):
                break
            print(self.chat(user_input))
            print()

    def _emit(self, event: str, **data) -> None:
        if event == "tool_call":
            print(f"  [tool] {data.get('name')}", file=sys.stderr)


def build_system_prompt() -> str:
    prompt=BASE_PROMPT
    for path in AGENTS_PATHS:
        if os.path.exists(path):
            try:
                with open(path,"r",encoding="utf-8") as f:
                    content=f.read().strip()
                if content:
                    prompt+=f"\n\n===Project Rules and Instructions===\n\n{content}"
                break
            except Exception:
                pass
    return prompt


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=str, help="Resume an existing session ID")
    parser.add_argument("--tui", action="store_true", help="Launch the full-screen terminal interface layout")
    parser.add_argument("query", nargs="?", type=str, help="Optional one-shot query string")
    args = parser.parse_args()
    if args.tui:
        from tui import TUIAgent
        app = TUIAgent(session_id=args.session)
        app.run()
        return
    agent = REPLAgent(session_id=args.session)
    if args.query:
        print(agent.run_once(args.query))
        return
    agent.run()

if __name__ == "__main__":
    main()







    
    








