"""
Exercise Agent Models
Pydantic models for exercise recommendation input/output.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ExerciseType(str, Enum):
    """Types of exercise"""
    CARDIO = "cardio"
    STRENGTH = "strength"
    FLEXIBILITY = "flexibility"
    BALANCE = "balance"
    HIIT = "hiit"


class IntensityLevel(str, Enum):
    """Exercise intensity levels"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class TimeOfDay(str, Enum):
    """Time of day for exercise"""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    ANY = "any"


class ExerciseItem(BaseModel):
    """A single exercise in a plan"""
    name: str = Field(..., description="Name of the exercise")
    exercise_type: ExerciseType = Field(..., description="Type of exercise")
    duration_minutes: int = Field(..., description="Duration in minutes")
    intensity: IntensityLevel = Field(..., description="Exercise intensity")
    calories_burned: int = Field(..., description="Estimated calories burned")
    equipment: List[str] = Field(
        default_factory=list,
        description="Required equipment"
    )
    target_muscles: List[str] = Field(
        default_factory=list,
        description="Target muscle groups"
    )
    instructions: List[str] = Field(
        default_factory=list,
        description="Exercise instructions"
    )
    reason: str = Field(
        ...,
        description="Why this exercise is suitable for the user"
    )
    safety_notes: List[str] = Field(
        default_factory=list,
        description="Safety considerations"
    )


class ExerciseSession(BaseModel):
    """A session of exercises (e.g., morning, afternoon)"""
    time_of_day: TimeOfDay = Field(..., description="When to perform")
    exercises: List[ExerciseItem] = Field(..., description="Exercises in this session")
    total_duration_minutes: int = Field(..., description="Total duration")
    total_calories_burned: int = Field(..., description="Total calories burned")
    overall_intensity: IntensityLevel = Field(..., description="Session intensity")


class ExercisePlan(BaseModel):
    """Complete exercise plan for one candidate"""
    id: int = Field(..., description="Candidate ID")
    title: str = Field(..., description="Plan title")
    sessions: Dict[str, ExerciseSession] = Field(
        ...,
        description="Exercise sessions keyed by time of day"
    )
    total_duration_minutes: int = Field(..., description="Total exercise duration")
    total_calories_burned: int = Field(..., description="Total calories burned")
    weekly_frequency: int = Field(
        ...,
        description="Recommended sessions per week"
    )
    progression: str = Field(
        ...,
        description="How to progress over time"
    )
    reasoning: str = Field(..., description="Overall reasoning for this plan")
    safety_notes: List[str] = Field(
        default_factory=list,
        description="Safety considerations"
    )


class ExerciseCandidatesResponse(BaseModel):
    """Response containing multiple exercise candidates"""
    candidates: List[ExercisePlan] = Field(
        ...,
        description="List of exercise candidates"
    )
    target_calories_burned: int = Field(
        ...,
        description="Target daily calories to burn"
    )
    user_conditions: List[str] = Field(
        ...,
        description="User's health conditions considered"
    )
    fitness_level: str = Field(..., description="User's fitness level")
    sampling_strategy: str = Field(
        ...,
        description="Strategy used for generation"
    )
    generation_notes: str = Field(
        ...,
        description="Additional notes about generation"
    )


class ExerciseAgentInput(BaseModel):
    """Input structure for exercise agent"""
    user_metadata: Dict[str, Any] = Field(
        ...,
        description="User physiological data"
    )
    environment: Dict[str, Any] = Field(
        default_factory=dict,
        description="Environmental context (weather, time)"
    )
    user_requirement: Dict[str, Any] = Field(
        default_factory=dict,
        description="User goals and preferences"
    )
    num_candidates: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of candidates to generate"
    )
