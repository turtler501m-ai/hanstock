import json
import hashlib
from pathlib import Path

import requests

from src.config import config
from src.strategy.features import FEATURE_VERSION, feature_contributions
from src.utils.logger import logger


class ModelPredictor:
    def __init__(self):
        self.enabled = bool(getattr(config, "ai_strategy_enabled", False))
        self.score_weight = max(0.0, min(1.0, float(getattr(config, "ai_score_weight", 0.4))))
        self.min_confidence = float(getattr(config, "ai_min_model_confidence", 0.6))
        self.provider = "openai_responses"
        self.model_name = str(getattr(config, "openai_model", "gpt-5-mini") or "gpt-5-mini")
        self.api_key = str(getattr(config, "openai_api_key", "") or "").strip()
        self.timeout_seconds = float(getattr(config, "openai_timeout_seconds", 20.0) or 20.0)
        self.cache_path = Path(".runtime") / "openai_ai_cache.json"
        self.cache_ttl_seconds = 86400
        self.model_status = "ready" if self.api_key else "fallback"
        self.fallback_reason = "" if self.api_key else "OPENAI_API_KEY not configured"

    def _cache_key(self, features: dict) -> str:
        payload = json.dumps(
            {
                "provider": self.provider,
                "model": self.model_name,
                "feature_version": features.get("feature_version", FEATURE_VERSION),
                "strategy_score": round(float(features.get("strategy_score", 0.0) or 0.0), 4),
                "rsi": round(float(features.get("rsi", 0.0) or 0.0), 4),
                "rsi2": round(float(features.get("rsi2", 0.0) or 0.0), 4),
                "macd_hist": round(float(features.get("macd_hist", 0.0) or 0.0), 6),
                "sma20_gap": round(float(features.get("sma20_gap", 0.0) or 0.0), 6),
                "sma60_gap": round(float(features.get("sma60_gap", 0.0) or 0.0), 6),
                "bb_position": round(float(features.get("bb_position", 0.0) or 0.0), 6),
                "return_5d": round(float(features.get("return_5d", 0.0) or 0.0), 6),
                "return_20d": round(float(features.get("return_20d", 0.0) or 0.0), 6),
                "volatility_20d": round(float(features.get("volatility_20d", 0.0) or 0.0), 6),
                "volume_ratio_20d": round(float(features.get("volume_ratio_20d", 0.0) or 0.0), 6),
                "max_drawdown_20d": round(float(features.get("max_drawdown_20d", 0.0) or 0.0), 6),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, cache: dict) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.info(f"[AI] cache write skipped: {e}")

    def _prompt_payload(self, features: dict, contributions: list[dict]) -> str:
        compact = {
            "strategy_score": round(float(features.get("strategy_score", 0.0) or 0.0), 4),
            "rsi": round(float(features.get("rsi", 0.0) or 0.0), 4),
            "rsi2": round(float(features.get("rsi2", 0.0) or 0.0), 4),
            "macd_hist": round(float(features.get("macd_hist", 0.0) or 0.0), 6),
            "sma20_gap": round(float(features.get("sma20_gap", 0.0) or 0.0), 6),
            "sma60_gap": round(float(features.get("sma60_gap", 0.0) or 0.0), 6),
            "bb_position": round(float(features.get("bb_position", 0.0) or 0.0), 6),
            "return_5d": round(float(features.get("return_5d", 0.0) or 0.0), 6),
            "return_20d": round(float(features.get("return_20d", 0.0) or 0.0), 6),
            "volatility_20d": round(float(features.get("volatility_20d", 0.0) or 0.0), 6),
            "volume_ratio_20d": round(float(features.get("volume_ratio_20d", 0.0) or 0.0), 6),
            "max_drawdown_20d": round(float(features.get("max_drawdown_20d", 0.0) or 0.0), 6),
            "top_features": contributions,
        }
        return json.dumps(compact, ensure_ascii=True)

    def _predict_probability(self, features: dict, contributions: list[dict]) -> float:
        payload = {
            "model": self.model_name,
            "instructions": (
                "You score a Korean stock candidate from 0.0 to 1.0. "
                "Return JSON only with keys probability and rationale. "
                "Probability means short-term buy quality confidence."
            ),
            "input": self._prompt_payload(features, contributions),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "stock_candidate_score",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "probability": {"type": "number", "minimum": 0, "maximum": 1},
                            "rationale": {"type": "string"},
                        },
                        "required": ["probability", "rationale"],
                        "additionalProperties": False,
                    },
                }
            },
        }
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        output_text = body.get("output_text", "")
        if not output_text:
            raise ValueError("OpenAI response missing output_text")
        parsed = json.loads(output_text)
        return max(0.0, min(1.0, float(parsed["probability"])))

    def predict(self, features: dict) -> dict:
        rule_score = float(features.get("strategy_score", 0.0) or 0.0)
        contributions = feature_contributions(features)
        cache_key = self._cache_key(features)
        result = {
            "rule_score": rule_score,
            "ml_score": None,
            "final_score": rule_score,
            "ai_enabled": self.enabled,
            "model_status": self.model_status,
            "model_version": self.model_name,
            "provider": self.provider,
            "feature_version": features.get("feature_version", FEATURE_VERSION),
            "score_weight": 0.0,
            "fallback_reason": None,
            "top_features": contributions,
        }

        if not self.enabled:
            result["model_status"] = "disabled"
            result["fallback_reason"] = "AI_STRATEGY_ENABLED=false"
            return result

        if not self.api_key:
            result["fallback_reason"] = self.fallback_reason
            return result

        cache = self._load_cache()
        cached = cache.get(cache_key)
        if cached and isinstance(cached, dict):
            result.update(
                {
                    "ml_score": cached.get("ml_score"),
                    "final_score": cached.get("final_score", rule_score),
                    "score_weight": cached.get("score_weight", self.score_weight),
                    "model_status": cached.get("model_status", "ready"),
                    "fallback_reason": cached.get("fallback_reason"),
                }
            )
            return result

        try:
            probability = self._predict_probability(features, contributions)
            model_component = probability * 5.0
            final_score = (rule_score * (1 - self.score_weight)) + (model_component * self.score_weight)
            cache[cache_key] = {
                "ml_score": probability,
                "final_score": final_score,
                "score_weight": self.score_weight,
                "model_status": "ready" if probability >= self.min_confidence else "low_confidence",
                "fallback_reason": None,
            }
            self._save_cache(cache)
            result.update(
                {
                    "ml_score": probability,
                    "final_score": final_score,
                    "score_weight": self.score_weight,
                    "model_status": "ready" if probability >= self.min_confidence else "low_confidence",
                }
            )
        except Exception as e:
            logger.error(f"[AI] OpenAI prediction error: {e}")
            result["model_status"] = "fallback"
            result["fallback_reason"] = str(e)
        return result

    def predict_score(self, features: dict) -> float:
        return float(self.predict(features)["final_score"])
