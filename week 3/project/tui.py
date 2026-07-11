import os
import sys
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Horizontal, Vertical
from textual.binding import Binding

from agent import Agent
class TUIAgent(Agent,App):
    CSS = """
    Horizontal {
        height: 1fr;
    }
    #chat-panel {
        width: 65%;
        border: solid $primary;
    }
    #tool-panel {
        width: 35%;
        border: solid $warning;
    }
    Input {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear_display", "Clear Display Viewport"),
        Binding("ctrl+h", "clear_history", "Hard Reset Context Memory"),
        Binding("ctrl+t", "quit", "Exit Session Window"),
    ]

    def __init__(self, workspace: str = ".", session_id: str | None = None):
        Agent.__init__(self, workspace=workspace, session_id=session_id)
        App.__init__(self)

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

    def _emit(self,event,**data)->None:
        if event=="tool_call":
            tool_name=data.get("name","unknown")
            try:
                tool_panel = self.query_one("#tool-panel", RichLog)
                self.call_from_thread(tool_panel.write, f"[bold yellow]TOOL CALL:[/bold yellow] executing {tool_name}")
            except Exception:
                pass
    
    def on_input_submitted(self, event: Input.Submitted):
        user_text=event.value.strip()
        if not user_text:
            return
        chat_panel = self.query_one("#chat-panel", RichLog)
        chat_panel.write(f"\n[bold blue]You:[/bold blue] {user_text}")
        
        event.input.clear() 

        self.run_worker(self.call_agent(user_text), thread=True)

    async def call_agent(self, user_text: str) -> None:
        chat_panel = self.query_one("#chat-panel", RichLog)
        response = self.chat(user_text)
        self.call_from_thread(chat_panel.write, f"[bold green]Agent:[/bold green] {response}")

    def action_clear_display(self) -> None:
        self.query_one("#chat-panel", RichLog).clear()
        self.query_one("#tool-panel", RichLog).clear()
        self.query_one("#chat-panel", RichLog).write("[bold yellow]Display viewports cleared. Memory is preserved.[/bold yellow]\n")

    def action_clear_history(self) -> None:
        self.action_clear_displayt()
        from agent import build_system_prompt
        self.messages = [{"role": "system", "content": build_system_prompt()}]
        chat_panel = self.query_one("#chat-panel", RichLog)
        chat_panel.write("[bold red]History Cleared.[/bold red] Conversation history reset.")


if __name__ == "__main__":
    app = TUIAgent()
    app.run()


    