"""
LLM Client Wrapper
封装 OpenAI/DeepSeek 客户端，提供统一的调用接口
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config_loader import get_config
from core.llm.utils import parse_messages_to_str, parse_response_to_str


def get_llm_client() -> OpenAI:
    """获取 DeepSeek LLM 客户端"""
    config = get_config()
    return OpenAI(
        api_key=config["deepseek"]["api_key"],
        base_url=config["deepseek"]["base_url"]
    )


def get_model_name() -> str:
    """获取模型名称"""
    config = get_config()
    return config.get("deepseek", {}).get("model", "deepseek-chat")


class LLMClient:
    """LLM 客户端封装类"""

    def __init__(self, model: Optional[str] = None):
        self.client = get_llm_client()
        self.model = model or get_model_name()
        self._log_path = self._get_log_path()

    def _get_log_path(self) -> str:
        """获取日志路径"""
        try:
            config = get_config()
            log_path = config.get("llm_log_path", "tests/llm.log")
            # 确保目录存在
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            return log_path
        except Exception:
            return "tests/llm.log"

    def _log(self, messages: List[Dict[str, str]], response: Any, duration_ms: float = 0):
        """记录 LLM 请求和响应到日志文件"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "messages": messages,
                "response": response,
                "duration_ms": duration_ms
            }
            output_lines = [
                f">>> model <{self.model}> generated at <{datetime.now().isoformat()}>:",
                f"- query:",
                parse_messages_to_str(messages),
                f"- response:",
                parse_response_to_str(response),
                f"- duration <{duration_ms}> ms",
                ""
            ]
            output_text = "\n".join(output_lines)
            with open(self._log_path, "a", encoding="utf-8") as f:
                print(f"output to log: {type(output_text)}")
                f.write(output_text)
        except Exception as e:
            print(f"[WARN] Failed to write LLM log: {e}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """发送对话请求，返回内容"""
        start_time = datetime.now()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        content = resp.choices[0].message.content
        self._log(messages, {"content": content}, duration_ms)
        return content

    def chat_with_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        **kwargs
    ) -> dict:
        """发送对话请求，返回解析后的 JSON"""
        start_time = datetime.now()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                response_format={'type': 'json_object'},
                **kwargs
            )
            content = resp.choices[0].message.content
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Handle empty response
            if not content or not content.strip():
                print(f"[WARN] LLM returned empty response")
                self._log(messages, {"content": "", "error": "empty response"}, duration_ms)
                return {}

            # Try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            # Parse JSON
            result = json.loads(content.strip())
            self._log(messages, result, duration_ms)
            return result

        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parsing failed: {e}")
            print(f"[DEBUG] Raw response: {content if 'content' in dir() else 'N/A'}")
            self._log(messages, {"error": str(e)}, duration_ms)
            return {}
        except Exception as e:
            print(f"[ERROR] LLM request failed: {e}")
            self._log(messages, {"error": str(e)}, duration_ms)
            return {}

    def extract_keywords(self, question: str, max_count: int = 3) -> List[str]:
        """提取问题中的关键词"""
        prompt = f"从以下问题中提取{max_count}个医学/健康实体关键词，只返回JSON列表格式：\n问题：{question}"
        messages = [{"role": "user", "content": prompt}]
        try:
            content = self.chat(messages, temperature=0.1)
            import re
            match = re.search(r'\[.*\]', content)
            if match:
                return json.loads(match.group())
            return []
        except Exception as e:
            print(f"关键词提取失败: {e}")
            return []


# 全局客户端实例
_llm_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    """获取全局 LLM 客户端实例"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
