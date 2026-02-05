"""
LLM Client Wrapper
封装 OpenAI/DeepSeek 客户端，提供统一的调用接口
"""
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config_loader import get_config


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

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """发送对话请求，返回内容"""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return resp.choices[0].message.content

    def chat_with_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        **kwargs
    ) -> dict:
        """发送对话请求，返回解析后的 JSON"""
        content = self.chat(messages, temperature=temperature, **kwargs)
        # 尝试从 markdown 代码块中提取 JSON
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            content = json_match.group(1)
        return json.loads(content.strip())

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
