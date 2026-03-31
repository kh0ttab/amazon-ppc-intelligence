"""Ollama LLM integration with streaming and auto model fallback."""

import json
from typing import AsyncGenerator

import requests

SYSTEM_PROMPT = """Ты эксперт Amazon PPC с 20-летним опытом. Отвечай только на русском.
Давай конкретные действия с цифрами: какой ключ, какую ставку, какой бюджет.
Говори как опытный менеджер, не как робот. Будь кратким и по делу.
У тебя есть доступ к реальным данным продавца — ссылайся на конкретные цифры."""

QUICK_PROMPTS = {
    "pause": "Какие ключевые слова нужно остановить прямо сейчас? Перечисли с суммой трат и причиной.",
    "scale": "Какие ключи и кампании можно масштабировать? Дай конкретные ставки и бюджеты.",
    "budget": "Где я теряю бюджет? Посчитай общие потери и дай план экономии.",
    "strategy": "Предложи стратегию роста на следующий месяц. Учти текущие данные.",
}

# Preferred model order — try largest first, fall back to smaller
MODEL_PREFERENCE = ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "qwen2.5-coder:7b", "phi3:mini"]


def check_ollama(endpoint: str = "http://localhost:11434") -> dict:
    try:
        r = requests.get(f"{endpoint}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}


def pick_model(endpoint: str = "http://localhost:11434", preferred: str = "qwen2.5:14b") -> str:
    """Pick the best available model, testing that it actually loads."""
    info = check_ollama(endpoint)
    if not info["online"]:
        return preferred

    available = info["models"]

    # Try preferred first
    candidates = [preferred] + [m for m in MODEL_PREFERENCE if m != preferred]

    for model in candidates:
        if any(model.split(":")[0] in a for a in available):
            # Quick test: can it actually run?
            try:
                r = requests.post(
                    f"{endpoint}/api/chat",
                    json={"model": model, "messages": [{"role": "user", "content": "ok"}], "stream": False},
                    timeout=30,
                )
                if r.status_code == 200:
                    return model
            except Exception:
                continue

    # Return first available model as last resort
    return available[0] if available else preferred


def build_data_context(kpis: dict, top_winners: list, top_bleeders: list) -> str:
    lines = [
        f"ДАННЫЕ: Расходы=${kpis['total_spend']:.2f}, Выручка=${kpis['total_sales']:.2f}, "
        f"Заказы={kpis['total_orders']}, ACoS={kpis['acos']}%, ROAS={kpis['roas']}x, "
        f"TACoS={kpis['tacos']}%, Ключей={kpis['total_keywords']}",
    ]
    if top_winners:
        lines.append("\nТОП ПОБЕДИТЕЛИ:")
        for w in top_winners[:5]:
            lines.append(f"  {w['search_term']}: Revenue=${w['sales']:.2f}, ACoS={w['acos']}%")
    if top_bleeders:
        lines.append("\nТОП УБЫТКИ:")
        for b in top_bleeders[:5]:
            lines.append(f"  {b['search_term']}: Spend=${b['spend']:.2f}, Orders={int(b['orders'])}")
    return "\n".join(lines)


async def stream_chat(
    message: str,
    data_context: str = "",
    endpoint: str = "http://localhost:11434",
    model: str = "qwen2.5:14b",
) -> AsyncGenerator[str, None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if data_context:
        messages.append({"role": "system", "content": f"ДАННЫЕ ПРОДАВЦА:\n{data_context}"})
    messages.append({"role": "user", "content": message})

    # Try the requested model, fall back if it fails
    models_to_try = [model]
    for m in MODEL_PREFERENCE:
        if m != model and m not in models_to_try:
            models_to_try.append(m)

    last_error = ""
    for try_model in models_to_try:
        try:
            resp = requests.post(
                f"{endpoint}/api/chat",
                json={"model": try_model, "messages": messages, "stream": True},
                stream=True,
                timeout=120,
            )

            # Check for error response (e.g., out of memory)
            if resp.status_code != 200:
                try:
                    err = resp.json().get("error", resp.text[:200])
                except Exception:
                    err = resp.text[:200]
                last_error = f"{try_model}: {err}"
                continue  # Try next model

            # Stream successful response
            yielded = False
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        # Check for error in stream
                        if "error" in chunk:
                            last_error = f"{try_model}: {chunk['error']}"
                            break
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            if not yielded:
                                yield f"[{try_model}] "
                                yielded = True
                            yield token
                        if chunk.get("done"):
                            return  # Success — stop trying other models
                    except json.JSONDecodeError:
                        continue

            if yielded:
                return  # Already produced output

        except requests.ConnectionError:
            yield "❌ Не удалось подключиться к Ollama. Запустите: ollama serve"
            return
        except Exception as e:
            last_error = str(e)
            continue

    # All models failed
    yield f"❌ Ни одна модель не загрузилась.\nПоследняя ошибка: {last_error}\n\nПопробуйте: ollama pull qwen2.5:7b"
