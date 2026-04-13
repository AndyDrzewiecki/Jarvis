"""
TUTORIAL: main.py is the Rich CLI for Jarvis.
Commands:
  - Type any message to chat
  - 'help'    → shows adapter table
  - 'history' → shows last 10 messages
  - 'quit'/'exit' → exits

Adapter responses are shown with a colored [adapter-name] tag.
General chat is shown in default color.
"""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import print as rprint

import jarvis.memory as memory
from jarvis.core import chat, get_adapter_list

console = Console()

ADAPTER_COLOR = "cyan"
JARVIS_COLOR = "green"
ERROR_COLOR = "red"
USER_COLOR = "yellow"


def show_help() -> None:
    table = Table(title="Jarvis Adapters", show_header=True, header_style="bold magenta")
    table.add_column("Adapter", style="cyan", width=12)
    table.add_column("Description", width=45)
    table.add_column("Capabilities", style="dim")
    for a in get_adapter_list():
        table.add_row(a["name"], a["description"], ", ".join(a["capabilities"]))
    console.print(table)


def show_history() -> None:
    messages = memory.recent(10)
    if not messages:
        console.print("[dim]No conversation history yet.[/dim]")
        return
    console.print("\n[bold]Last 10 messages:[/bold]")
    for m in messages:
        ts = m.get("timestamp", "")[:19]
        role = m.get("role", "?")
        text = m.get("text", "")[:200]
        adapter = m.get("adapter")
        tag = f" [{adapter}]" if adapter and adapter != "jarvis" else ""
        if role == "user":
            console.print(f"[{USER_COLOR}][{ts}] You:[/{USER_COLOR}] {text}")
        else:
            console.print(f"[{JARVIS_COLOR}][{ts}] Jarvis{tag}:[/{JARVIS_COLOR}] {text}")
    console.print()


def main() -> None:
    console.print("[bold green]Jarvis[/bold green] — local AI assistant. Type [bold]help[/bold] for adapters, [bold]history[/bold] for recent chat, [bold]quit[/bold] to exit.\n")

    while True:
        try:
            user_input = console.input(f"[{USER_COLOR}]You>[/{USER_COLOR}] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        if user_input.lower() == "help":
            show_help()
            continue

        if user_input.lower() == "history":
            show_history()
            continue

        result = chat(user_input)

        adapter_tag = result.adapter or "jarvis"
        color = ADAPTER_COLOR if adapter_tag != "jarvis" else JARVIS_COLOR
        err_prefix = "[red]Error:[/red] " if not result.success else ""

        console.print(f"\n[{color}][{adapter_tag}][/{color}] {err_prefix}{result.text}\n")


if __name__ == "__main__":
    main()
