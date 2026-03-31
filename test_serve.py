"""Minimal test app for textual-serve debugging."""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Button
from textual.containers import Vertical


class TestApp(App):
    CSS = """
    #main { padding: 2 4; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Static("Hello from Amazon PPC Intelligence!")
            yield Static("If you can see this, textual-serve works.")
            yield Button("Click me", id="test-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one("#main").mount(Static("[green]Button clicked![/green]"))


if __name__ == "__main__":
    app = TestApp()
    app.run()
