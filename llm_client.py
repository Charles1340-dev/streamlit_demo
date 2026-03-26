from __future__ import annotations

import json
import os
from typing import Any, Dict

from openai import OpenAI

from prompts import ANALYSIS_PLAN_SYSTEM_PROMPT, INSIGHT_SYSTEM_PROMPT


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
    ) -> None:
        raw_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        self.api_key = (raw_key or "").strip()
        self.model = (model or "deepseek-chat").strip()
        self.base_url = (base_url or "https://api.deepseek.com").strip()
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @property
    def is_configured(self) -> bool:
        return bool(self.client)

    def _require_client(self) -> OpenAI:
        if not self.client:
            raise RuntimeError("未配置 DeepSeek API Key")
        return self.client

    def _json_loads(self, text: str) -> Dict[str, Any]:
        cleaned = (text or "{}").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned or "{}")

    def generate_analysis_plan(
        self,
        user_question: str,
        df_profile: Dict[str, Any],
        file_name: str = "",
    ) -> Dict[str, Any]:
        client = self._require_client()
        payload = {
            "file_name": file_name,
            "user_question": user_question,
            "row_count": df_profile["row_count"],
            "column_count": df_profile["column_count"],
            "numeric_fields": df_profile["numeric_fields"],
            "date_fields": df_profile["date_fields"],
            "categorical_fields": df_profile["categorical_fields"],
            "text_fields": df_profile.get("text_fields", []),
            "columns": df_profile["columns"][:80],
        }

        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": ANALYSIS_PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请基于下面的数据画像，为这个问题生成 json 分析计划。\n"
                        f"问题：{user_question}\n"
                        f"数据画像：{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return self._json_loads(content)

    def generate_insights(
        self,
        user_question: str,
        analysis_result: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        client = self._require_client()
        payload = {
            "user_question": user_question,
            "plan": plan,
            "stats": analysis_result.get("stats", {}),
            "summary": analysis_result.get("summary", ""),
            "key_findings": analysis_result.get("key_findings", []),
            "management_takeaways": analysis_result.get("management_takeaways", []),
            "risks": analysis_result.get("risks", []),
        }
        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=850,
            messages=[
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "请根据下面的分析结果，生成 json 格式结论。\n"
                    + json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return self._json_loads(content)
