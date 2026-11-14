"""Gemini model ladder: strongest model first; rate-limit / unavailable / overloaded models
cool down and the request drops one rung. Every decision is written to the trace."""
import time
from dataclasses import dataclass, field

from app import config

RETRYABLE = {429, 500, 502, 503, 504}
MISSING = {404}


@dataclass
class LLMResult:
    text: str
    calls: list = field(default_factory=list)  # [{"name": str, "args": dict}]
    model: str = ""
    content: object = None                      # provider-native message, to append to history
    tokens: dict = field(default_factory=dict)  # {"prompt": int, "output": int} when the provider reports usage


class AllModelsLimited(Exception):
    def __init__(self, retry_after_s: float):
        super().__init__(f"all models are rate-limited or unavailable; retry in ~{int(retry_after_s)}s")
        self.retry_after_s = retry_after_s


class Ladder:
    def __init__(self, models, call, tracer, clock=time.monotonic, cooldown_s: float = 60.0):
        self.models, self.call, self.tracer, self.clock, self.cooldown_s = models, call, tracer, clock, cooldown_s
        self.cooling_until = {}

    def generate(self, run_id, contents, system=None, tools=None) -> LLMResult:
        now, tried = self.clock(), 0
        for i, m in enumerate(self.models):
            if self.cooling_until.get(m, 0) > now:
                continue
            tried += 1
            t0 = time.time()
            try:
                res = self.call(m, contents, system, tools)
            except Exception as e:  # noqa: BLE001
                code = getattr(e, "code", None)
                if code not in RETRYABLE and code not in MISSING:
                    raise
                self.cooling_until[m] = now + (3600 if code in MISSING else self.cooldown_s * (3 if code == 504 else 1))
                self.tracer.step(run_id, "fallback", m, dict(code=code, error=str(e)[:200],
                                                             cooling_s=self.cooling_until[m] - now),
                                 model=m, ms=int((time.time() - t0) * 1000))
                continue
            res.model = m
            self.tracer.step(run_id, "model", m, dict(rung=i, calls=[c["name"] for c in res.calls],
                                                      reason="primary" if i == 0 else "fallback rung", tokens=res.tokens),
                             model=m, ms=int((time.time() - t0) * 1000))
            return res
        waits = [t - now for t in self.cooling_until.values() if t > now]
        raise AllModelsLimited(min(waits) if waits else self.cooldown_s)


def gemini_call(api_key: str = None, timeout_ms: int = 20000):
    """Provider adapter: returns call(model, contents, system, tools) -> LLMResult."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key or config.GEMINI_API_KEY,
                          http_options=types.HttpOptions(timeout=timeout_ms))

    def call(model, contents, system=None, tools=None):
        cfg = types.GenerateContentConfig(
            system_instruction=system, tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        r = client.models.generate_content(model=model, contents=contents, config=cfg)
        cand = r.candidates[0].content if r.candidates else None
        parts = (cand.parts or []) if cand else []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        calls = [dict(name=p.function_call.name, args=dict(p.function_call.args or {}))
                 for p in parts if getattr(p, "function_call", None)]
        u = getattr(r, "usage_metadata", None)
        tokens = dict(prompt=getattr(u, "prompt_token_count", 0) or 0,
                      output=getattr(u, "candidates_token_count", 0) or 0) if u else {}
        return LLMResult(text=text, calls=calls, model=model, content=cand, tokens=tokens)
    return call
