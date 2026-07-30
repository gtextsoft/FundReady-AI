"""Recommendation HTTP endpoints.

Gap-to-program matching, filtered per country.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

from fastapi import APIRouter

router = APIRouter(tags=["recommendation"])
