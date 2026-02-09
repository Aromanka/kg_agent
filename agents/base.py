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
from kg.prompts import DIETARY_QUERY_ENTITIES, EXERCISE_QUERY_ENTITIES


        # Stop words to filter out from query
stop_words = {
    "i", "want", "a", "the", "with", "and", "or", "for", "to",
    "my", "me", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can",
    "this", "that", "these", "those", "it", "they", "them", "their",
    "on", "in", "at", "by", "from", "as", "of", "an", "like"
}

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
        temperature: float = 0.7,
        top_p: float = 0.92,
        top_k: int = 50
    ) -> Any:
        """
        Call LLM with system and user prompts.

        Args:
            system_prompt: System prompt defining behavior
            user_prompt: User prompt with input data
            response_format: Optional Pydantic model for structured output
            temperature: LLM temperature (0.0-1.0)
            top_p: LLM top_p for nucleus sampling (0.0-1.0)
            top_k: LLM top_k for top-k sampling

        Returns:
            LLM response (string or parsed model)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f" calling llm with temp={temperature}, top_p={top_p}, top_k={top_k}")
        if response_format:
            return self._llm.chat_with_json(
                messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k)
        else:
            return self._llm.chat(messages, temperature=temperature, top_p=top_p, top_k=top_k)

    def _validate_input(self, input_data: Dict[str, Any]) -> AgentInput:
        """Validate and normalize input data"""
        return AgentInput(**input_data)


# ================= Specialized Agent Mixins =================

class DietAgentMixin:
    """Mixin for diet-related agent capabilities"""

    def query_dietary_knowledge(
        self,
        conditions: List[str],
        restrictions: List[str] = [],
        cared_rels: List[str] = None
    ) -> List[Dict]:
        """Query knowledge graph for dietary recommendations"""
        results = []

        # Combine conditions and restrictions for unified search
        all_entities = list(set(conditions + restrictions + DIETARY_QUERY_ENTITIES))

        # Use universal search for all entities
        for entity in all_entities:
            try:
                search_results = self._kg.search_entities(entity)
                all_rel_types = []

                # Classify results based on relation types
                for result in search_results:
                    entity_name = result.get("head", "")
                    tail = result.get("tail", "")
                    rel_type = result.get("rel_type", "")
                    if cared_rels is not None and rel_type not in cared_rels:
                        continue
                    all_rel_types.append(rel_type)

                    if not tail:
                        continue

                    results.append({
                        "entity": entity_name,
                        "rel": rel_type,
                        "tail": tail,
                        "condition": entity
                    })

            except Exception as e:
                print(f"[WARN] Failed to query entity {entity}: {e}")

        return results

    def query_dietary_by_entity(
        self,
        user_query: str,
        score_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Query knowledge graph for dietary context based on entity matching.

        Extracts words from user query and searches for matching entities in the KG.
        Returns relevant dietary context (benefits, risks, conflicts) for matched entities.

        Args:
            user_query: User's preference string (e.g., "I want a tuna sandwich with vegetable")
            score_threshold: Minimum score threshold for entity matching (default 0.5)

        Returns:
            Dictionary with:
            - matched_entities: List of matched entity names from KG
            - entity_benefits: List of benefits for matched entities
            - entity_risks: List of risks for matched entities
            - entity_conflicts: List of conflicts/contraindications for matched entities
        """

        results = {
            "matched_entities": [],
            "entity_benefits": [],
            "entity_risks": [],
            "entity_conflicts": []
        }

        # Extract words from user query
        words = user_query.lower().split()
        # Filter out stop words and short words (<3 chars)
        keywords = [w.strip(".,!?;:\"'") for w in words if w.lower() not in stop_words and len(w) > 2]

        # Search KG for each keyword
        seen_entities = set()
        for keyword in keywords:
            search_results = self._kg.search_entities(keyword)

            print(f"searched result for keyword={keyword}")
            print(search_results)

            for result in search_results:
                entity_name = result.get("head", result.get("tail", ""))
                if not entity_name or entity_name.lower() in stop_words:
                    continue

                # Avoid duplicates
                if entity_name in seen_entities:
                    continue
                seen_entities.add(entity_name)
                results["matched_entities"].append(entity_name)

                # Collect benefits, risks, and conflicts based on relation type
                rel_type = result.get("rel_type", "")
                tail = result.get("tail", "")

                # Determine if this is a benefit, risk, or conflict
                if rel_type in ["Has_Benefit", "Indicated_For"]:
                    results["entity_benefits"].append({
                        "entity": entity_name,
                        "benefit": tail,
                        "relation": rel_type
                    })
                elif rel_type in ["Has_Risk", "Contraindicated_For"]:
                    results["entity_risks"].append({
                        "entity": entity_name,
                        "risk": tail,
                        "relation": rel_type
                    })
                elif rel_type == "Antagonism_With":
                    results["entity_conflicts"].append({
                        "entity": entity_name,
                        "conflicts_with": tail,
                        "relation": rel_type
                    })

        # Also query default dietary entities for additional context
        # all_entities_to_query = list(set(results["matched_entities"] + DIETARY_QUERY_ENTITIES))
        all_entities_to_query = list(set(results["matched_entities"]))

        # Use universal search for all entities (matched + default)
        for entity in all_entities_to_query[:10]:  # Limit total entities
            try:
                search_results = self._kg.search_entities(entity)

                # Classify results based on relation types
                for result in search_results:
                    entity_name = result.get("head", "")
                    tail = result.get("tail", "")
                    rel_type = result.get("rel_type", "")

                    if not tail:
                        continue

                    # Classify by relation type
                    if rel_type in ["Has_Benefit", "Indicated_For"]:
                        results["entity_benefits"].append({
                            "entity": entity_name,
                            "benefit": tail,
                            "relation": rel_type
                        })
                    elif rel_type in ["Has_Risk", "Contraindicated_For"]:
                        results["entity_risks"].append({
                            "entity": entity_name,
                            "risk": tail,
                            "relation": rel_type
                        })
                    elif rel_type == "Antagonism_With":
                        results["entity_conflicts"].append({
                            "entity": entity_name,
                            "conflicts_with": tail,
                            "relation": rel_type
                        })
            except Exception as e:
                print(f"[WARN] Failed to query entity {entity}: {e}")

        return results

    def _format_entity_kg_context(self, entity_knowledge: Dict) -> str:
        """Format entity-based KG knowledge for diet prompt"""
        if not entity_knowledge:
            return ""

        parts = []

        if entity_knowledge.get("matched_entities"):
            entities = entity_knowledge["matched_entities"]
            parts.append(f"- Matched Entities from KG: {', '.join(set(entities))}")

        if entity_knowledge.get("entity_benefits"):
            benefits = entity_knowledge["entity_benefits"][:5]  # Limit to top 5
            unique_benefits = {}
            for b in benefits:
                key = f"{b.get('entity', '')}-{b.get('benefit', '')}"
                if key not in unique_benefits:
                    unique_benefits[key] = b
            if unique_benefits:
                benefit_list = [f"{b.get('entity', '')} has {b.get('benefit', '')}" for b in unique_benefits.values()]
                parts.append(f"- Entity Benefits: {', '.join(benefit_list)}")

        if entity_knowledge.get("entity_risks"):
            risks = entity_knowledge["entity_risks"][:5]  # Limit to top 5
            unique_risks = {}
            for r in risks:
                key = f"{r.get('entity', '')}-{r.get('risk', '')}"
                if key not in unique_risks:
                    unique_risks[key] = r
            if unique_risks:
                risk_list = [f"{r.get('entity', '')} may have {r.get('risk', '')}" for r in unique_risks.values()]
                parts.append(f"- Entity Risks: {', '.join(risk_list)}")

        if entity_knowledge.get("entity_conflicts"):
            conflicts = entity_knowledge["entity_conflicts"][:5]  # Limit to top 5
            unique_conflicts = {}
            for c in conflicts:
                key = f"{c.get('entity', '')}-{c.get('conflicts_with', '')}"
                if key not in unique_conflicts:
                    unique_conflicts[key] = c
            if unique_conflicts:
                conflict_list = [f"{c.get('entity', '')} conflicts with {c.get('conflicts_with', '')}" for c in unique_conflicts.values()]
                parts.append(f"- Entity Conflicts: {', '.join(conflict_list)}")

        if parts:
            return "## Entity-Based KG Context\n" + "\n".join(parts) + "\n"
        return ""

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

    # ================= Condition-Exercise Knowledge Base =================
    # Fallback knowledge when KG doesn't have exercise data

    _CONDITION_EXERCISE_MAP = {
        "diabetes": {
            "recommended": ["walking", "swimming", "cycling", "light_strength", "water_aerobics"],
            "avoid": ["high_intensity_hiit", "extreme_endurance", "heavy_weightlifting"],
            "notes": ["Avoid exercise during peak insulin activity", "Check blood sugar before/after"],
            "safe_intensity": "low"
        },
        "hypertension": {
            "recommended": ["walking", "swimming", "yoga", "light_cycling", "pilates"],
            "avoid": ["heavy_weightlifting", "high_intensity_hiit", "valsalva_maneuver", "isometric"],
            "notes": ["Monitor blood pressure", "Avoid isometric exercises", "Avoid holding breath"],
            "safe_intensity": "moderate"
        },
        "heart_disease": {
            "recommended": ["light_walking", "slow_cycling", "water_exercise", "light_yoga"],
            "avoid": ["running", "hiit", "heavy_lifting", "competitive_sports", "sprinting"],
            "notes": ["Medical clearance required", "Keep intensity low", "Stop if chest pain or dizziness"],
            "safe_intensity": "low"
        },
        "obesity": {
            "recommended": ["walking", "water_aerobics", "recumbent_bike", "elliptical", "swimming"],
            "avoid": ["running", "jumping", "high_impact_activities", "jump_rope"],
            "notes": ["Start slow, progress gradually", "Focus on low-impact options", "Use proper footwear"],
            "safe_intensity": "low"
        },
        "arthritis": {
            "recommended": ["swimming", "water_exercise", "cycling", "yoga", "pilates", "elliptical"],
            "avoid": ["running", "high_impact_jumping", "heavy_lifting", "squat_deadlift"],
            "notes": ["Range of motion exercises preferred", "Avoid high-impact", "Warm up joints before activity"],
            "safe_intensity": "low"
        },
        "back_pain": {
            "recommended": ["swimming", "walking", "yoga", "pilates", "light_cycling", "elliptical"],
            "avoid": ["heavy_squat", "deadlift", "high_impact_jumping", "heavy_lifting"],
            "notes": ["Core strengthening recommended", "Avoid hyperextension", "Maintain neutral spine"],
            "safe_intensity": "moderate"
        },
        "asthma": {
            "recommended": ["swimming", "walking", "cycling", "yoga", "light_strength"],
            "avoid": ["running", "hiit", "cold_weather_outdoor", "high_intensity_cardio"],
            "notes": ["Use inhaler before exercise if needed", "Avoid cold dry air", "Warm up gradually"],
            "safe_intensity": "moderate"
        },
        "osteoporosis": {
            "recommended": ["walking", "light_strength", "balance_exercises", "tai_chi", "swimming"],
            "avoid": ["running", "jumping", "high_impact", "heavy_lifting", "bending_forward"],
            "notes": ["Focus on weight-bearing exercise", "Improve balance to prevent falls"],
            "safe_intensity": "low"
        }
    }

    # ================= KG Query Methods =================

    def query_exercise_knowledge(
        self,
        conditions: List[str],
        fitness_level: str = "beginner",
        cared_rels: List[str] = None
    ) -> List[Dict]:
        """
        Query knowledge graph for exercise recommendations.
        Returns a list of relationship dicts matching the diet agent pattern.
        """
        results = []
        all_entities = list(set(conditions + EXERCISE_QUERY_ENTITIES))


        # Use universal search for all conditions
        for entity in all_entities:
            try:
                search_results = self._kg.search_entities(entity)
                all_rel_types = []

                # Classify results based on relation types
                for result in search_results:
                    entity_name = result.get("head", "")
                    tail = result.get("tail", "")
                    rel_type = result.get("rel_type", "")
                    if cared_rels is not None and rel_type not in cared_rels:
                        continue
                    all_rel_types.append(rel_type)

                    if not tail:
                        continue

                    results.append({
                        "entity": entity_name,
                        "rel": rel_type,
                        "tail": tail,
                        "condition": entity
                    })
            except Exception as e:
                print(f"[WARN] Failed to query condition {condition}: {e}")

        return results

    def query_exercise_by_entity(
        self,
        user_query: str,
        score_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Query knowledge graph for exercise context based on entity matching.

        Extracts words from user query and searches for matching entities in the KG.
        Returns relevant exercise context (benefits, target muscles, duration, frequency) for matched entities.

        Args:
            user_query: User's preference string (e.g., "I want to focus on upper body exercises")
            score_threshold: Minimum score threshold for entity matching (default 0.5)

        Returns:
            Dictionary with:
            - matched_entities: List of matched entity names from KG
            - entity_benefits: List of benefits for matched entities
            - target_muscles: List of target muscle groups for matched entities
            - duration_recommendations: List of recommended duration for matched entities
            - frequency_recommendations: List of recommended frequency for matched entities
        """

        results = {
            "matched_entities": [],
            "entity_benefits": [],
            "target_muscles": [],
            "duration_recommendations": [],
            "frequency_recommendations": []
        }

        # Extract words from user query
        words = user_query.lower().split()
        # Filter out stop words and short words (<3 chars)
        keywords = [w.strip(".,!?;:\"'") for w in words if w.lower() not in stop_words and len(w) > 2]

        # Search KG for each keyword
        seen_entities = set()
        for keyword in keywords:
            search_results = self._kg.search_entities(keyword)

            for result in search_results:
                entity_name = result.get("head", result.get("tail", ""))
                if not entity_name or entity_name.lower() in stop_words:
                    continue

                # Avoid duplicates
                if entity_name in seen_entities:
                    continue
                seen_entities.add(entity_name)
                results["matched_entities"].append(entity_name)

        # Also try direct entity queries for more specific results
        for entity in results["matched_entities"][:5]:  # Limit to top 5 for performance
            try:
                # Query benefits
                benefits = self._kg.query_exercise_benefits(entity)
                if benefits:
                    for b in benefits:
                        results["entity_benefits"].append({
                            "entity": entity,
                            "benefit": b.get("entity", ""),
                            "relation": b.get("relation", "")
                        })

                # Query target muscles
                muscles = self._kg.query_exercise_targets_muscle(entity)
                if muscles:
                    for m in muscles:
                        results["target_muscles"].append({
                            "entity": entity,
                            "target": m.get("entity", ""),
                            "relation": m.get("relation", "")
                        })

                # Query duration
                duration = self._kg.query_exercise_duration(entity)
                if duration:
                    for d in duration:
                        results["duration_recommendations"].append({
                            "entity": entity,
                            "duration": d.get("entity", ""),
                            "relation": d.get("relation", "")
                        })

                # Query frequency
                frequency = self._kg.query_exercise_frequency(entity)
                if frequency:
                    for f in frequency:
                        results["frequency_recommendations"].append({
                            "entity": entity,
                            "frequency": f.get("entity", ""),
                            "relation": f.get("relation", "")
                        })
            except Exception as e:
                print(f"[WARN] Failed to query entity {entity}: {e}")

        # Query default exercise entities for additional context
        all_entities_to_query = list(set(results["matched_entities"] + EXERCISE_QUERY_ENTITIES))

        # Use universal search for all entities (matched + default)
        for entity in all_entities_to_query[:10]:  # Limit total entities
            try:
                search_results = self._kg.search_entities(entity)

                # Classify results based on relation types
                for result in search_results:
                    entity_name = result.get("head", "")
                    tail = result.get("tail", "")
                    rel_type = result.get("rel_type", "")

                    if not tail:
                        continue

                    # Classify by relation type for exercise
                    if rel_type == "Targets_Entity":
                        results["target_muscles"].append({
                            "entity": entity_name,
                            "target": tail,
                            "relation": rel_type
                        })
                    elif rel_type in ["Has_Benefit", "Indicated_For"]:
                        results["entity_benefits"].append({
                            "entity": entity_name,
                            "benefit": tail,
                            "relation": rel_type
                        })
                    elif rel_type in ["Recommended_Duration", "Duration"]:
                        results["duration_recommendations"].append({
                            "entity": entity_name,
                            "duration": tail,
                            "relation": rel_type
                        })
                    elif rel_type in ["Recommended_Frequency", "Frequency"]:
                        results["frequency_recommendations"].append({
                            "entity": entity_name,
                            "frequency": tail,
                            "relation": rel_type
                        })
            except Exception as e:
                print(f"[WARN] Failed to query entity {entity}: {e}")

        return results

    def _format_exercise_entity_kg_context(self, entity_knowledge: Dict) -> str:
        """Format entity-based KG knowledge for exercise prompt"""
        if not entity_knowledge:
            return ""

        parts = []

        if entity_knowledge.get("matched_entities"):
            entities = entity_knowledge["matched_entities"]
            parts.append(f"- Matched Entities from KG: {', '.join(set(entities))}")

        if entity_knowledge.get("entity_benefits"):
            benefits = entity_knowledge["entity_benefits"][:5]  # Limit to top 5
            unique_benefits = {}
            for b in benefits:
                key = f"{b.get('entity', '')}-{b.get('benefit', '')}"
                if key not in unique_benefits:
                    unique_benefits[key] = b
            if unique_benefits:
                benefit_list = [f"{b.get('entity', '')} has {b.get('benefit', '')}" for b in unique_benefits.values()]
                parts.append(f"- Exercise Benefits: {', '.join(benefit_list)}")

        if entity_knowledge.get("target_muscles"):
            muscles = entity_knowledge["target_muscles"][:5]  # Limit to top 5
            unique_muscles = {}
            for m in muscles:
                key = f"{m.get('entity', '')}-{m.get('target', '')}"
                if key not in unique_muscles:
                    unique_muscles[key] = m
            if unique_muscles:
                muscle_list = [f"{m.get('entity', '')} targets {m.get('target', '')}" for m in unique_muscles.values()]
                parts.append(f"- Target Muscles: {', '.join(muscle_list)}")

        if entity_knowledge.get("duration_recommendations"):
            durations = entity_knowledge["duration_recommendations"][:5]  # Limit to top 5
            unique_durations = {}
            for d in durations:
                key = f"{d.get('entity', '')}-{d.get('duration', '')}"
                if key not in unique_durations:
                    unique_durations[key] = d
            if unique_durations:
                duration_list = [f"{d.get('entity', '')}: {d.get('duration', '')}" for d in unique_durations.values()]
                parts.append(f"- Duration Recommendations: {', '.join(duration_list)}")

        if entity_knowledge.get("frequency_recommendations"):
            frequencies = entity_knowledge["frequency_recommendations"][:5]  # Limit to top 5
            unique_frequencies = {}
            for f in frequencies:
                key = f"{f.get('entity', '')}-{f.get('frequency', '')}"
                if key not in unique_frequencies:
                    unique_frequencies[key] = f
            if unique_frequencies:
                freq_list = [f"{f.get('entity', '')}: {f.get('frequency', '')}" for f in unique_frequencies.values()]
                parts.append(f"- Frequency Recommendations: {', '.join(freq_list)}")

        if parts:
            return "## Entity-Based KG Context\n" + "\n".join(parts) + "\n"
        return ""

    def query_exercise_by_type(
        self,
        exercise_type: str,
        conditions: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query exercises by type with condition filtering.

        Args:
            exercise_type: Type of exercise (cardio, strength, flexibility, etc.)
            conditions: User's medical conditions to filter

        Returns:
            List of exercise objects
        """
        # Expanded exercise library by type
        exercise_library = {
            "cardio": [
                {"name": "Brisk Walking", "intensity_levels": ["low", "moderate"], "cal_per_min": {"low": 4, "moderate": 5}},
                {"name": "Jogging", "intensity_levels": ["moderate", "high"], "cal_per_min": {"moderate": 8, "high": 10}},
                {"name": "Running", "intensity_levels": ["moderate", "high", "very_high"], "cal_per_min": {"moderate": 10, "high": 12}},
                {"name": "Cycling", "intensity_levels": ["low", "moderate", "high"], "cal_per_min": {"low": 5, "moderate": 7, "high": 9}},
                {"name": "Swimming", "intensity_levels": ["low", "moderate", "high"], "cal_per_min": {"low": 6, "moderate": 8, "high": 10}},
                {"name": "Rowing", "intensity_levels": ["moderate", "high"], "cal_per_min": {"moderate": 7, "high": 9}},
                {"name": "Jump Rope", "intensity_levels": ["high", "very_high"], "cal_per_min": {"high": 12, "very_high": 15}},
                {"name": "Elliptical", "intensity_levels": ["low", "moderate"], "cal_per_min": {"low": 5, "moderate": 7}},
                {"name": "Stair Climbing", "intensity_levels": ["moderate", "high"], "cal_per_min": {"moderate": 7, "high": 9}},
                {"name": "Dancing", "intensity_levels": ["low", "moderate", "high"], "cal_per_min": {"low": 4, "moderate": 6, "high": 8}}
            ],
            "strength": [
                {"name": "Bodyweight Squats", "intensity_levels": ["low", "moderate"], "target_muscles": ["legs", "glutes"]},
                {"name": "Push-ups", "intensity_levels": ["moderate", "high"], "target_muscles": ["chest", "arms", "core"]},
                {"name": "Lunges", "intensity_levels": ["low", "moderate"], "target_muscles": ["legs", "glutes"]},
                {"name": "Plank", "intensity_levels": ["moderate", "high"], "target_muscles": ["core", "shoulders"]},
                {"name": "Dumbbell Rows", "intensity_levels": ["moderate", "high"], "target_muscles": ["back", "arms"]},
                {"name": "Resistance Band Exercises", "intensity_levels": ["low", "moderate"], "target_muscles": ["full_body"]},
                {"name": "Bodyweight Rows", "intensity_levels": ["moderate", "high"], "target_muscles": ["back", "biceps"]},
                {"name": "Glute Bridge", "intensity_levels": ["low", "moderate"], "target_muscles": ["glutes", "hamstrings"]}
            ],
            "flexibility": [
                {"name": "Static Stretching", "duration_unit": "seconds"},
                {"name": "Yoga Sun Salutation", "flow": True},
                {"name": "Dynamic Stretching", "warmup": True},
                {"name": "Hamstring Stretch", "target": "hamstrings"},
                {"name": "Hip Flexor Stretch", "target": "hip_flexors"},
                {"name": "Shoulder Stretch", "target": "shoulders"},
                {"name": "Cat-Cow Flow", "target": "spine"}
            ],
            "balance": [
                {"name": "Single Leg Stand", "progression": "eyes_closed"},
                {"name": "Heel-to-Toe Walk", "progression": "forward_backward"},
                {"name": "Tandem Stance", "progression": "tandem_walk"},
                {"name": "Tai Chi Movements", "flow": True},
                {"name": "Balance Board", "difficulty": "progressive"}
            ],
            "hiit": [
                {"name": "Sprint Intervals", "work_rest": "1:2", "max_duration": 30},
                {"name": "Burpee Variations", "work_rest": "1:1", "max_duration": 20},
                {"name": "Mountain Climbers", "work_rest": "1:1", "max_duration": 30},
                {"name": "High Knees", "work_rest": "1:1", "max_duration": 30},
                {"name": "Box Jumps", "work_rest": "1:2", "max_duration": 20}
            ]
        }

        exercises = exercise_library.get(exercise_type.lower(), [])

        # Filter by conditions if provided
        if conditions:
            exercises = [ex for ex in exercises if not self._check_exercise_conflict(ex.get("name", ""), conditions)]

        return exercises

    # ================= Progression Planning =================

    def get_exercise_progression_plan(
        self,
        current_level: str,
        goal: str,
        weeks: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Generate exercise progression plan based on current level and goal.

        Args:
            current_level: beginner, intermediate, advanced
            goal: weight_loss, muscle_building, cardio_improvement, etc.
            weeks: Duration of progression plan

        Returns:
            Weekly progression plan with exercise modifications
        """
        progression_templates = {
            ("beginner", "weight_loss"): [
                {"week": 1, "focus": "Establish baseline", "duration": 20, "intensity": "low", "sessions": 3},
                {"week": 2, "focus": "Build consistency", "duration": 25, "intensity": "low", "sessions": 4},
                {"week": 3, "focus": "Increase duration", "duration": 30, "intensity": "moderate", "sessions": 4},
                {"week": 4, "focus": "Introduce intervals", "duration": 30, "intensity": "moderate", "sessions": 5}
            ],
            ("beginner", "muscle_building"): [
                {"week": 1, "focus": "Learn proper form", "duration": 20, "intensity": "low", "sessions": 2},
                {"week": 2, "focus": "Increase volume", "duration": 30, "intensity": "low", "sessions": 3},
                {"week": 3, "focus": "Add sets", "duration": 35, "intensity": "moderate", "sessions": 3},
                {"week": 4, "focus": "Progressive overload", "duration": 40, "intensity": "moderate", "sessions": 4}
            ],
            ("beginner", "cardio_improvement"): [
                {"week": 1, "focus": "Low impact start", "duration": 20, "intensity": "low", "sessions": 3},
                {"week": 2, "focus": "Extend time", "duration": 25, "intensity": "low", "sessions": 3},
                {"week": 3, "focus": "Add intervals", "duration": 30, "intensity": "moderate", "sessions": 4},
                {"week": 4, "focus": "Build endurance", "duration": 35, "intensity": "moderate", "sessions": 4}
            ],
            ("intermediate", "weight_loss"): [
                {"week": 1, "focus": "Mixed modalities", "duration": 35, "intensity": "moderate", "sessions": 5},
                {"week": 2, "focus": "HIIT introduction", "duration": 40, "intensity": "moderate_high", "sessions": 5},
                {"week": 3, "focus": "Increase intensity", "duration": 40, "intensity": "high", "sessions": 5},
                {"week": 4, "focus": "Peak week", "duration": 45, "intensity": "high", "sessions": 6}
            ],
            ("intermediate", "muscle_building"): [
                {"week": 1, "focus": "Compound movements", "duration": 45, "intensity": "moderate", "sessions": 4},
                {"week": 2, "focus": "Volume increase", "duration": 50, "intensity": "moderate", "sessions": 4},
                {"week": 3, "focus": "Intensity focus", "duration": 50, "intensity": "high", "sessions": 5},
                {"week": 4, "focus": "Deload week", "duration": 35, "intensity": "low", "sessions": 3}
            ],
            ("advanced", "general"): [
                {"week": 1, "focus": "High volume", "duration": 60, "intensity": "high", "sessions": 6},
                {"week": 2, "focus": "Peak intensity", "duration": 60, "intensity": "very_high", "sessions": 6},
                {"week": 3, "focus": "Maintain", "duration": 55, "intensity": "high", "sessions": 5},
                {"week": 4, "focus": "Deload", "duration": 45, "intensity": "moderate", "sessions": 4}
            ]
        }

        key = (current_level.lower(), goal.lower())
        base_plan = progression_templates.get(key, progression_templates.get((current_level.lower(), "general"), [
            {"week": i, "focus": "Week " + str(i), "duration": 30, "intensity": "moderate", "sessions": 4} for i in range(1, weeks + 1)
        ]))

        return base_plan[:weeks]

    # ================= Helper Methods =================

    def _get_safe_intensity(
        self,
        condition: str,
        fitness_level: str
    ) -> str:
        """Determine safe intensity based on condition and fitness level"""
        condition_intensity_map = {
            "diabetes": "low",
            "hypertension": "moderate",
            "heart_disease": "low",
            "obesity": "low",
            "arthritis": "low",
            "back_pain": "moderate",
            "asthma": "moderate",
            "osteoporosis": "low"
        }

        base_intensity = condition_intensity_map.get(condition.lower(), "moderate")

        # Adjust for fitness level
        fitness_adjustments = {
            "beginner": {"low": "low", "moderate": "low", "high": "moderate"},
            "intermediate": {"low": "low", "moderate": "moderate", "high": "high"},
            "advanced": {"low": "moderate", "moderate": "high", "high": "very_high"}
        }

        return fitness_adjustments.get(fitness_level, {}).get(base_intensity, "moderate")

    def _check_exercise_conflict(
        self,
        exercise_name: str,
        conditions: List[str]
    ) -> bool:
        """Check if an exercise conflicts with any medical condition"""
        exercise_lower = exercise_name.lower()

        # Build conflict map
        conflicts = {
            "diabetes": ["hiit", "high intensity", "extreme", "sprinting", "heavy lifting"],
            "hypertension": ["heavy weightlifting", "isometric", "valsalva", "heavy lifting"],
            "heart_disease": ["running", "hiit", "heavy", "sprinting", "competitive"],
            "obesity": ["running", "jumping", "jump rope", "high impact"],
            "arthritis": ["running", "jumping", "high impact", "heavy squat", "deadlift"],
            "back_pain": ["heavy squat", "deadlift", "heavy lifting", "jumping"],
            "asthma": ["running", "hiit", "cold weather", "high intensity"],
            "osteoporosis": ["running", "jumping", "high impact", "heavy lifting"]
        }

        for condition in conditions:
            condition_key = condition.lower()
            for cond_key, conflict_exercises in conflicts.items():
                if cond_key in condition_key or condition_key in cond_key:
                    for conflict in conflict_exercises:
                        if conflict in exercise_lower:
                            return True

        return False

    def _deduplicate_exercises(self, exercises: List[Dict]) -> List[Dict]:
        """Remove duplicate exercises from list"""
        seen = set()
        unique = []
        for ex in exercises:
            key = ex.get("exercise", ex.get("name", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(ex)
        return unique

    # ================= Calorie Estimation =================

    def estimate_calories_burned(
        self,
        exercise_type: str,
        duration_minutes: int,
        weight_kg: float,
        intensity: str = "moderate"
    ) -> int:
        """Estimate calories burned for an exercise (MET-based)"""
        # Extended MET values database
        met_values = {
            # Cardio
            "walking": {"low": 2.5, "moderate": 3.5, "high": 5.0, "very_high": 6.0},
            "jogging": {"low": 5.0, "moderate": 7.0, "high": 8.5, "very_high": 10.0},
            "running": {"low": 7.0, "moderate": 9.8, "high": 11.5, "very_high": 14.0},
            "cycling": {"low": 4.0, "moderate": 6.0, "high": 8.0, "very_high": 10.0},
            "swimming": {"low": 5.0, "moderate": 7.0, "high": 9.0, "very_high": 11.0},
            "rowing": {"low": 4.0, "moderate": 7.0, "high": 9.0, "very_high": 12.0},
            "jump_rope": {"low": 8.0, "moderate": 10.0, "high": 12.0, "very_high": 15.0},
            "elliptical": {"low": 4.0, "moderate": 5.5, "high": 7.0, "very_high": 8.5},
            "stair_climbing": {"low": 4.0, "moderate": 7.0, "high": 9.0, "very_high": 11.0},
            "dancing": {"low": 4.0, "moderate": 6.0, "high": 8.0, "very_high": 10.0},

            # Strength
            "strength_training": {"low": 3.0, "moderate": 5.0, "high": 6.0, "very_high": 8.0},
            "weightlifting": {"low": 3.0, "moderate": 5.0, "high": 6.0, "very_high": 8.0},
            "bodyweight_training": {"low": 3.0, "moderate": 4.5, "high": 6.0, "very_high": 7.5},
            "resistance_band": {"low": 2.5, "moderate": 4.0, "high": 5.5, "very_high": 7.0},
            "calisthenics": {"low": 3.5, "moderate": 5.0, "high": 6.5, "very_high": 8.0},

            # Flexibility & Balance
            "yoga": {"low": 2.0, "moderate": 3.0, "high": 4.0, "very_high": 5.0},
            "pilates": {"low": 2.5, "moderate": 3.5, "high": 4.5, "very_high": 5.5},
            "stretching": {"low": 1.5, "moderate": 2.5, "high": 3.5, "very_high": 4.0},
            "tai_chi": {"low": 2.0, "moderate": 3.0, "high": 4.0, "very_high": 5.0},

            # HIIT
            "hiit": {"low": 8.0, "moderate": 10.0, "high": 12.0, "very_high": 15.0},
            "sprinting": {"low": 10.0, "moderate": 12.0, "high": 15.0, "very_high": 20.0},
            "burpees": {"low": 8.0, "moderate": 10.0, "high": 12.0, "very_high": 15.0},
            "mountain_climbers": {"low": 6.0, "moderate": 8.0, "high": 10.0, "very_high": 12.0},

            # Water exercises
            "water_aerobics": {"low": 4.0, "moderate": 5.5, "high": 7.0, "very_high": 8.5},
            "aquatic_exercise": {"low": 4.0, "moderate": 5.5, "high": 7.0, "very_high": 8.5},
            "swimming_laps": {"low": 5.0, "moderate": 7.0, "high": 9.0, "very_high": 11.0}
        }

        # Get MET value (default to moderate if not found)
        met = 5.0  # Default MET
        for key, values in met_values.items():
            if key in exercise_type.lower() or exercise_type.lower() in key:
                met = values.get(intensity.lower(), values.get("moderate", 5.0))
                break

        # Calculate calories: MET * 3.5 * weight_kg / 200 = kcal/min
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
