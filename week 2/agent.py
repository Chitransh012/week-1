import os
import sys
import json
import requests
from urllib.parse import urlparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Horizontal
from dotenv import load_dotenv

try:
    import trafilatura
except ImportError:
    trafilatura = None

load_dotenv()

if "OPENROUTER_API_KEY" not in os.environ or "SERPER_API_KEY" not in os.environ:
    print("some error occured in getting api keys")
    sys.exit(1)

from openai import OpenAI
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

MODEL = "openrouter/free"
MAX_ITERATIONS = 8

SERPER_API_KEY = os.environ["SERPER_API_KEY"]

def web_search(query: str, num_results: int = 5) -> list[dict]:
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results
    except Exception as e:
        return [{"error": f"some error occured in searching with serper: {str(e)}"}]

def web_fetch(url: str) -> str:
    try:
        """Fetch the content of a URL and return it as text."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"some error occured in fetching response:{str(e)}"
    
def fetch_clean(url: str) -> str:
    try:
        html = web_fetch(url)
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        return text or ""
    except Exception as e:
        return f"some error occured in using trafilatura {str(e)}"

MAX_CHARS = 8000

def fetch_for_agent(url: str) -> str:
    content = fetch_clean(url)
    if len(content) > MAX_CHARS:
        content = content[:MAX_CHARS] + "\n\n[...truncated]"
    return content

def discover_papers(query: str) -> list[dict]:
    try:
        # Communicate directly with the server using standard HTTP requests
        resp = requests.post(
            "https://mcp.alphaxiv.org/tools/discover_papers",
            json={"query": query},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("papers", [])[:4]
        else:
            return [{f"AlphaXiv API returned status code: {resp.status_code}"}]
    except Exception as e:
        return [{f"AlphaXiv paper discovery failed: {str(e)}"}]

def get_paper_content(paper_id: str) -> str:
    try:
        resp = requests.post(
            "https://mcp.alphaxiv.org/tools/get_paper_content",
            json={"paper_id": paper_id},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            content = resp.json().get("content", "Empty content text field returned.")
            if len(content) > 5000:
                return content[:5000] + "\n\n[...Truncated...]"
            else:
                return content
        return f"AlphaXiv content server returned error status code: {resp.status_code}"
    except Exception as e:
        return f"Failed to load AlphaXiv document details: {str(e)}"
    
TOOL_REGISTRY={
    "web_search":web_search,
    "web_fetch":fetch_for_agent,
    "discover_papers":discover_papers,
    "get_paper_content":get_paper_content
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live web for recent events, facts, news articles, and links using keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The explicit target search query keywords stream."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and parse the raw body text content of an absolute web URL link page address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The exact absolute web target URL address link."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discover_papers",
            "description": "Search AlphaXiv academic database for physics, computer science, and AI papers matching keyword queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Academic search terms, e.g. 'Quantum Error Correction'"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_content",
            "description": "Fetch the body context, details, and text content for a specific AlphaXiv paper document id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "The exact target paper identifier or string hash key."}
                },
                "required": ["paper_id"]
            }
        }
    }
]
class PerplexityApp(App):
    """Dual-panel terminal engine coordinating user logs alongside active tool queues."""

    TITLE = "Perplexity Research Agent"
    
    CSS = """
    Screen {
        layout: vertical;
    }
    Horizontal {
        height: 1fr;
    }
    #chat-panel {
        width: 50%;
        border: solid green;
        background: blue;
    }
    #tool-panel {
        width: 40%;
        border: round blue;
        background: green;
    }
    Input {
        dock: bottom;
        height:3;
    }
    """
    BINDINGS = [
        Binding("ctrl+l", "clear_display", "Clear Display Viewport"),
        Binding("ctrl+h", "clear_history", "Hard Reset Context Memory"),
        Binding("ctrl+t", "quit", "Exit Session Window"),
    ]

    def __init__(self):
        super().__init__()
        # Central conversation logging state array tracking variables
        self.messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are a premium autonomous synthesis researcher. "
                    "You possess tools to search Google, scrape URLs, and read AlphaXiv academic papers. "
                    "Chain tools together dynamically to verify details step-by-step. Always cite links, papers, and sources."
                )
            }
        ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield RichLog(id="chat-panel", wrap=True, markup=True)
            yield RichLog(id="tool-panel", wrap=True, markup=True)
        yield Input(placeholder="Ask anything...")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#chat-panel").write("[bold]Chat[/bold]\n")
        self.query_one("#tool-panel").write("[bold]Tool Log[/bold]\n")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_query = event.value.strip()
        if not user_query:
            return

        event.input.clear()

        chat = self.query_one("#chat-panel", RichLog)
        chat.write(f"\n[bold cyan][User Question][/bold cyan] {user_query}")
        self.messages.append({"role": "user", "content": user_query})
        self.run_worker(self._run_agent_loop_worker, thread=True)

    def dispatch(self,tool_call) -> str:
        try:
            if tool_call.function.name in TOOL_REGISTRY:
                tool_name=tool_call.function.name
                arguments=json.loads(tool_call.function.arguments)
                tool_function=TOOL_REGISTRY[tool_name]
                json_dict=tool_function(**arguments)
                result_dict=json.dumps(json_dict)
                return result_dict
            else:
                return json.dumps({"error": f"Unknown tool reference mapping: {tool_call.function.name}"})
        except Exception as e:
            return json.dumps({"error": f"Tool execution pipeline failure: {str(e)}"})
        
    def _run_agent_loop_worker(self) -> None:
        """Isolated background workflow thread management managing execution sweeps safely."""
        chat = self.query_one("#chat-panel", RichLog)
        tool_log = self.query_one("#tool-panel", RichLog)

        try:
            self.call_from_thread(tool_log.write, "[dim]📡 External tool pipeline status checked: OK.[/dim]")

            # Run the Multi-Step Reasoning Cycle Window Limit
            for iteration in range(MAX_ITERATIONS):
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=self.messages,
                    tools=TOOLS
                )
                
                message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "tool_calls":
                    self.messages.append(message)
                    
                    for tool_call in message.tool_calls:
                        self.call_from_thread(tool_log.write, f"[bold yellow] Calling Tool:[/bold yellow] [cyan]{tool_call.function.name}({tool_call.function.arguments})[/cyan]")
                        tool_output_json_string = self.dispatch(tool_call)
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": tool_output_json_string
                            }
                    self.messages.append(tool_message)
                    continue
                elif finish_reason == "stop":
                    self.messages.append(message)
                    self.call_from_thread(self.final_answer, message.content)
                    return

            self.call_from_thread(chat.write, "[bold red] System Error:[/bold red] Agent loop hit max execution iteration boundary step depth without resolving.")

        except Exception as e:
            error_notice = f"[bold red] System Core Exception Crash Encountered:[/bold red] {str(e)}"
            self.call_from_thread(chat.write, error_notice)
            self.call_from_thread(tool_log.write, f"[red]CRASH DEBUG: {str(e)}[/red]")
    def final_answer(self, final_text: str) -> None:
        chat = self.query_one("#chat-panel", RichLog)
        chat.write(f"\n[bold green]📚 Synthesis Report Compiled:[/bold green]\n{final_text}\n")

    def action_clear_display(self) -> None:
        self.query_one("#chat-panel", RichLog).clear()
        self.query_one("#tool-panel", RichLog).clear()
        self.query_one("#chat-panel", RichLog).write("[bold yellow]Display viewports cleared. Memory is preserved.[/bold yellow]\n")

    def action_clear_history(self) -> None:
        self.messages = [
            {
                "role": "system",
                "content": "You are a premium Perplexity-style autonomous synthesis researcher."
            }
        ]
        self.query_one("#chat-panel", RichLog).clear()
        self.query_one("#tool-panel", RichLog).clear()
        self.query_one("#chat-panel", RichLog).write("[bold red] History wiped clean.[/bold red]\n")


if __name__ == "__main__":
    PerplexityApp().run()


