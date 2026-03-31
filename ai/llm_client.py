"""Local LLM integration via Ollama API."""

import json
import logging
import sys
from typing import Generator, Optional

import requests
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

import pandas as pd
from config import load_config

logger = logging.getLogger(__name__)
console = Console()

SYSTEM_PROMPT = """Ты эксперт по Amazon PPC с 20-летним опытом управления
Sponsored Products, Sponsored Brands и Sponsored Display кампаниями.

Всегда отвечай на русском языке. Будь конкретным,
используй реальные цифры из данных продавца.
Каждый совет: конкретное действие — что сделать,
в какой кампании, какую ставку поставить.
Говори как опытный менеджер, не как робот.

Твоя экспертиза:
- Оптимизация ключевых слов и ставок
- Стратегии ACoS/ROAS оптимизации
- Структура кампаний и распределение бюджета
- Анализ конкурентов и позиционирование
- Стратегия органических vs PPC продаж
- Понимание алгоритма Amazon A9/A10

У тебя есть доступ к реальным данным продавца.
Всегда ссылайся на конкретные цифры из данных.
Давай конкретные рекомендации с суммами в долларах,
процентами и действиями на уровне ключевых слов.

При анализе данных:
- Выявляй паттерны и тренды
- Сразу отмечай критические проблемы
- Приоритизируй по импакту (сначала самые большие потери)
- Давай пошаговые действия
- Учитывай краткосрочные фиксы и долгосрочную стратегию"""

QUICK_PROMPTS = {
    "1": {
        "label": "Худшие кампании и ключи",
        "prompt": "Проанализируй худшие кампании и ключевые слова из моих данных. "
                  "Какие кампании имеют самый высокий ACoS и самый низкий ROAS? "
                  "Дай конкретные действия для каждой.",
    },
    "2": {
        "label": "Какие ключи остановить сегодня?",
        "prompt": "На основе моих данных, какие ключевые слова нужно остановить немедленно? "
                  "Сфокусируйся на ключах с высокими тратами и нулём заказов, или очень высоким ACoS. "
                  "Перечисли их с суммой трат и причиной остановки.",
    },
    "3": {
        "label": "Где я теряю бюджет?",
        "prompt": "Найди все области где я теряю рекламный бюджет. "
                  "Включи: ключи без конверсий, высокий ACoS, неправильные типы соответствия, "
                  "и проблемы структуры кампаний. Посчитай общую сумму потерь.",
    },
    "4": {
        "label": "Стратегия масштабирования",
        "prompt": "На основе моих выигрышных ключей и кампаний, предложи стратегию масштабирования. "
                  "На каких ключах повысить ставки? Какие новые кампании создать? "
                  "Как перераспределить бюджет от убыточных к прибыльным?",
    },
    "5": {
        "label": "Анализ органика vs PPC",
        "prompt": "Проанализируй соотношение органических и PPC продаж. "
                  "Помогает ли реклама растить органику? Какой тренд TACoS? "
                  "Слишком ли я зависим от PPC? Предложи стратегию улучшения "
                  "органических позиций с сохранением эффективности PPC.",
    },
}


class LLMClient:
    """Client for Ollama local LLM integration."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.endpoint = self.config["ollama_endpoint"]
        self.model = self.config["ollama_model"]
        self.conversation_history: list[dict] = []

    def check_connection(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.ConnectionError:
            return False
        except Exception:
            return False

    def check_model_available(self) -> bool:
        """Check if the configured model is available in Ollama."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(m.get("name", "").startswith(self.model.split(":")[0]) for m in models)
            return False
        except Exception:
            return False

    def build_data_context(self, data: Optional[pd.DataFrame], limit: int = 20) -> str:
        """Build a data context string from the top keywords by spend."""
        if data is None or len(data) == 0:
            return "No campaign data currently loaded."

        context_parts = ["CURRENT CAMPAIGN DATA (Top keywords by spend):"]

        # Sort by spend and take top N
        sort_col = "Spend" if "Spend" in data.columns else data.columns[0]
        top_data = data.nlargest(limit, sort_col) if sort_col in data.columns else data.head(limit)

        keyword_col = "Customer Search Term" if "Customer Search Term" in data.columns else data.columns[0]

        for _, row in top_data.iterrows():
            line_parts = [f"Keyword: {row.get(keyword_col, 'N/A')}"]
            for col in ["Spend", "Sales", "Orders", "ACoS", "ROAS", "Clicks", "Impressions", "CPC", "Conv_Rate", "Status"]:
                if col in row.index:
                    val = row[col]
                    if col in ["Spend", "Sales", "CPC"]:
                        line_parts.append(f"{col}: ${val:.2f}")
                    elif col in ["ACoS", "Conv_Rate"]:
                        line_parts.append(f"{col}: {val:.1f}%")
                    elif col == "ROAS":
                        line_parts.append(f"ROAS: {val:.2f}x")
                    else:
                        line_parts.append(f"{col}: {val}")
            context_parts.append(" | ".join(line_parts))

        # Add summary stats
        if "Spend" in data.columns:
            total_spend = data["Spend"].sum()
            total_sales = data["Sales"].sum() if "Sales" in data.columns else 0
            total_orders = data["Orders"].sum() if "Orders" in data.columns else 0
            overall_acos = (total_spend / total_sales * 100) if total_sales > 0 else 0

            context_parts.append(f"\nSUMMARY: Total Spend=${total_spend:.2f}, "
                                 f"Total Sales=${total_sales:.2f}, "
                                 f"Total Orders={total_orders:.0f}, "
                                 f"Overall ACoS={overall_acos:.1f}%, "
                                 f"Total Keywords={len(data)}")

        return "\n".join(context_parts)

    def chat(
        self,
        user_message: str,
        data_context: str = "",
        stream: bool = True,
    ) -> str:
        """Send a message to the LLM and get a response.

        Args:
            user_message: The user's question or prompt
            data_context: Current data context to inject
            stream: Whether to stream the response in real-time
        """
        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if data_context:
            messages.append({
                "role": "system",
                "content": f"SELLER'S DATA CONTEXT:\n{data_context}",
            })

        # Add conversation history (keep last 10 exchanges)
        messages.extend(self.conversation_history[-20:])

        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }

        try:
            if stream:
                full_response = self._stream_response(payload)
            else:
                response = requests.post(
                    f"{self.endpoint}/api/chat",
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()
                full_response = result.get("message", {}).get("content", "")
                console.print(Markdown(full_response))

        except requests.ConnectionError:
            console.print("[red]Cannot connect to Ollama. Is it running?[/red]")
            console.print("[dim]Start Ollama with: ollama serve[/dim]")
            return ""
        except requests.Timeout:
            console.print("[red]LLM request timed out. Try a simpler question.[/red]")
            return ""
        except Exception as e:
            console.print(f"[red]LLM error: {e}[/red]")
            logger.error(f"LLM error: {e}")
            return ""

        # Save to history
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": full_response})

        return full_response

    def _stream_response(self, payload: dict) -> str:
        """Stream LLM response to terminal in real-time."""
        response = requests.post(
            f"{self.endpoint}/api/chat",
            json=payload,
            stream=True,
            timeout=120,
        )
        response.raise_for_status()

        full_text = ""
        console.print()  # Newline before response

        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_text += token
                        sys.stdout.write(token)
                        sys.stdout.flush()

                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

        console.print()  # Newline after response
        return full_text

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        console.print("[dim]Conversation history cleared.[/dim]")

    def get_quick_prompts(self) -> dict:
        """Get available quick analysis prompts."""
        return QUICK_PROMPTS
