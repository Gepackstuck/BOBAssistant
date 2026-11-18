import ast
import math
import operator

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
FUNCTIONS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos, "log": math.log}
CONSTANTS = {"pi": math.pi, "e": math.e}


def evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        if isinstance(node.op, ast.Pow) and abs(evaluate(node.right)) > 100:
            raise ValueError("слишком большая степень")
        return OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
        return OPERATORS[type(node.op)](evaluate(node.operand))
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
        return FUNCTIONS[node.func.id](*[evaluate(arg) for arg in node.args])
    raise ValueError("недопустимое выражение")


def calculate(expression: str) -> str:
    value = evaluate(ast.parse(expression.replace(",", ".").replace("^", "**"), mode="eval"))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(round(value, 6) if isinstance(value, float) else value)


def spec() -> dict:
    return {
        "name": "calculator",
        "description": "Точно вычисляет арифметическое выражение. Пример: (17*23)+sqrt(16).",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "Выражение на Python-синтаксисе"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        "run": lambda args: calculate(args["expression"]),
    }
