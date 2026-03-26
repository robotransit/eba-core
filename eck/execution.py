# eck/execution.py
from typing import Callable
import re
import ast
import operator

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

def _safe_eval(expr: str) -> float:
    """Safely evaluate a simple arithmetic expression using ast."""
    try:
        node = ast.parse(expr.strip(), mode="eval")
        if not isinstance(node, ast.Expression):  # pragma: no cover
            raise ValueError("Invalid expression")

        def _eval(n):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.BinOp):
                op_type = type(n.op)
                if op_type not in _ALLOWED_OPERATORS:
                    raise ValueError(f"Operator {op_type.__name__} not allowed")
                left = _eval(n.left)
                right = _eval(n.right)
                return _ALLOWED_OPERATORS[op_type](left, right)
            raise ValueError("Unsupported expression node")

        return _eval(node.body)
    except Exception as e:
        raise ValueError(f"Safe evaluation failed: {e}")


def execute_task(
    task_text: str,
    llm_call: Callable[[str], str],
    use_tools: bool = False,
) -> str:
    """
    Execute a task and return the outcome string.

    This is the main execution seam for the Epistemic Control Kernel (ECK).
    Supports optional dummy calculator tool for seam validation.
    """
    if use_tools:
        # Dummy tool: explicit calculator
        match = re.search(r'^CALC:\s*(.+)$', task_text.strip(), re.IGNORECASE)
        if match:
            expr = match.group(1)
            try:
                result = _safe_eval(expr)
                outcome = f"Calculation result: {result}"
                # Normalize tool output too (symmetry with other modules)
                outcome = ' '.join(outcome.split())
            except Exception as e:
                outcome = f"Calculation failed (invalid expression)"
        else:
            outcome = llm_call(task_text).strip()
    else:
        outcome = llm_call(task_text).strip()

    # Normalize internal whitespace (symmetry with prediction/task gen)
    return ' '.join(outcome.split())
