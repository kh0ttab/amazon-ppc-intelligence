"""Seasonality & event calendar with automatic alerts."""

import logging
from datetime import datetime, date, timedelta
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config, AMAZON_EVENTS

logger = logging.getLogger(__name__)
console = Console()

# Historical CPC inflation data (approximate multipliers during peak events)
CPC_INFLATION = {
    "Prime Day": 1.4,
    "Black Friday": 1.6,
    "Cyber Monday": 1.5,
    "Christmas": 1.3,
    "Q4 Peak": 1.35,
    "Valentine's Day": 1.1,
    "Mother's Day": 1.15,
    "Back to School": 1.2,
}


class SeasonalityAnalyzer:
    """Amazon event calendar and seasonality alerts."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.alert_days = self.config.get("seasonality_alert_days", 21)

    def get_upcoming_events(self, days_ahead: int = 60) -> list[dict]:
        """Get upcoming Amazon events within the specified window."""
        today = date.today()
        current_year = today.year
        upcoming = []

        for event in AMAZON_EVENTS:
            # Check this year and next year
            for year in [current_year, current_year + 1]:
                try:
                    event_date = date(year, event["month"], event["day"])
                except ValueError:
                    continue

                days_until = (event_date - today).days

                if 0 <= days_until <= days_ahead:
                    cpc_mult = CPC_INFLATION.get(event["name"], 1.0)
                    upcoming.append({
                        "name": event["name"],
                        "date": event_date,
                        "days_until": days_until,
                        "budget_increase": event["budget_increase"],
                        "bid_increase": event["bid_increase"],
                        "cpc_inflation": cpc_mult,
                        "alert": days_until <= self.alert_days,
                    })

        return sorted(upcoming, key=lambda x: x["days_until"])

    def get_alerts(self) -> list[dict]:
        """Get actionable alerts for upcoming events."""
        events = self.get_upcoming_events(days_ahead=self.alert_days + 7)
        alerts = []

        for event in events:
            if event["days_until"] <= self.alert_days:
                urgency = "HIGH" if event["days_until"] <= 7 else "MEDIUM" if event["days_until"] <= 14 else "LOW"

                alert = {
                    "event": event["name"],
                    "days_until": event["days_until"],
                    "urgency": urgency,
                    "message": (
                        f"{event['name']} in {event['days_until']} days! "
                        f"Recommend: budgets +{event['budget_increase']}%, "
                        f"bids +{event['bid_increase']}%"
                    ),
                    "actions": [],
                }

                if event["days_until"] <= 7:
                    alert["actions"] = [
                        f"Increase daily budgets by {event['budget_increase']}% NOW",
                        f"Raise bids by {event['bid_increase']}% on top performers",
                        f"Expect CPC inflation of ~{int((event['cpc_inflation']-1)*100)}%",
                        "Ensure inventory levels can handle increased orders",
                        "Activate any paused discovery campaigns",
                    ]
                elif event["days_until"] <= 14:
                    alert["actions"] = [
                        "Review and expand keyword lists",
                        f"Plan budget increase of +{event['budget_increase']}%",
                        "Prepare bid rule adjustments",
                        "Stock check - ensure 30+ days inventory",
                    ]
                else:
                    alert["actions"] = [
                        "Start building campaign structure for event",
                        "Research event-specific keywords",
                        "Review last year's performance during this period",
                        f"Budget reserve: set aside +{event['budget_increase']}% of weekly spend",
                    ]

                alerts.append(alert)

        return alerts

    def display_calendar(self) -> None:
        """Display upcoming Amazon events calendar."""
        events = self.get_upcoming_events(days_ahead=90)

        if not events:
            console.print("[dim]No major events in the next 90 days.[/dim]")
            return

        table = Table(title="Amazon Event Calendar (Next 90 Days)", show_lines=True)
        table.add_column("Event", style="bold")
        table.add_column("Date", style="cyan")
        table.add_column("Days Away", justify="right")
        table.add_column("Budget +%", justify="right")
        table.add_column("Bid +%", justify="right")
        table.add_column("CPC Inflation", justify="right")
        table.add_column("Status")

        for event in events:
            days = event["days_until"]

            if days <= 7:
                status = "[bold red]URGENT[/bold red]"
                day_color = "red"
            elif days <= 14:
                status = "[yellow]PREPARE[/yellow]"
                day_color = "yellow"
            elif days <= 21:
                status = "[cyan]PLAN[/cyan]"
                day_color = "cyan"
            else:
                status = "[dim]Upcoming[/dim]"
                day_color = "dim"

            inflation_str = f"+{int((event['cpc_inflation']-1)*100)}%" if event["cpc_inflation"] > 1 else "Normal"

            table.add_row(
                event["name"],
                str(event["date"]),
                f"[{day_color}]{days}[/{day_color}]",
                f"+{event['budget_increase']}%",
                f"+{event['bid_increase']}%",
                inflation_str,
                status,
            )

        console.print(table)

    def display_alerts(self) -> None:
        """Display actionable seasonality alerts."""
        alerts = self.get_alerts()

        if not alerts:
            console.print("[green]No upcoming event alerts. Operations normal.[/green]")
            return

        for alert in alerts:
            urgency_colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan"}
            color = urgency_colors.get(alert["urgency"], "white")

            console.print(Panel(
                f"[bold]{alert['message']}[/bold]",
                title=f"[{color}]{alert['urgency']} PRIORITY[/{color}] - {alert['event']}",
                border_style=color,
            ))

            if alert["actions"]:
                for i, action in enumerate(alert["actions"]):
                    console.print(f"  [{color}]{i+1}.[/{color}] {action}")
            console.print()

    def check_startup_alerts(self) -> list[dict]:
        """Quick check for events to show at app startup."""
        return [a for a in self.get_alerts() if a["urgency"] in ("HIGH", "MEDIUM")]
