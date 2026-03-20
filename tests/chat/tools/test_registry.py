"""Tests for the tool registry: schema validation, dispatch, and registration."""
from __future__ import annotations

import pytest

from backend.chat.tools.registry import (
    TOOL_SCHEMAS,
    TOOL_DISPATCH,
    dispatch_tool,
    get_all_schemas,
    register_tool,
    register_all_tools,
)


class TestToolSchemas:
    """Validate all tool schemas are well-formed Anthropic tool definitions."""

    def test_schemas_non_empty(self):
        assert len(TOOL_SCHEMAS) > 0

    @pytest.mark.parametrize("schema", TOOL_SCHEMAS, ids=lambda s: s["name"])
    def test_schema_has_required_fields(self, schema):
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema

    @pytest.mark.parametrize("schema", TOOL_SCHEMAS, ids=lambda s: s["name"])
    def test_description_is_substantial(self, schema):
        desc = schema["description"]
        # At least 3 sentences (roughly 2+ periods)
        assert desc.count(".") >= 2, f"Description too short for {schema['name']}"

    @pytest.mark.parametrize("schema", TOOL_SCHEMAS, ids=lambda s: s["name"])
    def test_input_schema_is_object(self, schema):
        assert schema["input_schema"]["type"] == "object"
        assert "properties" in schema["input_schema"]
        assert "required" in schema["input_schema"]

    def test_get_all_schemas_returns_all(self):
        assert get_all_schemas() is TOOL_SCHEMAS

    def test_all_schema_names_unique(self):
        names = [s["name"] for s in TOOL_SCHEMAS]
        assert len(names) == len(set(names)), "Duplicate tool names found"


class TestToolDispatch:

    def test_register_all_tools_populates_dispatch(self):
        TOOL_DISPATCH.clear()
        register_all_tools()
        schema_names = {s["name"] for s in TOOL_SCHEMAS}
        dispatch_names = set(TOOL_DISPATCH.keys())
        assert schema_names == dispatch_names, (
            f"Schema/dispatch mismatch. "
            f"In schemas but not dispatch: {schema_names - dispatch_names}. "
            f"In dispatch but not schemas: {dispatch_names - schema_names}."
        )

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_raises(self):
        with pytest.raises(KeyError, match="Unknown tool"):
            await dispatch_tool("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler(self):
        """Register a dummy tool and verify dispatch calls it."""
        called_with = {}

        async def dummy_handler(tool_input):
            called_with.update(tool_input)
            return "ok"

        register_tool("_test_dummy", dummy_handler)
        result = await dispatch_tool("_test_dummy", {"key": "value"})
        assert result == "ok"
        assert called_with == {"key": "value"}
        # Cleanup
        TOOL_DISPATCH.pop("_test_dummy", None)
