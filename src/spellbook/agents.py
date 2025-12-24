"""Agent definitions and styling for Spellbook."""

from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


@dataclass
class AgentConfig:
    """Configuration for a Spellbook agent."""

    name: str
    color: str
    icon: str
    description: str


# Agent color/style definitions
AGENTS = {
    "archivist": AgentConfig(
        name="Archivist",
        color="blue",
        icon="\u2699",  # gear
        description="Process transcripts into structured docs",
    ),
    "librarian": AgentConfig(
        name="Librarian",
        color="green",
        icon="\U0001F4DA",  # books
        description="Deep retrieval with synthesis",
    ),
    "researcher": AgentConfig(
        name="Researcher",
        color="cyan",
        icon="\U0001F50D",  # magnifying glass
        description="Fast factual lookup",
    ),
    "specter": AgentConfig(
        name="Specter",
        color="red",
        icon="\U0001F47B",  # ghost
        description="Dead code and quality checks",
    ),
    "trader": AgentConfig(
        name="Trader",
        color="yellow",
        icon="\U0001F4C8",  # chart
        description="Options and risk analysis",
    ),
    "ai-engineer": AgentConfig(
        name="AI Engineer",
        color="magenta",
        icon="\U0001F916",  # robot
        description="ML systems and LLM integration",
    ),
    "data-engineer": AgentConfig(
        name="Data Engineer",
        color="bright_blue",
        icon="\U0001F4BE",  # floppy
        description="Pipelines and databases",
    ),
    "quant-dev": AgentConfig(
        name="Quant Dev",
        color="bright_green",
        icon="\u03A3",  # sigma
        description="Numerical computing",
    ),
}


def get_agent(name: str) -> AgentConfig | None:
    """Get agent config by name."""
    return AGENTS.get(name.lower())


def agent_header(name: str, console: Console | None = None) -> None:
    """Print a styled agent header."""
    if console is None:
        console = Console()

    agent = get_agent(name)
    if not agent:
        console.print(f"[bold]{name}[/bold]")
        return

    header = Text()
    header.append(f"{agent.icon} ", style=agent.color)
    header.append(agent.name, style=f"bold {agent.color}")

    console.print(Panel(header, border_style=agent.color, expand=False))


def agent_print(name: str, message: str, console: Console | None = None) -> None:
    """Print a message with agent styling."""
    if console is None:
        console = Console()

    agent = get_agent(name)
    if not agent:
        console.print(message)
        return

    prefix = Text()
    prefix.append(f"[{agent.name}] ", style=agent.color)
    console.print(prefix, end="")
    console.print(message)


def list_agents(console: Console | None = None) -> None:
    """Print all available agents with their colors."""
    if console is None:
        console = Console()

    console.print("\n[bold]Available Agents[/bold]\n")

    for key, agent in AGENTS.items():
        line = Text()
        line.append(f"  {agent.icon} ", style=agent.color)
        line.append(f"{agent.name:15}", style=f"bold {agent.color}")
        line.append(f" {agent.description}", style="dim")
        console.print(line)

    console.print()
