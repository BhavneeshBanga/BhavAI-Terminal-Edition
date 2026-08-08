"""
`bhav config` command group — set/get API keys stored in bhavai
package's own .env file (global, CWD-independent).
"""
import click
from rich.console import Console

from bhavai.core.config_store import save_api_key_to_env, get_api_key_from_env

console = Console()


@click.group(name="config", invoke_without_command=True)
@click.pass_context
def config_group(ctx):
    """Manage API keys stored globally with the BhavAI package."""
    if ctx.invoked_subcommand is None:
        console.print(
            "[yellow]Usage:[/yellow] bhav config set <KEY> <VALUE>  |  bhav config get <KEY>"
        )


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """
    Example: bhav config set SARVAM_API_KEY sk_bhavi_ki_api_key
    """
    env_path = save_api_key_to_env(key, value)
    console.print(
        f"[bold green]✓ Saved[/bold green] [cyan]{key}[/cyan] to [bold]{env_path}[/bold]"
    )


@config_group.command(name="get")
@click.argument("key")
def config_get(key):
    """
    Example: bhav config get SARVAM_API_KEY
    """
    value = get_api_key_from_env(key)
    if value is None:
        console.print(f"[red]✗ '{key}' not found in bhavai's .env[/red]")
    else:
        console.print(f"[bold]{key}[/bold] = {value}")