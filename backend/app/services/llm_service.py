from __future__ import annotations

import json
import re
from typing import Any

from backend.app.core.config import Settings
from backend.app.schemas.llm import LLMGenerationResult, LLMProvider
from backend.app.schemas.prompt import PromptBuildResult, PromptMessage


class LLMServiceError(RuntimeError):
    """Lỗi cơ sở của dịch vụ LLM."""


class LLMConfigurationError(LLMServiceError):
    """Lỗi cấu hình nhà cung cấp hoặc API key."""


class LLMProviderError(LLMServiceError):
    """Lỗi khi gọi nhà cung cấp LLM."""


class LLMEmptyResponseError(LLMServiceError):
    """LLM không trả về nội dung hợp lệ."""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def generate(self, prompt: PromptBuildResult) -> LLMGenerationResult:
        if self.settings.llm_provider != LLMProvider.GEMINI.value:
            raise LLMConfigurationError(
                f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}."
            )

        if not self.settings.gemini_api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not configured in .env.")

        user_message = _first_message(prompt.messages, "user")
        if user_message is None:
            raise LLMConfigurationError(
                "Prompt Builder did not provide a user message for the LLM."
            )

        response_text, usage = self._generate_with_gemini(
            system_instruction=prompt.system_instruction,
            user_content=user_message.content,
        )

        parsed_output = _parse_json_object(response_text)
        answer = _parsed_string(parsed_output, "answer") or response_text
        citations = _parsed_list(parsed_output, "citations") or _extract_citation_refs(
            text=answer,
            allowed_source_ids=prompt.source_ids,
        )

        return LLMGenerationResult(
            provider=LLMProvider.GEMINI,
            model=self.settings.llm_model,
            applied=True,
            temperature=self.settings.llm_temperature,
            max_output_tokens=self.settings.llm_max_output_tokens,
            prompt_estimated_tokens=prompt.estimated_tokens,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            estimated_cost_usd=_estimate_cost_usd(
                usage=usage,
                input_cost_per_1k=self.settings.llm_input_cost_per_1k_tokens,
                output_cost_per_1k=self.settings.llm_output_cost_per_1k_tokens,
            ),
            raw_text=response_text,
            parsed_output=parsed_output,
            answer=answer,
            citations=citations,
            confidence_label=_parsed_string(parsed_output, "confidence"),
            warning=_parsed_string(parsed_output, "warning"),
            note="Gemini response generated from the Prompt Builder output.",
        )

    def generate_answer(self, question: str, context: str) -> str:
        prompt_text = "\n\n".join(
            [
                "CÂU HỎI NGƯỜI DÙNG:\n" + question,
                "CONTEXT:\n" + context,
                "QUY TẮC TRẢ LỜI:\n"
                "1. Chỉ trả lời dựa trên tài liệu được cung cấp.\n"
                "2. Không tự tạo điều luật, mức thuế hoặc số hiệu văn bản.\n"
                "3. Không chèn mã nguồn như [SOURCE_1] trực tiếp trong câu trả lời.\n"
                "4. Nếu tài liệu không đủ, phải nói rõ chưa đủ căn cứ.\n"
                "5. Trả lời bằng tiếng Việt, rõ ràng và dễ hiểu.\n"
                "6. Không tự thực hiện phép tính thuế nếu chưa có kết quả từ Tax Calculation Service.",
            ]
        )

        response_text, _usage = self._generate_with_gemini(
            system_instruction=(
                "Bạn là trợ lý giải đáp Thuế Thu nhập cá nhân tại Việt Nam."
            ),
            user_content=prompt_text,
        )
        return response_text

    def _generate_with_gemini(self, system_instruction: str, user_content: str) -> tuple[str, dict[str, int | None]]:
        genai, types = _load_gemini_dependencies()
        client = self._get_client(genai, types)

        try:
            response = client.models.generate_content(
                model=self.settings.llm_model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=self.settings.llm_temperature,
                    max_output_tokens=self.settings.llm_max_output_tokens,
                ),
            )
        except Exception as exc:
            raise LLMProviderError(
                _exception_message("Gemini provider request failed", exc)
            ) from exc

        try:
            response_text = getattr(response, "text", None)
        except Exception as exc:
            raise LLMProviderError(
                _exception_message("Gemini response text extraction failed", exc)
            ) from exc

        if not response_text or not response_text.strip():
            detail = _gemini_empty_response_detail(response)
            raise LLMEmptyResponseError(
                detail or "LLM did not return text content."
            )

        return response_text.strip(), _extract_usage_metadata(response)

    def _get_client(self, genai: Any, types: Any) -> Any:
        if self._client is not None:
            return self._client

        try:
            self._client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=self.settings.llm_timeout_ms),
            )
        except TypeError:
            # Một số version SDK có thể không nhận http_options ở Client.
            try:
                self._client = genai.Client(api_key=self.settings.gemini_api_key)
            except Exception as exc:
                raise LLMProviderError(
                    _exception_message("Failed to initialize Gemini client", exc)
                ) from exc
        except Exception as exc:
            raise LLMProviderError(
                _exception_message("Failed to initialize Gemini client", exc)
            ) from exc

        return self._client


def _load_gemini_dependencies() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ModuleNotFoundError as exc:
        raise LLMConfigurationError(
            "Missing Gemini dependency. Install project requirements first: "
            "python -m pip install -r requirements.txt"
        ) from exc

    return genai, types


def _first_message(messages: list[PromptMessage], role: str) -> PromptMessage | None:
    for message in messages:
        if message.role == role:
            return message
    return None


def _parse_json_object(text: str) -> dict[str, Any] | None:
    candidates = [
        text.strip(),
        _strip_markdown_fence(text),
        _extract_json_object(text),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    return None


def _strip_markdown_fence(text: str) -> str | None:
    match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).strip()


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    return text[start : end + 1].strip()


def _parsed_string(parsed_output: dict[str, Any] | None, key: str) -> str | None:
    if not parsed_output:
        return None

    value = parsed_output.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _parsed_list(parsed_output: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not parsed_output:
        return []

    value = parsed_output.get(key)
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _extract_citation_refs(text: str, allowed_source_ids: list[str]) -> list[dict[str, str]]:
    allowed = set(allowed_source_ids)
    refs = re.findall(r"\[(SOURCE_\d+)\]", text)

    citations: list[dict[str, str]] = []
    seen: set[str] = set()

    for ref in refs:
        if ref in seen:
            continue

        if allowed and ref not in allowed:
            continue

        citations.append({"citation_id": ref})
        seen.add(ref)

    return citations


def _exception_message(prefix: str, exc: Exception) -> str:
    detail = str(exc).strip()
    exc_name = exc.__class__.__name__

    if detail:
        return f"{prefix}: {exc_name}: {detail}"

    return f"{prefix}: {exc_name}"


def _gemini_empty_response_detail(response: Any) -> str | None:
    details: list[str] = []

    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback is not None:
        details.append(f"prompt_feedback={prompt_feedback}")

    candidates = getattr(response, "candidates", None)
    if candidates is not None:
        details.append(f"candidates={candidates}")

    if not details:
        return None

    return "LLM did not return text content. " + " | ".join(details)


def _extract_usage_metadata(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }

    prompt_tokens = _usage_int(
        usage,
        "prompt_token_count",
        "prompt_tokens",
        "input_token_count",
    )
    completion_tokens = _usage_int(
        usage,
        "candidates_token_count",
        "completion_tokens",
        "output_token_count",
    )
    total_tokens = _usage_int(
        usage,
        "total_token_count",
        "total_tokens",
    )
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _usage_int(usage: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _estimate_cost_usd(
    *,
    usage: dict[str, int | None],
    input_cost_per_1k: float,
    output_cost_per_1k: float,
) -> float | None:
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None and completion_tokens is None:
        return None

    cost = ((prompt_tokens or 0) / 1000 * input_cost_per_1k) + (
        (completion_tokens or 0) / 1000 * output_cost_per_1k
    )
    return round(cost, 8)
