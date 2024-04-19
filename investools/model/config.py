import pydantic

from .base import BaseModel


class Config(BaseModel):
    drift_limit: float = pydantic.Field(0.01, ge=0.0, le=1.0)
    same_tax_class_drift_limit: float = pydantic.Field(0.05, ge=0.0, le=1.0)
    ordinary_tax_rate: float = pydantic.Field(0.0, ge=0.0, le=1.0)
    preferential_tax_rate: float = pydantic.Field(0.0, ge=0.0, le=1.0)
