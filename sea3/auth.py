import hashlib
import re
import sqlite3
import uuid

from database import (
    add_user, get_user, update_last_login, pin_in_use, pin_in_use_by_other,
    get_account_id_by_pin, get_account_ids_by_name_age, update_user_fields,
)


def validate_name(name):
    """Validate name - should be at least 2 characters."""
    return len(name.strip()) >= 2


def validate_age(age):
    """Validate age is within acceptable range."""
    return 3 <= age <= 99


def validate_pin(pin):
    return re.fullmatch(r"\d{4}", pin) is not None


def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()


PIN_TAKEN = "That PIN is already taken. Please pick a different one."


def register_user(name, age, pin):
    """Register a new account with name, age and a 4-digit PIN. Returns (success, message, account_id)."""
    if not validate_name(name):
        return False, "Name must be at least 2 characters.", None

    if not validate_age(age):
        return False, "Age must be between 3 and 99.", None

    if not validate_pin(pin):
        return False, "Your PIN must be exactly 4 numbers.", None

    if get_account_ids_by_name_age(name, age):
        return False, "You already have an account! Go to **Re-login** and use your PIN, or your name and age.", None

    pin_hash = hash_pin(pin)
    if pin_in_use(pin_hash):
        return False, PIN_TAKEN, None

    account_id = f"user-{uuid.uuid4().hex}@sea.local"
    success, message = add_user(name.strip(), age, account_id, pin_hash)
    return success, message, account_id if success else None


def change_name(account_id, name):
    """Returns (success, message)."""
    if not validate_name(name):
        return False, "Name must be at least 2 characters."
    update_user_fields(account_id, name=name.strip())
    return True, "Your name was changed!"


def change_age(account_id, age):
    if not validate_age(age):
        return False, "Age must be between 3 and 99."
    update_user_fields(account_id, age=age)
    return True, "Your age was changed!"


def change_pin(account_id, pin):
    if not validate_pin(pin):
        return False, "Your PIN must be exactly 4 numbers."
    pin_hash = hash_pin(pin)
    if pin_in_use_by_other(pin_hash, account_id):
        return False, PIN_TAKEN
    try:
        update_user_fields(account_id, pin_hash=pin_hash)
    except sqlite3.IntegrityError:
        return False, PIN_TAKEN
    return True, "Your PIN was changed!"


def get_account(account_id):
    """Load an account by its ID and record the login."""
    user_data = get_user(account_id)
    if user_data:
        update_last_login(account_id)
    return user_data


def login_with_pin(pin):
    if not validate_pin(pin):
        return None
    account_id = get_account_id_by_pin(hash_pin(pin))
    return get_account(account_id) if account_id else None


def login_with_name_age(name, age):
    """Returns (user_data, error_message)."""
    # Fall back to last year's age so a birthday doesn't lock anyone out
    matches = get_account_ids_by_name_age(name, age) or get_account_ids_by_name_age(name, age - 1)
    if not matches:
        return None, "I couldn't find you. Check your name, and try the age you were when you signed up."
    if len(matches) > 1:
        return None, "More than one account has that name and age. Please log in with your PIN."
    return get_account(matches[0]), None
