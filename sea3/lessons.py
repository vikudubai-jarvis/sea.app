"""Offline lessons: algebra equations and big-number maths, taught step by step without giving answers."""

import re
from collections import namedtuple
from fractions import Fraction

PLACES = ["ones", "tens", "hundreds", "thousands", "ten-thousands", "hundred-thousands"]
BIG = 20  # from here on, "count up one at a time" stops being a sensible strategy

Equation = namedtuple("Equation", "var a b c d solution display trivial")
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+|[+\-*/()=]")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def fmt(value):
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


# ---------- algebra ----------

def _tokens(text):
    t = text.lower().replace("×", "*").replace("÷", "/").replace("−", "-")
    return _TOKEN.findall(t)


def _is_equation_token(tok):
    return bool(_NUMBER.fullmatch(tok) or tok in "+-*/()" or re.fullmatch(r"[a-z]", tok))


def _to_python(tokens, var):
    """Build an arithmetic expression from already-validated tokens (numbers, one variable, operators)."""
    out, prev = [], None
    for tok in tokens:
        if tok == var:
            piece, kind = "X", "value"
        elif _NUMBER.fullmatch(tok):
            piece, kind = f"Fraction('{tok}')", "value"
        elif tok in "+-*/()":
            piece, kind = tok, tok
        else:
            return None
        if prev in ("value", ")") and (kind == "value" or piece == "("):
            out.append("*")  # 3x, 2(x+1), x(...)
        out.append(piece)
        prev = kind
    return "".join(out)


def _linear(expr):
    """(slope, intercept) if expr is linear in X, else None."""
    if "**" in expr:
        return None
    try:
        y0, y1, y2 = (eval(expr, {"__builtins__": {}, "Fraction": Fraction}, {"X": Fraction(v)}) for v in (0, 1, 2))
    except (ZeroDivisionError, SyntaxError, TypeError):
        return None
    if not all(isinstance(y, Fraction) for y in (y0, y1, y2)) or y2 - y1 != y1 - y0:
        return None
    return y1 - y0, y0


def _display(tokens):
    text = ""
    for tok in tokens:
        text += f" {tok.replace('*', '×')} " if tok in "+-*/=" else tok
    return " ".join(text.split())


def parse_equation(text):
    """A one-variable linear equation in the text (e.g. '3x + 2 = 11'), or None."""
    tokens = _tokens(text)
    if tokens.count("=") != 1:
        return None
    i = tokens.index("=")
    left, j = [], i - 1
    while j >= 0 and _is_equation_token(tokens[j]):
        left.insert(0, tokens[j])
        j -= 1
    right, k = [], i + 1
    while k < len(tokens) and _is_equation_token(tokens[k]):
        right.append(tokens[k])
        k += 1
    letters = {t for t in left + right if t.isalpha()}
    if not left or not right or len(letters) != 1:
        return None
    var = letters.pop()
    sides = []
    for side in (left, right):
        expr = _to_python(side, var)
        line = _linear(expr) if expr else None
        if line is None:
            return None
        sides.append(line)
    (a, b), (c, d) = sides
    if a == c:
        return None
    trivial = (left == [var] and len(right) == 1) or (right == [var] and len(left) == 1)
    return Equation(var, a, b, c, d, (d - b) / (a - c), _display(left + ["="] + right), trivial)


def equation_signature(text):
    eq = parse_equation(text)
    return None if eq is None or eq.trivial else (eq.a, eq.b, eq.c, eq.d)


def guide_equation(eq, age):
    v, shown = eq.var, eq.display
    if eq.c != 0 or eq.a == 0:
        return f"""Let's solve **{shown}** together!

The goal is to get **{v}** all by itself on one side. Whatever you do to one side, do to the other side too.

First: can you get all the **{v}** parts onto one side? What could you do?"""

    a, b, d = eq.a, eq.b, eq.d
    if age < 8:
        if a == 1 and b > 0:
            return f"""Let's solve **{shown}**!

Think of **{v}** as a mystery number hiding in a box. 📦
The mystery number plus **{fmt(b)}** makes **{fmt(d)}**.

What number plus {fmt(b)} makes {fmt(d)}? Try counting up from {fmt(b)}!"""
        if a == 1 and b < 0:
            return f"""Let's solve **{shown}**!

Think of **{v}** as a mystery number hiding in a box. 📦
If you take away **{fmt(-b)}** from the mystery number, **{fmt(d)}** is left.

What number would you start with? Try counting up from {fmt(d)}!"""
        if b == 0 and a.denominator == 1:
            return f"""Let's solve **{shown}**!

Think of **{fmt(a)}** boxes, each with the same mystery number inside. 📦
All the boxes together make **{fmt(d)}**.

If you share {fmt(d)} equally into {fmt(a)} boxes, how many go in each box?"""

    if b != 0:
        first = f"undo the **{'+' if b > 0 else '-'} {fmt(abs(b))}**. What could you do to both sides to get rid of it?"
    elif a.numerator == 1 and a.denominator != 1:
        first = f"undo the **÷ {a.denominator}**. What is the opposite of dividing?"
    else:
        first = f"undo the **× {fmt(a)}**. What is the opposite of multiplying?"
    return f"""Let's solve **{shown}**!

The goal: get **{v}** all by itself. Whatever you do to one side, do to the other side too.

First, {first}"""


def equation_steps(eq):
    v, shown = eq.var, eq.display
    if eq.c != 0 or eq.a == 0:
        steps = [
            f"Take the **{v}** parts away from one side (do it to both sides), so **{v}** is only on one side.",
            "Move the plain numbers to the other side the same way.",
            f"Divide both sides by the number in front of **{v}**.",
            f"Check: put your number in place of **{v}**. Do both sides match?",
        ]
    else:
        a, b, d = eq.a, eq.b, eq.d
        steps = []
        if b != 0:
            sign = "-" if b > 0 else "+"
            steps.append(f"{'Take away' if b > 0 else 'Add'} **{fmt(abs(b))}** on both sides. What is {fmt(d)} {sign} {fmt(abs(b))}?")
        if a.numerator == 1 and a.denominator != 1:
            steps.append(f"Now multiply that number by **{a.denominator}** (that undoes the ÷ {a.denominator}).")
        elif a != 1:
            steps.append(f"Now **{fmt(a)} × {v}** equals that number. Divide it by **{fmt(a)}** to find **{v}**.")
        steps.append(f"Check: put your number in place of **{v}** in **{shown}**. Does it work?")
    lines = "\n".join(f"Step {i}: {s}" for i, s in enumerate(steps, start=1))
    return f"""No problem! Let's solve **{shown}** step by step:

{lines}

Tell me what you get for **{v}**!"""


def equation_check_hint(eq, given):
    return f"""You said **{eq.var} = {fmt(given)}**. Let's check it!

Put **{fmt(given)}** in place of **{eq.var}** in **{eq.display}** and work out each side.
Do both sides come out the same? If not, try a different number!"""


def answer_value(text):
    """The last number in the text, allowing decimals and fractions like 7/2 or -3."""
    found = re.findall(r"-?\d+(?:\.\d+)?(?:/\d+)?", text)
    if not found:
        return None
    try:
        return Fraction(found[-1])
    except (ValueError, ZeroDivisionError):
        return None


# ---------- big-number maths ----------

def is_big(a, b):
    return max(a, b) >= BIG


def _digits(n):
    return [int(ch) for ch in reversed(str(n))]


def _place_parts(n):
    return [d * 10 ** i for i, d in reversed(list(enumerate(_digits(n)))) if d]


def big_math_steps(a, op, b):
    """Step list (no final answer) for a big-number sum."""
    if op in "+-":
        if op == "-" and a < b:
            return [f"Careful: {a} is smaller than {b}, so the answer goes below zero.",
                    f"Work out **{b} - {a}** first, then put a minus sign in front."]
        top, bottom = _digits(a), _digits(b)
        steps = [f"Write **{a}** on top and **{b}** underneath, lining up the ones on the right."]
        if op == "-":
            steps.append("If a top digit is smaller than the one under it, borrow 1 from the column to its left "
                         "(that column is now 1 smaller, and your digit gets 10 more).")
        for i in range(max(len(top), len(bottom))):
            x = top[i] if i < len(top) else 0
            y = bottom[i] if i < len(bottom) else 0
            place = PLACES[i] if i < len(PLACES) else "next"
            if op == "+":
                carry = " (plus any 1 you carried)" if i else ""
                steps.append(f"Add the **{place}**: {x} + {y}{carry}. If it's 10 or more, write the ones digit and carry 1.")
            else:
                steps.append(f"Subtract the **{place}**: {x} - {y}.")
        return steps

    if op == "*":
        big, small = max(a, b), min(a, b)
        if small < 10:
            parts = _place_parts(big)
            steps = [f"Break **{big}** into parts: {' + '.join(str(p) for p in parts)}."]
            steps += [f"Work out **{p} × {small}**." for p in parts]
            steps.append("Add all your answers together.")
            return steps
        tens, ones = small - small % 10, small % 10
        steps = [f"Break **{small}** into {tens} and {ones}."]
        steps.append(f"Work out **{big} × {tens}**. (Tip: to times by {tens}, times by {tens // 10} and then add a 0.)")
        if ones:
            steps.append(f"Work out **{big} × {ones}**.")
        steps.append("Add your answers together.")
        return steps

    if op == "/":
        steps = []
        if a % 10 == 0 and b % 10 == 0:
            steps.append(f"Both numbers end in 0, so cross a 0 off each: **{a} ÷ {b}** is the same as **{a // 10} ÷ {b // 10}**.")
        steps += [
            f"Ask: how many groups of **{b}** fit into **{a}**?",
            f"Make a guess, then times your guess by **{b}**.",
            "Too big? Guess smaller. Too small? Guess bigger.",
        ]
        if a % b:
            steps.append("It won't fit exactly, so the bit left over at the end is the **remainder**.")
        return steps
    return []


def sum_text(a, op, b):
    return f"{a} {op.replace('*', '×').replace('/', '÷')} {b}"


def big_math_intro(a, op, b):
    steps = big_math_steps(a, op, b)
    return f"""Big numbers! Let's do **{sum_text(a, op, b)}** in small steps.

{steps[0]}
{steps[1] if len(steps) > 1 else ''}

Try that, then tell me what you get. Say "I don't know" if you'd like all the steps."""


def fmt_value(value, decimal=False):
    """3/4 stays a fraction unless the question used decimals, then 0.75."""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.10g}" if decimal else f"{value.numerator}/{value.denominator}"


def show_expr(expr):
    return " ".join(expr.replace("*", "×").split())


def divide_by_zero_text(expr):
    return f"""Ooh, tricky one: **{show_expr(expr)}**

Dividing by **0** doesn't work! Imagine sharing cookies between **0** friends - there's nobody to give them to.
So this sum has no answer. Try dividing by a different number!"""


def order_rules(expr):
    """Order-of-operations steps, mentioning only the kinds of step this sum actually has."""
    rules = []
    if "(" in expr:
        rules.append("Work out the part in brackets ( ) first.")
    if re.search(r"[*/]", expr):
        rules.append("Do the × and ÷ parts, going from left to right.")
    if re.search(r"\d\s*[+\-]\s*[\d(]", expr):
        rules.append("Do the + and - parts, going from left to right (start with the first two numbers).")
    rules.append("Write down each little answer as you go, then use it in the next step.")
    return rules


def multi_step_intro(expr):
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(order_rules(expr)[:-1], start=1))
    return f"""This one has more than one step: **{show_expr(expr)}**

Remember the order:
{rules}

Which part will you work out first?"""


def negative_steps(a, b):
    return [f"Careful: **{fmt(a)}** is smaller than **{fmt(b)}**, so the answer goes below zero.",
            f"Work out **{fmt(b)} - {fmt(a)}** first.",
            "Then put a minus sign in front of your answer."]


def negative_intro(a, b):
    steps = negative_steps(a, b)
    return f"""Let's do **{fmt(a)} - {fmt(b)}**!

{steps[0]}
Think of a number line: start at **{fmt(a)}** and count back **{fmt(b)}** steps. You'll go past zero!

Where do you land?"""


def decimal_steps(op):
    if op in "+-":
        return ["Write the numbers one under the other so the decimal points line up.",
                "Fill any empty spaces with 0.",
                "Work it out like normal numbers, column by column from the right.",
                "Put the decimal point in your answer straight under the others."]
    return ["Pretend the decimal points aren't there and work it out with whole numbers.",
            "Count how many digits were after the decimal points in the question.",
            "Put the decimal point back so your answer makes sense (check by rounding the numbers)."]


def numbered(steps):
    return "\n".join(f"Step {i}: {s}" for i, s in enumerate(steps, start=1))
