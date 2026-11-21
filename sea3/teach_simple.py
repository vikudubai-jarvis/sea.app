"""
SOCRATIC TEACHING - Help them figure it out, don't give answers! 🌊
"""

import re
from collections import namedtuple
from fractions import Fraction

from content import TOPICS
from lessons import (
    parse_equation, guide_equation, is_big, big_math_intro, fmt, fmt_value,
    divide_by_zero_text, multi_step_intro, negative_intro,
)


def find_known_topic(question):
    """A lesson topic from content.py named in the question (e.g. 'algebra', 'machines'), or None."""
    text = question.lower()
    for topic in TOPICS:
        if re.search(r'\d', topic):
            continue
        names = {topic, topic.split()[-1]}
        if any(re.search(rf'\b{re.escape(name.rstrip("s"))}s?\b', text) for name in names):
            return topic
    # Second pass: extra words a lesson lists, e.g. "friction" -> forces, "main character" -> reading
    for topic, data in TOPICS.items():
        if any(re.search(rf'\b{re.escape(alias)}\b', text) for alias in data.get("aliases", [])):
            return topic
    return None


BOOK_QUESTION = """Let's look at your book together! 📚

**What kind of book is it?** Press one of the buttons below:
1. 📖 **Reading** - a story, comic or poems
2. 🎓 **Learning** - a book that teaches facts, like science or history
3. 🛠️ **Instructions** - a book that tells you how to do or make something"""


def mentions_book(text):
    return re.search(r"\bbooks?\b", text.lower()) is not None


def topic_level(age):
    if age < 8:
        return "young_child"
    if age < 13:
        return "child"
    return "teen"


def topic_hints(topic, age):
    """Hints with no numbers in them, so none of them gives an answer away."""
    return [h for h in TOPICS[topic][topic_level(age)]["hints"] if not re.search(r'\d', h)]


def guide_topic(question, topic, age):
    opener = TOPICS[topic][topic_level(age)]["initial_question"]
    return f"""Good question! Let's work out **{topic}** together.

{opener}

Tell me what you think - there's no wrong answer!"""


def teach(question, age):
    """Main teaching - HELP them think, don't answer!"""
    guidance = get_guidance(question, age)
    return guidance


def get_guidance(question, age):
    """Guide them to figure it out themselves"""

    # Clean up
    q = question.lower().strip()
    original = question

    # Equations first: "3x + 2 = 11" contains sums that would otherwise look like plain maths
    equation = parse_equation(q)
    if equation and not equation.trivial:
        return guide_equation(equation, age)

    # IS IT MATH? Help them solve it, don't give answer
    if is_math_question(q):
        p = parse_math(normalize_math(q))
        if p and p.divide_by_zero:
            return divide_by_zero_text(p.expr)
        if p and not p.simple:
            return multi_step_intro(p.expr)
        if p and p.op == "-" and p.a < p.b:
            return negative_intro(p.a, p.b)
        if p and p.a.denominator == p.b.denominator == 1 and is_big(int(p.a), int(p.b)):
            return big_math_intro(int(p.a), p.op, int(p.b))
        return guide_math(q, age)

    if mentions_book(q):
        return BOOK_QUESTION
    topic = find_known_topic(q)
    if topic:
        return guide_topic(original, topic, age)

    # IS IT A CONCEPT? Help them understand it
    if is_concept_question(q):
        return guide_concept(original, age)

    # OTHERWISE: Ask what they think
    return guide_general(original, age)


UNITS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * n for n, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2)}
SCALES = {"hundred": 100, "thousand": 1000}
NUMBER_WORDS = set(UNITS) | set(TENS) | set(SCALES)
DIVIDE = r'\b(?:de|di)vi?de?\w*'  # divide, divided, dividing, plus typos like "divid" or "devide"


def words_to_numbers(text):
    """'twenty five' -> '25', 'two hundred and five' -> '205'. 'one and two' stays two separate numbers."""
    text = re.sub(r'\b(' + '|'.join(TENS) + r')-(' + '|'.join(UNITS) + r')\b', r'\1 \2', text)
    tokens = re.sub(r'([+\-*/×÷=?,!])', r' \1 ', text).split()
    out, i = [], 0
    while i < len(tokens):
        if tokens[i] not in NUMBER_WORDS:
            out.append(tokens[i])
            i += 1
            continue
        total = current = 0
        last = None
        while i < len(tokens):
            word = tokens[i]
            if word == "and" and last == "scale" and i + 1 < len(tokens) and tokens[i + 1] in UNITS | TENS.keys():
                i += 1
                continue
            if word in TENS and last in (None, "scale"):
                current += TENS[word]
                last = "tens"
            elif word in UNITS and last in (None, "scale", "tens") and not (last == "tens" and UNITS[word] >= 10):
                current += UNITS[word]
                last = "unit"
            elif word == "hundred" and last in (None, "unit", "tens") and current < 100:
                current = max(current, 1) * 100
                last = "scale"
            elif word == "thousand" and last in (None, "unit", "tens", "scale"):
                total += max(current, 1) * 1000
                current = 0
                last = "scale"
            else:
                break
            i += 1
        out.append(str(total + current))
    return " ".join(out)


def normalize_math(text):
    """Turn number words and phrases like 'subtract 2 from 10' or 'divided by' into symbols"""
    t = text.lower()
    t = re.sub(r'half\s+(?:of\s+)?(?:an?\s+)?million', '1000000/2', t)
    t = re.sub(r'half\s+(?:of\s+)?(?:an?\s+)?thousand', '1000/2', t)
    t = words_to_numbers(t)
    t = re.sub(r'half\s+(?:of\s+)?(\d+)', r'\1/2', t)
    t = re.sub(r'\bmillion\b', '1000000', t)
    t = re.sub(r'(\d)\s*x\s*(\d)', r'\1*\2', t)  # "25 x 4" means times
    # Phrases where the second number comes first: "divide 2 from 10" and "subtract 2 from 10" mean 10 ÷ 2 and 10 - 2
    t = re.sub(DIVIDE + r'\s+(\d+)\s+(?:from|into|out of)\s+(\d+)', r'\2 / \1', t)
    t = re.sub(DIVIDE + r'\s+(\d+)\s+by\s+(\d+)', r'\1 / \2', t)
    t = re.sub(r'\b(?:subtract|take away|take|minus)\s+(\d+)\s+from\s+(\d+)', r'\2 - \1', t)
    t = re.sub(r'\badd\s+(\d+)\s+(?:and|to|plus)\s+(\d+)', r'\1 + \2', t)
    t = re.sub(DIVIDE + r'(?:\s+(?:by|into))?(?=\s*\d)', '/', t)  # "10 divided by 2", "10 divid 2"
    t = re.sub(r'multiplied\s+by|\btimes\b', '*', t)
    t = re.sub(r'\bplus\b', '+', t)
    t = re.sub(r'\bminus\b|take\s+away', '-', t)
    return t.replace('×', '*').replace('÷', '/')


def is_math_question(q):
    """Check if it's a math problem"""
    return re.search(r'[\d)]\s*[+\-*/]\s*[\d(]', normalize_math(q)) is not None


MathProblem = namedtuple("MathProblem", "expr value simple a op b divide_by_zero")
_ARITH_RUN = re.compile(r"[-\d.(][\d.\s+\-*/()]*[\d.)]")
_HAS_OPERATOR = re.compile(r"[\d.)]\s*[+\-*/]\s*[\d.(]")
_SIMPLE = re.compile(r"(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)")


def _eval_arith(expr):
    """Exact value of an arithmetic expression (numbers, + - * / and brackets only)."""
    tokens = re.findall(r"\d+(?:\.\d+)?|[+\-*/()]", expr)
    if "".join(tokens) != re.sub(r"\s", "", expr):
        return None
    code = "".join(f"Fraction('{t}')" if t[0].isdigit() else t for t in tokens)
    if "**" in code or "//" in code:
        return None
    value = eval(code, {"__builtins__": {}, "Fraction": Fraction})  # only numbers and + - * / ( ) reach here
    return value if isinstance(value, Fraction) else None


def parse_math(normalized):
    """The sum in already-normalised text, worked out exactly (brackets, decimals, fractions), or None."""
    runs = [r.strip() for r in _ARITH_RUN.findall(normalized)]
    candidates = [r for r in runs if _HAS_OPERATOR.search(r)]
    if not candidates:
        return None
    expr = max(candidates, key=len)
    try:
        value = _eval_arith(expr)
    except ZeroDivisionError:
        return MathProblem(expr, None, False, None, None, None, True)
    except (SyntaxError, TypeError):
        return None
    if value is None:
        return None
    m = _SIMPLE.fullmatch(expr)
    if m:
        return MathProblem(expr, value, True, Fraction(m.group(1)), m.group(2), Fraction(m.group(3)), False)
    return MathProblem(expr, value, False, None, None, None, False)


def try_simple_math(expression):
    """The answer to the sum in the text, or None. For 'a ÷ b' with a remainder, the whole-number part."""
    p = parse_math(normalize_math(expression))
    if not p or p.divide_by_zero:
        return None
    if p.simple and p.op == "/" and p.a.denominator == p.b.denominator == 1 and p.a % p.b:
        return int(p.a // p.b)
    return int(p.value) if p.value.denominator == 1 else p.value


def is_concept_question(q):
    """Check if it's asking 'what is'"""
    return 'what' in q or 'how' in q or 'why' in q or 'explain' in q


def things(count):
    return "thing" if count == "1" else "things"


def guide_math(expression, age):
    """GUIDE them through math, don't just answer!"""

    # Extract the numbers
    normalized = normalize_math(expression)
    p = parse_math(normalized)
    if not p or not p.simple:
        return guide_general(expression, age)
    num1, num2 = fmt_value(p.a, "." in p.expr), fmt_value(p.b, "." in p.expr)
    normalized = p.op  # pick the branch by the actual operator, not by any '-' elsewhere in the text

    # Find operator
    if '+' in normalized:
        if age < 8:
            return f"""Great question about **{expression}**!

Let me help you figure this out:
- You have **{num1}** {things(num1)}
- You GET **{num2}** more {things(num2)}
- If you count them all together... how many do you have?

Try counting! Use your fingers if you want! 🖐️

**What do YOU think the answer is?**"""
        elif age < 13:
            return f"""Good question: **{expression}**

Here's how to solve it:
1. Start with **{num1}**
2. Count UP **{num2}** more times
3. See where you land!

Try it! What number do you get?"""
        else:
            return f"""You're asking: **{expression}**

Here's the method:
- Start at {num1}
- Add {num2}
- Count carefully

What's your answer? Show me how you got it!"""

    elif '-' in normalized:
        if age < 8:
            return f"""You asked: **{expression}**

Let me help:
- You START with **{num1}** {things(num1)}
- You TAKE AWAY **{num2}**
- How many are LEFT?

Try it! **What's your answer?**"""
        elif age < 13:
            return f"""Subtraction question: **{expression}**

Here's how:
1. Start with {num1}
2. Take away {num2}
3. Count what's left

What do you get?"""
        else:
            return f"""Problem: **{expression}**

Solve this by:
- Beginning at {num1}
- Subtracting {num2}
- Finding the result

What's your answer?"""

    elif '*' in normalized:
        if age < 8:
            return f"""Multiplication: **{expression}**

Think of it like:
- **{num1}** groups
- **{num2}** items in each group
- How many TOTAL?

Can you figure it out?"""
        elif age < 13:
            return f"""Multiplication: **{expression}**

Remember:
- {num1} groups of {num2}
- OR {num2} groups of {num1}
- What's the total?

Give it a try!"""
        else:
            return f"""Problem: **{expression}**

Multiply {num1} × {num2}. What do you get?"""

    elif '/' in normalized:
        if age < 8 and p.a > 20:
            small = fmt(p.b * 5)
            return f"""Let's practice with a smaller number first.

You have **{small} cookies**. Give them to **{num2} friends**, so each friend gets the same amount.

How many cookies does each friend get?"""
        if age < 8:
            return f"""Sharing question: **{expression}**

Imagine you have **{num1}** cookies and you share them with **{num2}** friends.
- Give one cookie to each friend
- Keep going until no cookies are left over

How many cookies does each friend get?"""
        elif age < 13:
            return f"""Division question: **{expression}**

Think of it as sharing:
1. Start with **{num1}**
2. Split it into **{num2}** equal groups
3. How many are in each group?

What do you get?"""
        else:
            return f"""Problem: **{expression}**

How many times does **{num2}** fit into **{num1}**? What's the result?"""

    return f"""You asked: **{expression}**

Try solving this step by step. What do YOU think the answer is?"""


def guide_concept(question, age):
    """GUIDE them to understand concepts"""

    if age < 8:
        return f"""You asked: **{question}** 🤔

That's a GREAT question! Let me ask YOU something:

**What do you ALREADY know about it?**
Tell me what you think! 💭"""

    elif age < 13:
        return f"""Good question: **{question}**

Before I explain, I want to know:
**What do YOU think it means?**

Tell me your guess - there's no wrong answer!"""

    elif age < 18:
        return f"""Interesting: **{question}**

Here's what I want YOU to think about:
- What CONNECTS this to things you know?
- What's your CURRENT understanding?

Let's build from there!"""

    else:
        return f"""You're asking about: **{question}**

Before we dive in:
- What do you already know about it?
- Where have you come across it before?

Let's work it out together!"""


def guide_general(question, age):
    """Guide for any other question"""

    if age < 8:
        return f"""You asked: **{question}** 🤔

**I want to know - what do YOU think?**
What's your guess? 💭"""

    elif age < 13:
        return f"""Great question: **{question}**

Before I help, tell me:
**What do you already know about this?**
What's your guess?"""

    elif age < 18:
        return f"""Interesting question: **{question}**

What's your CURRENT understanding of this?
What would help you figure it out?"""

    else:
        return f"""Regarding **{question}**:

What's your initial take? What do you think?"""
