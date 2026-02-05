"""
Agent Base Class
All specialized agents inherit from this base class.
Provides common interface, LLM client, and knowledge graph integration.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, TypeVar, Type
from pydantic import BaseModel

from core.llm import LLMClient, get_llm
from core.neo4j import Neo4jClient, KnowledgeGraphQuery, get_neo4j, get_kg_query
from config_loader import get_config


# ================= Configuration =================

class UserMetadata(BaseModel):
    """Common user metadata for all agents"""
    age: int
    gender: str
    height_cm: float
    weight_kg: float
    medical_conditions: List[str] = []
    dietary_restrictions: List[str] = []
    fitness_level: str = "beginner"  # beginner, intermediate, advanced


class EnvironmentContext(BaseModel):
    """Environment context for plan generation"""
    weather: Dict[str, Any] = {}
    time_context: Dict[str, Any] = {}


class AgentInput(BaseModel):
    """Common input structure for all agents"""
    user_metadata: UserMetadata
    environment: EnvironmentContext = EnvironmentContext()
    user_requirement: Dict[str, Any] = {}


T = TypeVar("T", bound=BaseModel)


# ================= Base Agent Class =================

class BaseAgent(ABC):
    """
    Abstract base class for all health recommendation agents.

    Usage:
        class DietAgent(BaseAgent):
            def generate(self, input: AgentInput) -> List[DietRecommendation]:
                ...

        agent = DietAgent()
        result = agent.generate(input_data)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        neo4j_client: Optional[Neo4jClient] = None,
        kg_query: Optional[KnowledgeGraphQuery] = None
    ):
        """Initialize agent with dependencies"""
        self._llm = llm_client or get_llm()
        self._neo4j = neo4j_client or get_neo4j()
        self._kg = kg_query or get_kg_query()
        self._config = get_config()

    @property
    def llm(self) -> LLMClient:
        """Access LLM client"""
        return self._llm

    @property
    def neo4j(self) -> Neo4jClient:
        """Access Neo4j client"""
        return self._neo4j

    @property
    def kg(self) -> KnowledgeGraphQuery:
        """Access knowledge graph query utilities"""
        return self._kg

    @property
    def config(self) -> dict:
        """Access configuration"""
        return self._config

    @abstractmethod
    def get_agent_name(self) -> str:
        """Return the name of this agent"""
        pass

    @abstractmethod
    def get_input_type(self) -> Type[BaseModel]:
        """Return the expected input type for this agent"""
        pass

    @abstractmethod
    def get_output_type(self) -> Type[BaseModel]:
        """Return the output type for this agent"""
        pass

    @abstractmethod
    def generate(
        self,
        input_data: Dict[str, Any],
        num_candidates: int = 3
    ) -> List[BaseModel]:
        """
        Generate candidates based on input.

        Args:
            input_data: Dictionary containing user_metadata, environment, user_requirement
            num_candidates: Number of candidates to generate

        Returns:
            List of candidate objects
        """
        pass

    def _get_kg_context(self, query_type: str, **kwargs) -> str:
        """
        Get relevant knowledge graph context for a query type.

        Subclasses can override to provide specific KG context.
        """
        return ""

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Type[T]] = None,
        temperature: float = 0.7
    ) -> Any:
        """
        Call LLM with system and user prompts.

        Args:
            system_prompt: System prompt defining behavior
            user_prompt: User prompt with input data
            response_format: Optional Pydantic model for structured output
            temperature: LLM temperature (0.0-1.0)

        Returns:
            LLM response (string or parsed model)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if response_format:
            return self._llm.chat_with_json(
                messages,
                temperature=temperature
            )
        else:
            return self._llm.chat(messages, temperature=temperature)

    def _validate_input(self, input_data: Dict[str, Any]) -> AgentInput:
        """Validate and normalize input data"""
        return AgentInput(**input_data)


# ================= Specialized Agent Mixins =================

class DietAgentMixin:
    """Mixin for diet-related agent capabilities"""

    def query_dietary_knowledge(
        self,
        conditions: List[str],
        restrictions: List[str] = []
    ) -> Dict[str, Any]:
        """Query knowledge graph for dietary recommendations"""
        results = {
            "recommended_foods": [],
            "restricted_foods": [],
            "nutrient_advice": []
        }

        for condition in conditions:
            # Query recommended foods
            foods = self._kg.query_foods_by_disease(condition)
            results["recommended_foods"].extend([dict(r) for r in foods])

            # Query restrictions
            restrictions_data = self._kg.query_dietary_restrictions(condition)
            results["restricted_foods"].extend([dict(r) for r in restrictions_data])

            # Query nutrient advice
            nutrients = self._kg.query_nutrient_advice(condition)
            results["nutrient_advice"].extend([dict(r) for r in nutrients])

        return results

    def calculate_target_calories(
        self,
        age: int,
        gender: str,
        height_cm: float,
        weight_kg: float,
        goal: str = "maintenance",
        activity_factor: float = 1.2
    ) -> int:
        """Calculate target daily calories using Harris-Benedict formula"""
        # BMR calculation
        if gender.lower() == "male":
            bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
        else:
            bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)

        # TDEE
        tdee = bmr * activity_factor

        # Goal adjustment
        adjustments = {
            "weight_loss": -500,
            "weight_gain": 500,
            "muscle_building": 300,
            "maintenance": 0
        }

        return int(tdee + adjustments.get(goal, 0))


class ExerciseAgentMixin:
    """Mixin for exercise-related agent capabilities"""

    def query_exercise_knowledge(
        self,
        conditions: List[str],
        fitness_level: str = "beginner"
    ) -> Dict[str, Any]:
        """Query knowledge graph for exercise recommendations"""
        # Placeholder - knowledge graph needs exercise data
        return {
            "recommended_exercises": [],
            "avoid_exercises": [],
            "intensity_recommendations": []
        }

    def estimate_calories_burned(
        self,
        exercise_type: str,
        duration_minutes: int,
        weight_kg: float,
        intensity: str = "moderate"
    ) -> int:
        """Estimate calories burned for an exercise (MET-based)"""
        met_values = {
            "walking": {"low": 2.5, "moderate": 3.5, "high": 5.0},
            "running": {"low": 6.0, "moderate": 8.0, "high": 11.5},
            "swimming": {"low": 5.0, "moderate": 7.0, "high": 9.0},
            "cycling": {"low": 4.0, "moderate": 6.0, "high": 8.0},
            "strength_training": {"low": 3.0, "moderate": 5.0, "high": 6.0},
            "yoga": {"low": 2.0, "moderate": 3.0, "high": 4.0}
        }

        met = met_values.get(exercise_type, {}).get(intensity, 5.0)
        calories_per_minute = (met * 3.5 * weight_kg) / 200
        return int(calories_per_minute * duration_minutes)


# ================= Agent Registry =================

_AGENT_REGISTRY: Dict[str, Type[BaseAgent]] = {}


def register_agent(agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
    """Decorator to register an agent class"""
    name = getattr(agent_class, "AGENT_NAME", None)
    if name is None:
        # Try to get from get_agent_name method
        if hasattr(agent_class, "get_agent_name"):
            # Can't call it here, use class attribute
            pass
    _AGENT_REGISTRY[agent_class.__name__] = agent_class
    return agent_class


def get_agent(name: str) -> Optional[BaseAgent]:
    """Get an agent instance by name"""
    agent_class = _AGENT_REGISTRY.get(name)
    if agent_class:
        return agent_class()
    return None


def list_agents() -> List[str]:
    """List all registered agent names"""
    return list(_AGENT_REGISTRY.keys())
