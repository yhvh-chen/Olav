"""Banner definitions for OLAV CLI.

Users can customize by editing this file directly.
Supports Rich markup language for colors and formatting.
"""

# Default OLAV + Snowman banner (Side-by-side)
DEFAULT_BANNER = """[bold bright_cyan] ▄████▄ [/][bold blue]▓[/][bold white]  ██      [/][bold bright_green]  ▄████▄  [/][bold blue]▓[/][bold magenta]  ██    ██[/]   [cyan]  ✶    [/][bold white]▄▀▀▄[/][cyan]   ✶   [/]
[bold bright_cyan]██▀  ▀██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██▀  ▀██ [/][bold blue]▓[/][bold magenta]  ██    ██[/]    [bold white] .  ( [cyan]°[/] [cyan]°[/] )  .   [/]
[bold bright_cyan]██    ██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ████████ [/][bold blue]▓[/][bold magenta]  ██    ██[/]    [bold white]  . (  [orange1]>[/]  ) .    [/]
[bold bright_cyan]██▄  ▄██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]   ██  ██ [/]    [bold white]   (   [red]~[/]   )      [/]
[bold bright_cyan] ▀████▀ [/][bold blue]▓[/][bold white]  ████████[/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]    ████  [/]    [bold white]   ▄▀     ▀▄     [/]
[bold blue] ▓▓▓▓▓▓ [/][bold blue] [/][bold grey39]  ▓▓▓▓▓▓▓▓[/][bold dark_green]  ▓▓    ▓▓ [/][bold blue] [/][bold purple]    ▓▓   [/]    [dim white]   ❆   ❅   ❆   [/]"""

# OLAV Logo only
OLAV_LOGO = """[bold bright_cyan] ▄████▄ [/][bold blue]▓[/][bold white]  ██      [/][bold bright_green]  ▄████▄  [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██▀  ▀██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██▀  ▀██ [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██    ██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ████████ [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██▄  ▄██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]   ██  ██ [/]
[bold bright_cyan] ▀████▀ [/][bold blue]▓[/][bold white]  ████████[/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]    ████  [/]
[bold blue] ▓▓▓▓▓▓ [/][bold blue] [/][bold grey39]  ▓▓▓▓▓▓▓▓[/][bold dark_green]  ▓▓    ▓▓ [/][bold blue] [/][bold purple]    ▓▓   [/]"""

# Snowman only
SNOWMAN = """[cyan]   ✶   [/][bold white]▄▀▀▄[/][cyan]   ✶   [/]
[bold white]   .  ( [cyan]°[/] [cyan]°[/] )  .   [/]
[bold white]   . (  [orange1]>[/]  ) .    [/]
[bold white]  (   [red]~[/]   )      [/]
[bold white]  ▄▀     ▀▄     [/]
[dim white]   ❆   ❅   ❆   [/]"""

# Minimal text only
MINIMAL = "[bold cyan]OLAV[/] [bold white]v0.8[/] - [dim]Network Operations AI Assistant[/]"

# DeepAgents style
DEEPAGENTS = """[bold cyan]
  ╔════════════════════════════════════════════════════════════╗
  ║ [bold white]DeepAgents[/] [cyan]- Agentic AI Framework                   ║
  ║                                                            ║
  ║ [dim]Powered by LangGraph & LangChain                        ║
  ╚════════════════════════════════════════════════════════════╝
[/]"""

# Empty banner
NONE = ""

# ============================================================================
# OEM Customization - Edit below to customize banner
# ============================================================================

# Company-branded banner example (uncomment and edit to use)
# CUSTOM = """[bold cyan]
#   ╔════════════════════════════════════════╗
#   ║  [bold white]YourCompany[/] Network Operations    ║
#   ║  [cyan]Enterprise Edition v2.0[/]           ║
#   ║  [dim]Secure • Reliable • Intelligent[/]    ║
#   ╚════════════════════════════════════════╝
# [/]"""

# Banner mapping - change ACTIVE_BANNER to switch
BANNERS = {
    "default": DEFAULT_BANNER,
    "olav": OLAV_LOGO,
    "snowman": SNOWMAN,
    "minimal": MINIMAL,
    "deepagents": DEEPAGENTS,
    "none": NONE,
    # "custom": CUSTOM,  # Uncomment to use custom banner
}

# Set the active banner here or in settings.json
ACTIVE_BANNER = "default"


def get_banner_text(banner_name: str = ACTIVE_BANNER) -> str:
    """Get banner text by name.

    Args:
        banner_name: Name of the banner (key in BANNERS dict)

    Returns:
        Banner text string
    """
    return BANNERS.get(banner_name.lower(), DEFAULT_BANNER)
