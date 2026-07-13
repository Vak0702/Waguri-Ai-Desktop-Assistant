"""
quick_math.py — Fast, no-LLM-call arithmetic, percentages, and unit
conversions. Handled entirely locally: deterministic, instant, and doesn't
burn an API call (or hit a rate limit) for something that's just math.
"""

from __future__ import annotations

import ast
import operator
import re

# ---------- safe arithmetic evaluation ----------
# Uses Python's `ast` module to parse the expression into a tree and only
# evaluates a small allow-list of arithmetic node types — never raw eval(),
# so there's no way for a crafted phrase to execute arbitrary code.

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Invalid constant")
    elif isinstance(node, ast.BinOp):
        op_func = _ALLOWED_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError("Operator not allowed")
        return op_func(_eval_node(node.left), _eval_node(node.right))
    elif isinstance(node, ast.UnaryOp):
        op_func = _ALLOWED_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError("Operator not allowed")
        return op_func(_eval_node(node.operand))
    else:
        raise ValueError("Expression not allowed")


def _safe_eval(expr: str) -> float:
    node = ast.parse(expr, mode="eval").body
    return _eval_node(node)


_WORD_TO_OP = [
    (r"\bto the power of\b", "**"),
    (r"\btimes\b", "*"),
    (r"\bmultiplied by\b", "*"),
    (r"\bdivided by\b", "/"),
    (r"\bover\b", "/"),
    (r"\bplus\b", "+"),
    (r"\badded to\b", "+"),
    (r"\bminus\b", "-"),
    (r"\bsubtracted from\b", "-"),
]


def _normalize_expression(text: str) -> str:
    expr = text.lower()
    for pattern, replacement in _WORD_TO_OP:
        expr = re.sub(pattern, replacement, expr)
    # Strip anything that isn't part of a valid arithmetic expression —
    # this is what makes it safe to run a full sentence like "what's 24
    # times 7" through here without needing to precisely extract just the
    # math part first.
    expr = re.sub(r"[^0-9.+\-*/() ]", "", expr)
    return expr.strip()


def calculate(raw_text: str) -> str:
    """Handles general arithmetic questions, e.g. 'what's 24 times 7'."""
    expr = _normalize_expression(raw_text)
    if not expr:
        return "I couldn't find a calculation in that."
    try:
        result = _safe_eval(expr)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"That's {result}."
    except Exception:
        return "I couldn't calculate that — try rephrasing it as a simple expression."


def percentage(percent: float, base: float) -> str:
    result = (percent / 100) * base
    if result == int(result):
        result = int(result)
    else:
        result = round(result, 4)
    return f"{percent:g} percent of {base:g} is {result}."


# ---------- unit conversions ----------
# Organized by category so "miles to kilometers" and "kilometers to miles"
# don't need mirrored entries — everything converts through a common base
# unit (meters/kilograms/liters) and the factor is just inverted as needed.

_LENGTH_TO_METERS = {
    "mile": 1609.344, "miles": 1609.344, "mi": 1609.344,
    "kilometer": 1000.0, "kilometers": 1000.0, "km": 1000.0,
    "meter": 1.0, "meters": 1.0, "m": 1.0,
    "centimeter": 0.01, "centimeters": 0.01, "cm": 0.01,
    "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
    "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
    "yard": 0.9144, "yards": 0.9144, "yd": 0.9144,
}

_WEIGHT_TO_KG = {
    "kilogram": 1.0, "kilograms": 1.0, "kg": 1.0,
    "gram": 0.001, "grams": 0.001, "g": 0.001,
    "pound": 0.453592, "pounds": 0.453592, "lb": 0.453592, "lbs": 0.453592,
    "ounce": 0.0283495, "ounces": 0.0283495, "oz": 0.0283495,
}

_VOLUME_TO_LITERS = {
    "liter": 1.0, "liters": 1.0, "litre": 1.0, "litres": 1.0, "l": 1.0,
    "milliliter": 0.001, "milliliters": 0.001, "ml": 0.001,
    "gallon": 3.78541, "gallons": 3.78541, "gal": 3.78541,
    "cup": 0.236588, "cups": 0.236588,
    "fluid ounce": 0.0295735, "fluid ounces": 0.0295735, "fl oz": 0.0295735,
}

_TEMP_UNITS = {"celsius", "fahrenheit", "kelvin", "c", "f", "k"}


def _convert_via_base(amount: float, from_unit: str, to_unit: str, table: dict) -> float | None:
    from_factor = table.get(from_unit.lower())
    to_factor = table.get(to_unit.lower())
    if from_factor is None or to_factor is None:
        return None
    return (amount * from_factor) / to_factor


def convert_units(amount: float, from_unit: str, to_unit: str) -> str:
    from_clean = from_unit.strip().lower()
    to_clean = to_unit.strip().lower()

    if from_clean in _TEMP_UNITS or to_clean in _TEMP_UNITS:
        return _convert_temperature(amount, from_unit, to_unit)

    for table in (_LENGTH_TO_METERS, _WEIGHT_TO_KG, _VOLUME_TO_LITERS):
        result = _convert_via_base(amount, from_unit, to_unit, table)
        if result is not None:
            result = int(result) if result == int(result) else round(result, 4)
            return f"{amount:g} {from_unit} is {result} {to_unit}."

    return f"I don't know how to convert {from_unit} to {to_unit} yet."


def _convert_temperature(amount: float, from_unit: str, to_unit: str) -> str:
    f = from_unit.strip().lower()
    t = to_unit.strip().lower()

    def to_celsius(value, unit):
        if unit in ("celsius", "c"):
            return value
        elif unit in ("fahrenheit", "f"):
            return (value - 32) * 5 / 9
        elif unit in ("kelvin", "k"):
            return value - 273.15
        raise ValueError("unknown unit")

    def from_celsius(value, unit):
        if unit in ("celsius", "c"):
            return value
        elif unit in ("fahrenheit", "f"):
            return value * 9 / 5 + 32
        elif unit in ("kelvin", "k"):
            return value + 273.15
        raise ValueError("unknown unit")

    try:
        celsius = to_celsius(amount, f)
        result = round(from_celsius(celsius, t), 1)
        return f"{amount:g} degrees {from_unit} is {result} degrees {to_unit}."
    except Exception:
        return f"I don't know how to convert {from_unit} to {to_unit} yet."


def handle(payload: dict) -> str:
    mode = payload.get("mode")
    if mode == "percentage":
        return percentage(payload["percent"], payload["base"])
    elif mode == "convert":
        return convert_units(payload["amount"], payload["from_unit"], payload["to_unit"])
    elif mode == "calculate":
        return calculate(payload["raw"])
    return "I didn't understand that calculation."