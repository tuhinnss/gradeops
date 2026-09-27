"""Shared schema base."""

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for API schemas.

    In the OpenAPI *response* schema, fields that always have a value (because
    they have a default) are marked required, so the generated TypeScript types
    (frontend/src/lib/api-schema.ts) are precise. Request validation is unchanged.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
