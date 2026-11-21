"""
SIMPLE TEACHING ENGINE - My baby AI Sea's brain! 🌊
No complexity, just ANSWERS then QUESTIONS
"""

import re
from difflib import SequenceMatcher

from teach_simple import (
    teach, is_math_question, normalize_math, find_known_topic, topic_hints,
    words_to_numbers, NUMBER_WORDS, parse_math, mentions_book,
)
from lessons import (
    parse_equation, equation_signature, equation_steps, equation_check_hint, answer_value,
    is_big, big_math_steps, numbered, fmt, sum_text, fmt_value, divide_by_zero_text, order_rules,
    negative_steps, decimal_steps, show_expr,
)

QUESTION_WORDS = {"what", "how", "why", "who", "when", "where", "explain", "tell", "can", "does", "do"}


def start_learning_session(question, age):
    """Start learning session - returns ANSWER then question"""
    return teach(question, age)


QUESTION_START = re.compile(
    r"^(?:(?:but|and|so|ok|okay|um+|hm+|wait)\b[\s,]*)?(" + "|".join(QUESTION_WORDS) + r"|is|are)\b"
)
# While Sea waits for "how did you solve it", answers often start with how/when/can/do
EXPLANATION_SAFE_STARTS = {"what", "why", "who", "where", "explain", "tell"}


def math_signature(text):
    p = parse_math(normalize_math(text))
    return re.sub(r"\s", "", p.expr) if p else None


def _math_steps(p):
    """Steps (never the answer) for a parsed sum, or None when the plain counting steps fit."""
    if p.divide_by_zero:
        return None
    if not p.simple:
        return order_rules(p.expr)
    if p.op == "-" and p.a < p.b:
        return negative_steps(p.a, p.b)
    if p.a.denominator != 1 or p.b.denominator != 1 or "." in p.expr:
        return decimal_steps(p.op)
    if is_big(int(p.a), int(p.b)):
        return big_math_steps(int(p.a), p.op, int(p.b))
    return None


def _shown(p):
    if not p.simple:
        return show_expr(p.expr)
    decimal = "." in p.expr
    return sum_text(fmt_value(p.a, decimal), p.op, fmt_value(p.b, decimal))


def is_new_question(text, current_question="", awaiting_explanation=False):
    """True when the student is asking something new rather than answering."""
    t = text.strip().lower()
    eq_sig = equation_signature(t)
    if eq_sig:
        return eq_sig != equation_signature(current_question)
    if "=" in t:
        return False  # "3+2=5" or "x = 4" is an answer
    sig = math_signature(t)
    if sig and sig != math_signature(current_question):
        return True
    m = QUESTION_START.match(t)
    if not m:
        return False
    if m.group(1) in ("is", "are"):
        return False  # "is it 55" is an answer
    return not awaiting_explanation or m.group(1) in EXPLANATION_SAFE_STARTS


def mentions_new_question(text, current_question):
    """'I don't know what gravity is' names a different topic or sum than the one being worked on."""
    topic = find_known_topic(text)
    if topic and topic != find_known_topic(current_question):
        return True
    eq_sig = equation_signature(text)
    if eq_sig:
        return eq_sig != equation_signature(current_question)
    sig = math_signature(text)
    return bool(sig) and sig != math_signature(current_question)


OPERATION_WORD = re.compile(
    r'\b(add|adding|added|plus|subtract|subtracting|minus|take|taking|took|times|multiply|multiplied|'
    r'multiplying|divide|divided|dividing|share|sharing|sum|total|combine|combined)\b'
)
DONT_KNOW_PHRASES = (
    "i dont know", "dont know", "i do not know", "idk", "dunno", "idunno", "duno", "donno", "dono",
    "no idea", "no clue",
)
DONT_KNOW_TARGETS = ("i dont know", "dont know")
SQUASHED_TARGETS = ("idontknow", "dontknow", "idunno")


def _looks_like_dont_know(window, target):
    # "I do know" / "I did know" is spelled almost like "I don't know" but means the opposite
    if {"do", "did"} & set(window.split()) or "doknow" in window.replace(" ", ""):
        return False
    return SequenceMatcher(None, window, target).ratio() >= 0.8


def is_dont_know(text):
    """'I don't know', including typos like 'I don now', 'i do't know' or 'idontknow'."""
    t = " ".join(re.sub(r"[^a-z ]", "", text.lower()).split())
    if any(re.search(rf"\b{phrase}\b", t) for phrase in DONT_KNOW_PHRASES):
        return True
    words = t.split()
    if len(words) == 1:
        return any(_looks_like_dont_know(words[0], target) for target in SQUASHED_TARGETS)
    for target in DONT_KNOW_TARGETS:
        n = len(target.split())
        for size in (n - 1, n, n + 1):
            for i in range(max(len(words) - size + 1, 0)):
                if size and _looks_like_dont_know(" ".join(words[i:i + size]), target):
                    return True
    return False


def step_by_step_help(question, age=10):
    equation = parse_equation(question)
    if equation and not equation.trivial:
        return equation_steps(equation)

    p = parse_math(normalize_math(question)) if is_math_question(question) else None
    if p and p.divide_by_zero:
        return divide_by_zero_text(p.expr)
    special = _math_steps(p) if p else None
    if special:
        return f"""No problem, let's do **{_shown(p)}** step by step:

{numbered(special)}

Work through the steps and tell me what you get!"""
    if not p:
        topic = find_known_topic(question)
        hints = topic_hints(topic, age) if topic else []
        if hints:
            steps = "\n".join(f"Step {i}: {hint}" for i, hint in enumerate(hints, start=1))
            return f"""No problem! Let's figure out **{topic}** one step at a time:

{steps}

Start with Step 1 and tell me what you think!"""
        return f"""No problem! Let's break **{question}** into steps.

Step 1: Find the most important number or word in the question.
Step 2: Say in your own words what the question is asking.
Step 3: Tell me what you think Step 2 means."""

    a, op, b = fmt(p.a), p.op, fmt(p.b)

    if op == '+':
        steps = f"""Step 1: Start at **{a}**.
Step 2: Count up **{b}** more, one at a time.
Step 3: The number you land on is the answer."""
    elif op == '-':
        steps = f"""Step 1: Start with **{a}**.
Step 2: Count back **{b}**, one at a time (or cross out **{b}** of them).
Step 3: The number you stop on is the answer."""
    elif op == '*':
        steps = f"""Step 1: Write **{a}** down **{b}** times.
Step 2: Add all of them together."""
    elif op == '/':
        steps = f"""Step 1: Start with **{a}**.
Step 2: Split it into **{b}** equal groups, one at a time.
Step 3: Count how many are in one group."""
    else:
        steps = f"""Step 1: Start with **{a}**.
Step 2: Work with **{b}** using the operation in the question.
Step 3: Check your result."""

    return f"""No problem, let's do **{question}** step by step:

{steps}

Work through the steps and tell me what you get!"""


GOODBYE_PATTERN = re.compile(r'\b(bye|goodbye|good bye|see you|see ya|cya)\b')
GOODBYE_REPLY = "Bye! Have a great day, and come back anytime to keep learning!"


def is_goodbye(text):
    return GOODBYE_PATTERN.search(text.strip().lower()) is not None


LEARN_MORE_PROMPT = "Okay, do you want to learn more?"
DONE_PATTERN = re.compile(
    r"^(?:ok(?:ay)?\s+)?(?:i'?m\s+|i\s+am\s+|im\s+)?(?:all\s+)?(?:done|finished)"
    r"(?:\s+(?:reading|answering|now|with\s+(?:this|that|it|my\s+book|reading)))?\s*[.!]*$"
)


def is_done(text):
    """'done', 'done reading', 'done answering', 'I'm done', 'finished' - the whole message, not part of an answer."""
    return DONE_PATTERN.match(text.strip().lower()) is not None


SURE_PROMPT = "Okay, are you sure?"
YES_WORDS = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay"}
NO_WORDS = {"no", "n", "nope", "nah"}


def closing_step(stage, text):
    """Handle a yes/no reply after the student explains; returns (reply, next_stage)"""
    words = re.sub(r"[^a-z ]", "", text.lower()).split()
    first = words[0] if words else ""
    if first not in YES_WORDS | NO_WORDS:
        return "Please type **yes** or **no**.", stage

    is_yes = first in YES_WORDS
    if stage == "sure":
        if is_yes:
            return LEARN_MORE_PROMPT, "learn_more"
        return "Okay, let's keep going. What are you unsure about?", None

    if is_yes:
        return "What do you need help with?", "need_help"
    return "Okay, enjoy your day!", None


def wrong_answer_hint(question, given):
    p = parse_math(normalize_math(question))
    given = fmt_value(given, decimal="." in str(p.expr if p else "")) if not isinstance(given, str) else given
    if not p or p.divide_by_zero:
        return f"""You said **{given}**. Let's think about it step by step. What do you get now?"""

    special = _math_steps(p)
    if special:
        return f"""You said **{given}**. Not quite - let's check it carefully, one step at a time:

{numbered(special)}

Try again and tell me your new answer!"""

    a, op, b = fmt(p.a), p.op, fmt(p.b)

    if op == '-':
        story = f"""Imagine a person has **{a} chocolates**, and they take away **{b}** of them.
How many chocolates does that person have left?"""
    elif op == '+':
        story = f"""Imagine a person has **{a} chocolates**, and a friend gives them **{b}** more.
How many chocolates do they have now?"""
    elif op == '*':
        story = f"""Imagine **{a} bags**, and each bag has **{b} chocolates** in it.
How many chocolates are there in total?"""
    elif op == '/':
        story = f"""Imagine a person has **{a} chocolates** and shares them equally between **{b} friends**.
How many chocolates does each friend get?"""
    else:
        story = "Let's count it out step by step. What do you get now?"

    return f"""You said **{given}**. Let's check with a story:

{story}

Try it and tell me your new answer!"""


def get_next_teaching_step(question, student_answer, age, step_count, awaiting_explanation=False):
    """Give feedback on the student's answer and keep the conversation going"""
    question = question.strip()
    cleaned = re.sub(r'\bstep\s*\d+\b', '', student_answer.lower())
    if NUMBER_WORDS & set(re.findall(r"[a-z]+", cleaned)):
        cleaned = words_to_numbers(cleaned)  # "seven" counts as 7
    explained = OPERATION_WORD.search(cleaned) is not None

    equation = parse_equation(question)
    if equation and not equation.trivial:
        value = answer_value(cleaned)
        if value == equation.solution or (awaiting_explanation and explained):
            if awaiting_explanation:
                return SURE_PROMPT
            return f"""Good job! **{equation.var} = {fmt(equation.solution)}** makes **{equation.display}** true. You got it!

Can you explain HOW you solved it?"""
        if value is None:
            if explained:
                return f"""You're on the right track! Keep going - what number is **{equation.var}**?"""
            return f"""Good thinking! Try the steps and tell me what number **{equation.var}** is."""
        return equation_check_hint(equation, value)

    p = parse_math(normalize_math(question)) if is_math_question(question) else None
    if p:
        if p.divide_by_zero:
            return divide_by_zero_text(p.expr)

        decimal = "." in p.expr
        # Grade the last number only: "I had 4, took away 2 and got 3" mentions 2 but answers 3
        given = answer_value(cleaned)
        numbers = [int(n) for n in re.findall(r'-?\d+', cleaned)]
        exact = given is not None and given == p.value

        if (exact or (awaiting_explanation and explained)) and awaiting_explanation:
            return SURE_PROMPT
        if exact:
            return f"""Good job! **{_shown(p)}** = **{fmt_value(p.value, decimal)}**. You got it!

Can you explain HOW you solved it?"""

        whole_numbers = p.simple and p.a.denominator == p.b.denominator == 1
        if whole_numbers and p.op == "/" and p.a % p.b:
            a, b = int(p.a), int(p.b)
            quotient, remainder = divmod(a, b)
            if len(numbers) >= 2 and numbers[-1] == remainder and quotient in numbers[:-1]:
                return f"""Good job! **{a} ÷ {b}** = **{quotient} remainder {remainder}**. You got it!

Can you explain HOW you solved it?"""
            if numbers and numbers[-1] == quotient:
                return f"""Yes! **{b}** fits into **{a}** exactly **{quotient}** times. But some are left over.
How many are left over? Tell me like this: **{quotient} remainder ?**"""
            if quotient in numbers[:-1]:
                return f"""**{quotient}** groups is right! Now check the left-over part:
work out **{b} × {quotient}**, then take that away from **{a}**. What's left?"""

        if explained:
            return f"""You're on the right track! Use that idea to finish the math: **{_shown(p)}**. What do you get?"""

        if given is None:
            return f"""Good thinking! Try the steps above and tell me the number you get for **{_shown(p)}**."""

        return wrong_answer_hint(question, given)

    topic = find_known_topic(question)
    if topic == "reading" or mentions_book(question):
        book_type = book_type_in(student_answer)
        if book_type:
            return book_type_help(book_type)
    hints = topic_hints(topic, age) if topic else []
    if hints:
        hint = hints[step_count % len(hints)]
        return f"""Good thinking! You said *"{student_answer}"*.

Here's something to think about next: {hint}

What do you think?"""

    return f"""Good thinking! You said *"{student_answer}"*.

What part of **{question}** feels most interesting to you? Tell me what you'd like to figure out next."""


BOOK_TYPES = [
    ("comic", r"comic|graphic novel|manga|cartoon", "📚 A comic! Comics tell the story with pictures AND words.",
     ["Look at each picture - what is happening in it?",
      "Read the speech bubbles. Who is talking in each one?",
      "How do the characters' faces show how they feel?"]),
    ("poem", r"poem|poetry|rhyme|rhyming|verse", "🎵 A poem book! Poems play with sounds and feelings.",
     ["Read the poem out loud. Which words rhyme?",
      "What picture does the poem make in your head?",
      "How does the poem make you feel, and which words make you feel that way?"]),
    ("instructions", r"instructions?|how to|manual|recipe|guide|steps|making|build",
     "🛠️ An instructions book! It tells you how to do or make something, one step at a time.",
     ["Read ALL the steps first, before you start. What are you going to make or do?",
      "What things (tools or ingredients) do you need? Get them ready.",
      "Do one step at a time. Look at the pictures - does yours look the same?"]),
    ("fact", r"learning|learn|fact|non-?fiction|science|history|real|information|animal|space|encyclopedia|about real",
     "🔎 A fact book! Fact books teach you true things about the world.",
     ["Look at the title and headings - what will this page teach you?",
      "What is one new fact you learned?",
      "Look at the pictures, labels and diagrams. What do they show?"]),
    ("story", r"reading|story|stories|fiction|adventure|mystery|fantasy|funny|fairy|chapter|novel|picture book",
     "📖 A story book! Stories have characters, a problem, and an ending.",
     ["Who is the main character, and what do they want?",
      "What problem happens in the story?",
      "What do you think will happen next, and why?"]),
]


def book_type_in(text):
    t = text.lower()
    for name, pattern, intro, tips in BOOK_TYPES:
        if re.search(rf"\b(?:{pattern})", t):
            return name
    return None


def book_type_help(name):
    _, _, intro, tips = next(b for b in BOOK_TYPES if b[0] == name)
    lines = "\n".join(f"- {tip}" for tip in tips)
    return f"""{intro}

Let's think about it together:
{lines}

Start with the first one - what do you think?"""


def get_hint(question, age):
    """One small next step - the first step of the step-by-step help - without spoiling the answer."""
    steps = re.findall(r"^Step \d+: (.+)$", step_by_step_help(question, age), flags=re.MULTILINE)
    if steps and "most important number or word" not in steps[0]:
        return steps[0]
    return "Read the question again slowly. What is it really asking you to find? Say it in your own words."
