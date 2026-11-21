import html
import traceback

import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta
from auth import (
    register_user, get_account, login_with_pin, login_with_name_age,
    change_name, change_age, change_pin,
)
from ai_tutor import (
    is_ai_available, tutor_reply, get_hint_ai, prepare_image, REFUSAL_REPLY,
    key_source, saved_key_ending, online_enabled, set_online, save_api_key, remove_api_key,
)
from database import (
    init_db, create_remember_token, get_email_for_token, delete_remember_tokens_for_email, REMEMBER_DAYS,
    delete_account,
)
from guest_mode import get_guest_info, start_guest_trial, record_guest_usage, trial_status, reset_trial, EXTRA_DAYS
from sessions import (
    init_sessions_table, create_new_session, add_message_to_session,
    end_session, get_user_sessions, get_session_details, get_session_stats, delete_session
)

# Initialize database
init_db()
init_sessions_table()


@st.cache_resource
def backup_once_per_start():
    """The Settings page promises a backup every time the app starts; this runs once per server start."""
    from backup import backup_database
    return backup_database()


backup_once_per_start()

# Page configuration
st.set_page_config(
    page_title="Sea - Student Education AI",
    page_icon="🌊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for styling
st.markdown("""
    <style>
    .main {
        max-width: 800px;
    }
    .sea-header {
        text-align: center;
        color: #0066cc;
        margin-bottom: 30px;
    }
    .welcome-box {
        background-color: #e6f2ff;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_data = None
    st.session_state.show_settings = False
    st.session_state.is_guest = False
    st.session_state.current_session_id = None
    st.session_state.view_page = "learn"  # "learn" or "sessions"

PER_USER_KEYS = (
    "learning_active", "opening_question", "current_question", "learning_stage", "student_answer", "conversation",
    "step_count", "closing_stage", "account_msg", "show_name_login",
    "settings_name", "settings_age", "settings_pin", "login_pin", "login_name", "login_age",
    "reg_name", "reg_age", "reg_pin",
)


def reset_user_state():
    """Forget everything from the previous person so the next login starts clean."""
    for key in PER_USER_KEYS:
        st.session_state.pop(key, None)
    st.session_state.current_session_id = None
    st.session_state.view_page = "learn"
    st.session_state.show_settings = False


FRIENDLY_ERROR = "Oops, Sea had trouble thinking just now. Please try again in a minute, or ask a grown-up for help."


def report_error():
    """Show kids a friendly message; the details go to the terminal for grown-ups."""
    traceback.print_exc()
    st.error(FRIENDLY_ERROR)


def show_text(text):
    st.markdown(text.replace("$", r"\$"))  # "$5 and $2" would otherwise render as maths


def save_to_history(msg, user_email, is_guest):
    if st.session_state.get("current_session_id") and not is_guest:
        add_message_to_session(st.session_state.current_session_id, user_email, msg["type"], msg["content"])


def add_reply(student_msg, reply_text, user_email, is_guest):
    sea_msg = {"type": "sea", "content": reply_text}
    if reply_text == REFUSAL_REPLY:
        student_msg["skip_api"] = sea_msg["skip_api"] = True
    st.session_state.conversation.append(sea_msg)
    save_to_history(student_msg, user_email, is_guest)
    save_to_history(sea_msg, user_email, is_guest)
    st.session_state.step_count += 1


def drop_last(msg):
    conversation = st.session_state.conversation
    if conversation and conversation[-1] is msg:
        conversation.pop()


REMEMBER_COOKIE = "sea_remember"
cookie_manager = stx.CookieManager(key="cookie_manager")

# Set on the run after login: setting it right before st.rerun() can be dropped by the browser component
if st.session_state.get("pending_remember_token"):
    cookie_manager.set(
        REMEMBER_COOKIE, st.session_state.pop("pending_remember_token"),
        expires_at=datetime.now() + timedelta(days=REMEMBER_DAYS),
        key="set_remember",
    )

# "Are you new?" popup: shown for the first 3 days on this browser, unless "never show this again" was ticked
FIRST_SEEN_COOKIE, HIDE_WELCOME_COOKIE, WELCOME_DAYS = "sea_first_seen", "sea_hide_welcome", 3
browser_cookies = dict(st.context.cookies)
if not browser_cookies.get(FIRST_SEEN_COOKIE) and not st.session_state.get("first_seen_saved"):
    cookie_manager.set(FIRST_SEEN_COOKIE, datetime.now().date().isoformat(),
                       expires_at=datetime.now() + timedelta(days=365), key="set_first_seen")
    st.session_state.first_seen_saved = True
if st.session_state.pop("pending_forget_cookie", False) and browser_cookies.get(REMEMBER_COOKIE):
    cookie_manager.delete(REMEMBER_COOKIE, key="restart_forget_remember")
if st.session_state.pop("pending_hide_welcome", False):
    cookie_manager.set(HIDE_WELCOME_COOKIE, "1", expires_at=datetime.now() + timedelta(days=3650), key="set_hide_welcome")
    st.session_state.welcome_hidden = True


def show_auth_tab(tab):
    """Open the Re-login or Register tab (a new key makes st.tabs use the new default)."""
    st.session_state.auth_tab = tab
    st.session_state.auth_tab_round = st.session_state.get("auth_tab_round", 0) + 1


def welcome_dialog():
    """The 'Are you new?' box on the right-hand side of the login page."""
    with st.container(border=True):
        st.markdown("## 🌊 Welcome to Sea!")
        st.write("### Are you new?")
        choice = None
        if st.button("Yes, I'm new", key="welcome_new", type="primary", use_container_width=True):
            choice = "Register"
        if st.button("No, I have an account", key="welcome_old", use_container_width=True):
            choice = "Re-login"
        never_again = st.checkbox("Never show this again", key="hide_welcome_box")
    if choice:
        st.session_state.welcome_done = True
        show_auth_tab(choice)
        if never_again:
            st.session_state.pending_hide_welcome = True
        st.rerun()


def should_welcome():
    if st.session_state.get("welcome_done"):
        return False
    if st.session_state.get("force_welcome"):  # just pressed Restart
        return True
    if st.session_state.get("welcome_hidden"):
        return False
    if browser_cookies.get(HIDE_WELCOME_COOKIE):
        return False
    try:
        first_seen = datetime.fromisoformat(browser_cookies.get(FIRST_SEEN_COOKIE, "")).date()
    except ValueError:
        first_seen = datetime.now().date()
    return (datetime.now().date() - first_seen).days < WELCOME_DAYS


TOUR = [
    ("👋 Welcome to Sea!",
     "Sea is your learning buddy. Sea doesn't just tell you answers - it **helps you work them out yourself**, "
     "with hints, stories and small steps. Press **Next** to see how it works."),
    ("🔑 Getting in",
     "- **Register**: make an account with your name, age and a 4-number PIN.\n"
     "- **Re-login**: come back with your PIN, or press *Use age and name to login*.\n"
     "- **Try Free**: use Sea without an account for a while (your chats aren't saved)."),
    ("💡 Asking a question",
     "Type any question in **Your Question** and press **Start Learning**. For example:\n"
     "- *what is 45 + 12* or *ten minus four*\n- *solve 3x + 2 = 11*\n- *what are cells* or *help me with my book*\n\n"
     "📚 **Book help:** if your question has the word *book* in it, Sea shows 3 buttons: "
     "**📖 Reading** (stories, comics, poems), **🎓 Learning** (facts) or **🛠️ Instructions** "
     "(how to do or make something). Pick one and Sea gives tips that fit that kind of book."),
    ("💬 Chatting with Sea",
     "Type your answer in the chat box at the bottom.\n"
     "- Right answer: Sea says **Good job!** and asks how you solved it.\n"
     "- Wrong answer: Sea gives a story hint, like sharing chocolates, so you can try again.\n"
     "- Stuck? Type **I don't know** and Sea shows you the steps."),
    ("🛠️ Helpful buttons",
     "- **💡 Hint**: one small next step.\n"
     "- **📷 Picture**: upload a photo of a hard question (online mode only).\n"
     "- **🏁 End**: finish the session. Typing **done** or **bye** also works."),
    ("📋 Your menu",
     "- **📚 Learn**: ask questions.\n- **📋 Sessions**: see your old chats.\n"
     "- **⚙️ Settings**: change your name, age or PIN, turn on online mode, or delete your account.\n"
     "- **🔄 Restart**: fully log out and start fresh.\n- **Logout**: log out."),
    ("🚀 You're ready!",
     "That's everything! Make an account on **Register**, or press **Try Free** to have a go right now."),
]


def show_tour():
    step = st.session_state.tour_step
    title, text = TOUR[step]
    with st.container(border=True):
        st.caption(f"Tour - step {step + 1} of {len(TOUR)}")
        st.progress((step + 1) / len(TOUR))
        st.subheader(title)
        st.markdown(text)
        back, nxt, close = st.columns(3)
        if back.button("⬅️ Back", key="tour_back", disabled=step == 0, use_container_width=True):
            st.session_state.tour_step -= 1
            st.rerun()
        if step < len(TOUR) - 1:
            if nxt.button("Next ➡️", key="tour_next", type="primary", use_container_width=True):
                st.session_state.tour_step += 1
                st.rerun()
        else:
            if nxt.button("Register", key="tour_register", type="primary", use_container_width=True):
                del st.session_state.tour_step
                show_auth_tab("Register")
                st.rerun()
            if close.button("Try Free", key="tour_try", use_container_width=True):
                del st.session_state.tour_step
                show_auth_tab("Try Free")
                st.rerun()
        if step < len(TOUR) - 1 and close.button("✖ Close tour", key="tour_close", use_container_width=True):
            del st.session_state.tour_step
            st.rerun()


def full_restart(user_email, message=None):
    """Log out completely: forget 'stay logged in' and everything from this visit, then show the start screen."""
    delete_remember_tokens_for_email(user_email)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.pending_forget_cookie = True  # removed on the next run, after the page reloads
    st.session_state.force_welcome = True
    if message:
        st.session_state.start_message = message
    st.rerun()


def log_in_button(key):
    """The 'Do you want to log in?' button shown at the bottom of the screen on free-trial rest days."""
    with st.container(border=True):
        st.write("😴 The free trial is resting today and will be back tomorrow.")
        return st.button("Do you want to log in?", key=key, type="primary", use_container_width=True)

if not st.session_state.logged_in:
    remembered_token = cookie_manager.get(cookie=REMEMBER_COOKIE)
    remembered_email = get_email_for_token(remembered_token) if remembered_token else None
    remembered_user = get_account(remembered_email) if remembered_email else None
    if remembered_user:
        st.session_state.logged_in = True
        st.session_state.user_data = remembered_user
        st.session_state.is_guest = False
        st.rerun()

# Main app logic
if not st.session_state.logged_in:
    st.markdown("<h1 class='sea-header'>🌊 Sea</h1>", unsafe_allow_html=True)
    start_message = st.session_state.pop("start_message", None)
    if start_message:
        st.success(start_message)
    st.write("Hey there! 👋 I'm **Sea**, your learning buddy. I'm here to help you learn about anything you want to know. Ask me anything - we'll figure it out together!")

    if "tour_step" in st.session_state:
        show_tour()
        st.stop()
    if st.button("🧭 Take a tour of Sea", key="tour_btn"):
        st.session_state.tour_step = 0
        st.rerun()

    def finish_login(user_data, stay):
        reset_user_state()
        if stay:
            st.session_state.pending_remember_token = create_remember_token(user_data["email"])
        st.session_state.logged_in = True
        st.session_state.user_data = user_data
        st.session_state.is_guest = False
        st.rerun()

    if should_welcome():
        main_col, side_col = st.columns([2, 1])
        with side_col:
            welcome_dialog()  # shown on every run until answered
    else:
        main_col = st.container()

    trial = trial_status()
    with main_col:
        tab1, tab2, tab3 = st.tabs(
            ["Re-login", "Register", "Try Free"],
            default=st.session_state.get("auth_tab", "Re-login"),
            key=f"auth_tabs_{st.session_state.get('auth_tab_round', 0)}",
        )

    with tab1:
        st.subheader("Re-login")
        stay_logged_in = st.checkbox(
            f"Stay logged in for {REMEMBER_DAYS} days (only on your own computer)",
            value=False, key="stay_logged_in",
        )

        with st.form("pin_login_form"):
            pin = st.text_input("Type your PIN", type="password", max_chars=4, key="login_pin")
            if st.form_submit_button("Login with PIN", key="pin_login_btn", type="primary"):
                user_data = login_with_pin(pin.strip())
                if user_data:
                    finish_login(user_data, stay_logged_in)
                else:
                    st.error("That PIN didn't match an account. Check it, or use your name and age.")

        with st.container(border=True):
            if st.button("Use age and name to login", key="show_name_login_btn"):
                st.session_state.show_name_login = not st.session_state.get("show_name_login", False)

            if st.session_state.get("show_name_login", False):
                with st.form("name_login_form", border=False):
                    login_name = st.text_input("Your Name", key="login_name")
                    login_age = st.number_input("Your Age", min_value=3, max_value=99, value=13, step=1, key="login_age")
                    if st.form_submit_button("Login", key="name_login_btn"):
                        user_data, error = login_with_name_age(login_name, int(login_age))
                        if user_data:
                            finish_login(user_data, stay_logged_in)
                        else:
                            st.error(error)

    with tab2:
        st.subheader("Create New Account")
        name = st.text_input("Your Name", key="reg_name")
        age = st.slider("Your Age", min_value=3, max_value=99, value=13, key="reg_age")
        reg_pin = st.text_input("Make a 4-number PIN (you'll use it to log in)", type="password", max_chars=4, key="reg_pin")

        if st.button("Register", key="register_btn"):
            if name and reg_pin:
                success, message, account_id = register_user(name, age, reg_pin.strip())
                if success:
                    finish_login(get_account(account_id), stay=False)
                else:
                    st.error(message)
            else:
                st.error("Please fill in your name and a PIN.")

    with tab3:
        st.subheader("🎉 Free Trial")

        if trial["state"] in ("not_started", "active"):
            if trial["state"] == "not_started":
                st.success("✅ Try Sea free for **1 month**!")
            else:
                st.success(f"✅ Free trial active! You have **{trial['days_left']} days** left")
                st.write(f"📊 Questions asked so far: **{trial['usage_count']}**")
            if trial["extended"]:
                st.caption("Extra months: after every 10 days of the free trial there is 1 rest day.")
            st.info("💾 Want to keep your chats? Make an account on the **Register** tab.")

            guest_age = st.slider("How old are you?", min_value=3, max_value=99, value=8, key="guest_age")
            if st.button("Start Free Trial", key="guest_btn", type="primary"):
                start_guest_trial()
                reset_user_state()
                st.session_state.logged_in = True
                st.session_state.is_guest = True
                st.session_state.user_data = {
                    "name": "Guest User",
                    "age": guest_age,
                    "email": "guest@sea.local",
                    "is_guest": True
                }
                st.rerun()
        elif trial["state"] == "rest_day":
            st.warning("😴 Today is a **rest day** for the free trial. It will be back tomorrow!")
            st.write(f"You have **{trial['days_left']} days** of free trial left.")
        elif trial["can_reset"]:
            st.warning("Your 1-month free trial has ended.")
            st.write(f"You can reset it **once** to get **{EXTRA_DAYS // 30} more months**. "
                     "In those months, after every 10 days there is 1 rest day.")
            if st.button(f"Reset free trial ({EXTRA_DAYS // 30} more months)", key="reset_trial_btn", type="primary"):
                reset_trial()
                st.rerun()
        else:
            st.error("Your free trial has finished.")
            st.write("Please **Re-login** or **Register** to keep using Sea.")

    if trial["state"] == "rest_day" and log_in_button("rest_day_login_btn"):
        show_auth_tab("Re-login")
        st.rerun()

else:
    # Main app after login
    user_name = st.session_state.user_data['name']
    user_age = st.session_state.user_data['age']
    user_email = st.session_state.user_data['email']
    is_guest = st.session_state.is_guest

    def leave_guest_mode(tab):
        reset_user_state()
        st.session_state.logged_in = False
        st.session_state.user_data = None
        st.session_state.is_guest = False
        show_auth_tab(tab)
        st.rerun()

    # Free trial paused (rest day) or finished while a guest is in the app
    guest_trial = trial_status() if is_guest else None
    if guest_trial and guest_trial["state"] not in ("active", "not_started"):
        st.markdown("<h1 class='sea-header'>🌊 Sea</h1>", unsafe_allow_html=True)
        if guest_trial["state"] == "rest_day":
            st.warning("😴 Today is a **rest day** for the free trial. It will be back tomorrow!")
            if log_in_button("guest_rest_login_btn"):
                leave_guest_mode("Re-login")
        else:
            st.error("⏰ Your free trial has ended!")
            if guest_trial["can_reset"] and st.button(
                    f"Reset free trial ({EXTRA_DAYS // 30} more months)", key="guest_reset_btn", type="primary"):
                reset_trial()
                st.rerun()
            if st.button("Log in", key="guest_ended_login_btn"):
                leave_guest_mode("Re-login")
            if st.button("Make an account", key="guest_ended_register_btn"):
                leave_guest_mode("Register")
        st.stop()

    st.markdown(f"<h1 class='sea-header'>🌊 Hey {html.escape(user_name)}! Sea here!</h1>", unsafe_allow_html=True)
    st.write("Ready to learn something awesome? Ask me ANYTHING! 💪")

    if is_guest:
        guest_info = get_guest_info()
        st.write(f"⏳ **Free Trial:** {guest_info['days_left']} days left | Questions: {guest_info['usage_count']}")
        st.info("After 1 month, you'll need to login to continue. All your chats are saved! 💾")
    else:
        st.write(f"**You:** {user_age} years old | **Me:** Sea, ready to teach!")

    # Top menu with navigation
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        if st.button("📚 Learn", use_container_width=True):
            st.session_state.view_page = "learn"
            st.rerun()
    with col2:
        if st.button("📋 Sessions", use_container_width=True):
            st.session_state.view_page = "sessions"
            st.rerun()
    with col4:
        if st.button("⚙️ Settings", use_container_width=True):
            st.session_state.show_settings = not st.session_state.get("show_settings", False)
            st.rerun()
    with col5:
        if st.button("🔄 Restart", use_container_width=True, help="Fully log out and start Sea fresh"):
            if st.session_state.get("learning_active") and st.session_state.current_session_id and not is_guest:
                end_session(st.session_state.current_session_id, user_email)
            full_restart(user_email)
    with col6:
        if st.button("Logout", use_container_width=True):
            # End the current learning session, even if they're looking at another page
            if st.session_state.get("learning_active") and st.session_state.current_session_id and not is_guest:
                end_session(st.session_state.current_session_id, user_email)
            delete_remember_tokens_for_email(user_email)
            if cookie_manager.get(cookie=REMEMBER_COOKIE):
                cookie_manager.delete(REMEMBER_COOKIE, key="delete_remember")
            reset_user_state()
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.session_state.is_guest = False
            st.rerun()

    # Settings panel
    if st.session_state.get("show_settings", False):
        st.divider()
        st.subheader("⚙️ Settings & Backup")

        if not is_guest:
            with st.expander("👤 My Account", expanded=True):
                def apply_account_change(ok, msg, **updates):
                    if ok:
                        st.session_state.user_data.update(updates)
                        st.session_state.account_msg = msg
                        st.rerun()
                    else:
                        st.error(msg)

                account_msg = st.session_state.pop("account_msg", None)
                if account_msg:
                    st.success(account_msg)

                new_name = st.text_input("Name", value=user_name, key="settings_name")
                if st.button("Change name", key="change_name_btn"):
                    ok, msg = change_name(user_email, new_name)
                    apply_account_change(ok, msg, name=new_name.strip())

                new_age = st.slider("Age", min_value=3, max_value=99, value=int(user_age), key="settings_age")
                if st.button("Change age", key="change_age_btn"):
                    ok, msg = change_age(user_email, int(new_age))
                    apply_account_change(ok, msg, age=int(new_age))

                new_pin = st.text_input("New 4-number PIN", type="password", max_chars=4, key="settings_pin")
                if st.button("Change PIN", key="change_pin_btn"):
                    ok, msg = change_pin(user_email, new_pin.strip())
                    apply_account_change(ok, msg)

                st.divider()
                st.write("**🗑️ Delete my account**")
                st.caption("This deletes your account and all your saved sessions and chats. It can't be undone.")
                sure = st.checkbox("Yes, I really want to delete my account", key="delete_confirm")
                if st.button("Delete my account", key="delete_account_btn", disabled=not sure):
                    delete_account(user_email)
                    full_restart(user_email, "Your account was deleted. 👋")

        if not is_guest:
            with st.expander("🌐 Online mode (smart AI help)", expanded=True):
                st.write("Online mode uses Claude AI to help with **any** question, even complicated ones. "
                         "Offline mode only knows simple maths and a few topics.")

                ai_msg = st.session_state.pop("ai_msg", None)
                if ai_msg:
                    st.success(ai_msg)

                source = key_source()
                if source is None:
                    st.info("No API key yet. A grown-up can make one at **console.anthropic.com**. "
                            "Online mode costs a little money for each message.")

                online = st.toggle("Use online mode", value=online_enabled(), key="online_toggle",
                                   disabled=source is None)
                if source and online != online_enabled():
                    set_online(online)
                    st.rerun()

                if source == "server":
                    st.caption("Using the API key from the app's server settings.")
                else:
                    if source == "saved":
                        st.caption(f"An API key is saved (ending in ...{saved_key_ending()}).")
                        if st.button("Remove saved key", key="remove_key_btn"):
                            remove_api_key()
                            st.rerun()
                    new_key = st.text_input("Paste an Anthropic API key", type="password",
                                            placeholder="sk-ant-...", key="api_key_input")
                    if st.button("Save key", key="save_key_btn"):
                        with st.spinner("Checking the key..."):
                            ok, msg = save_api_key(new_key)
                        if ok:
                            st.session_state.ai_msg = msg
                            st.session_state.pop("online_toggle", None)
                            st.rerun()
                        else:
                            st.error(msg)

        with st.expander("📦 Data Backup & Recovery", expanded=True):
            st.write("**Automatic backups** are created every time the app starts.")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("💾 Create Manual Backup"):
                    from backup import backup_database
                    success, message = backup_database()
                    if success:
                        st.success(message)
                    else:
                        st.error(message)

            with col2:
                if st.button("📂 View Backups"):
                    from backup import list_backups
                    backups = list_backups()
                    if backups:
                        st.write("Available backups:")
                        for backup in backups:
                            size_kb = backup['size'] / 1024
                            st.caption(f"📁 {backup['name']} ({size_kb:.1f} KB)")
                    else:
                        st.info("No backups yet")

            st.info("💡 **Tip:** If the app resets and you can't login with your old account, you can restore from a backup here!")

        st.divider()

    st.divider()

    # SESSIONS PAGE VIEW
    if st.session_state.view_page == "sessions" and not is_guest:
        st.subheader("📋 Your Learning Sessions")

        # Get stats
        stats = get_session_stats(user_email)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Sessions", stats["total_sessions"])
        with col2:
            st.metric("Questions Asked", stats["total_questions"])
        with col3:
            if stats["last_session"]:
                st.metric("Last Session", stats["last_session"][:10])

        st.divider()

        # Get all sessions
        sessions = get_user_sessions(user_email, limit=50)

        if sessions:
            st.write(f"**Your {len(sessions)} Recent Sessions:**")

            for session in sessions:
                session_id, question, started_at, ended_at, status, questions_count = session

                with st.expander(f"📌 {question[:50]}... ({status}) - {started_at[:10]}", expanded=False):
                    st.write(f"**Session ID:** {session_id}")
                    st.write(f"**Started:** {started_at}")
                    if ended_at:
                        st.write(f"**Ended:** {ended_at}")
                    st.write(f"**Questions Asked:** {questions_count}")
                    st.write(f"**Status:** {status}")

                    # Show session details
                    if st.button(f"View Full Session", key=f"view_{session_id}"):
                        session_info, messages = get_session_details(session_id, user_email)

                        st.write("---")
                        st.write("**Session Conversation:**")

                        for msg_type, content, timestamp in messages:
                            if msg_type == "student":
                                with st.chat_message("user"):
                                    st.write(content[:200] + "..." if len(content) > 200 else content)
                            else:
                                with st.chat_message("assistant", avatar="🌊"):
                                    st.write(content[:300] + "..." if len(content) > 300 else content)

                    # Delete option
                    if st.button(f"🗑️ Delete Session", key=f"delete_{session_id}"):
                        delete_session(session_id, user_email)
                        st.success("Session deleted!")
                        st.rerun()
        else:
            st.info("No learning sessions yet. Start learning to create your first session! 🌊")

        st.stop()  # Don't show learning interface when viewing sessions

    # Initialize session state for learning session
    if "learning_active" not in st.session_state:
        st.session_state.learning_active = False
        st.session_state.current_question = None
        st.session_state.learning_stage = "initial"
        st.session_state.student_answer = ""
        st.session_state.conversation = []
        st.session_state.step_count = 0

    # Main question answering interface
    if not st.session_state.learning_active:
        # Show "New Session" button to reset the form
        if st.button("➕ New Session", use_container_width=False):
            st.session_state.current_session_id = None
            st.rerun()

        st.subheader("💡 Ask Me Anything")
        st.write("Ask any question, and I'll help you learn by explaining concepts and asking guiding questions.")

        question = st.text_area("Your Question:", placeholder="e.g., How does photosynthesis work? What is algebra? How do magnets work?", height=100, key="user_question")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Learning", type="primary"):
                if question.strip():
                    # Create new session (unless guest)
                    if not is_guest:
                        session_id = create_new_session(user_email, question)
                        st.session_state.current_session_id = session_id

                    st.session_state.learning_active = True
                    st.session_state.opening_question = question
                    st.session_state.current_question = question
                    st.session_state.learning_stage = "intro"
                    st.session_state.closing_stage = None
                    st.session_state.conversation = []
                    st.session_state.step_count = 0
                    st.rerun()
                else:
                    st.warning("Please enter a question first!")

    else:
        # Interactive learning conversation with AI (or offline mode)
        st.subheader("📚 Learning Session")
        st.caption(f"Question: {st.session_state.current_question}")
        answers_given = sum(1 for m in st.session_state.conversation if m["type"] == "student")
        st.progress(min(answers_given / 5, 1.0), text=f"Session progress: {min(answers_given, 5)} of 5 answers")

        api_available = is_ai_available()
        opening_question = st.session_state.get("opening_question") or st.session_state.current_question

        if not api_available:
            st.info("💡 Running in **Offline Mode** - simple maths and a few topics only. For help with complicated questions, turn on **Online mode** in ⚙️ Settings.")

        # Get initial explanation if starting
        if st.session_state.learning_stage == "intro":
            with st.spinner("🌊 Sea is thinking..."):
                from teaching import start_learning_session

                from teach_simple import mentions_book, BOOK_QUESTION

                intro_response = BOOK_QUESTION if mentions_book(opening_question) else None
                if intro_response is None and api_available:
                    try:
                        intro_response = tutor_reply(opening_question, [], user_name, user_age)
                    except Exception:
                        traceback.print_exc()  # fall back to offline guidance below instead of retrying on every rerun
                if intro_response is None:
                    intro_response = start_learning_session(st.session_state.current_question, user_age)

                if is_guest:
                    record_guest_usage()
                intro = {"type": "sea", "content": intro_response}
                st.session_state.conversation.append(intro)
                save_to_history(intro, user_email, is_guest)
                st.session_state.learning_stage = "answering"
                st.rerun()

        # Chat interface
        if st.session_state.learning_stage == "answering":
            # Chat options bar
            col1, col2 = st.columns([6, 1])

            with col2:
                if st.button("💡 Hint", use_container_width=True):
                    with st.spinner("Getting hint..."):
                        try:
                            if api_available:
                                hint = get_hint_ai(opening_question, st.session_state.conversation, user_name, user_age)
                            else:
                                from teaching import get_hint
                                hint = get_hint(st.session_state.current_question, user_age)
                        except Exception:
                            report_error()
                        else:
                            hint_msg = {"type": "hint", "content": hint}
                            st.session_state.conversation.append(hint_msg)
                            save_to_history(hint_msg, user_email, is_guest)
                            st.rerun()

            st.divider()

            # Chat messages
            chat_container = st.container(height=400)

            with chat_container:
                for msg in st.session_state.conversation:
                    if msg["type"] == "sea":
                        with st.chat_message("assistant", avatar="🌊"):
                            show_text(msg["content"])
                    elif msg["type"] == "student":
                        with st.chat_message("user"):
                            show_text(msg["content"])
                    elif msg["type"] == "hint":
                        with st.chat_message("assistant", avatar="💡"):
                            show_text(f"**Hint:** {msg['content']}")

            st.divider()

            # A new key after each picture empties the uploader, so the same photo isn't sent twice
            uploaded = st.file_uploader(
                "📷 Stuck on an exam or homework question? Upload a picture of it",
                type=["png", "jpg", "jpeg"],
                key=f"problem_pic_{st.session_state.get('pic_round', 0)}",
            )
            if api_available:
                st.caption("Messages and pictures are sent to Anthropic's Claude AI so Sea can help. "
                           "Please don't upload pictures that show faces, full names or addresses.")
            if uploaded and st.button("Help me with this picture", key="pic_help_btn"):
                if api_available:
                    try:
                        image_bytes, media_type = prepare_image(uploaded.getvalue())
                    except ValueError:
                        st.error("Sea couldn't open that picture. Try a clear PNG or JPG photo.")
                    else:
                        pic_msg = {
                            "type": "student",
                            "content": "📷 Here's a picture of a problem I'm stuck on. Can you help me work it out?",
                            "image": image_bytes,
                            "media_type": media_type,
                        }
                        st.session_state.conversation.append(pic_msg)
                        with st.spinner("🌊 Sea is looking at your picture..."):
                            try:
                                help_text = tutor_reply(opening_question, st.session_state.conversation, user_name, user_age)
                            except Exception:
                                drop_last(pic_msg)
                                report_error()
                            else:
                                add_reply(pic_msg, help_text, user_email, is_guest)
                                st.session_state.pic_round = st.session_state.get("pic_round", 0) + 1
                                st.rerun()
                else:
                    st.info("Picture help needs AI mode. Add your ANTHROPIC_API_KEY to use it.")

            # "What kind of book?" buttons, while that is the latest question from Sea
            from teach_simple import BOOK_QUESTION
            conv = st.session_state.conversation
            if conv and conv[-1]["type"] == "sea" and conv[-1]["content"] == BOOK_QUESTION:
                b1, b2, b3 = st.columns(3)
                picked = None
                if b1.button("📖 Reading", key="book_reading", use_container_width=True):
                    picked = ("reading", "It's a reading book (a story, comic or poems).")
                if b2.button("🎓 Learning", key="book_learning", use_container_width=True):
                    picked = ("learning", "It's a learning book that teaches facts.")
                if b3.button("🛠️ Instructions", key="book_instructions", use_container_width=True):
                    picked = ("instructions", "It's an instructions book that tells you how to do or make something.")
                if picked:
                    from teaching import book_type_in, book_type_help
                    pick_msg = {"type": "student", "content": picked[1]}
                    conv.append(pick_msg)
                    try:
                        reply = (tutor_reply(opening_question, conv, user_name, user_age) if api_available
                                 else book_type_help(book_type_in(picked[0])))
                    except Exception:
                        drop_last(pick_msg)
                        report_error()
                    else:
                        add_reply(pick_msg, reply, user_email, is_guest)
                        st.rerun()

            # Chat input - bottom row
            col1, col2 = st.columns([6, 1])

            with col1:
                user_message = st.chat_input("Type your answer or ask a question...", key="chat_input")

            # Process message if entered
            if user_message:
                from teaching import (
                    start_learning_session, get_next_teaching_step, is_new_question, mentions_new_question,
                    closing_step, SURE_PROMPT, is_goodbye, GOODBYE_REPLY, is_dont_know, step_by_step_help,
                    is_done, LEARN_MORE_PROMPT,
                )

                closing = st.session_state.get("closing_stage")
                current = st.session_state.current_question
                last_sea = next((m["content"] for m in reversed(st.session_state.conversation) if m["type"] == "sea"), "")
                awaiting_explanation = "explain HOW" in last_sea

                student_msg = {"type": "student", "content": user_message}
                st.session_state.conversation.append(student_msg)

                with st.spinner("🌊 Sea is thinking..."):
                    try:
                        if api_available:
                            # Claude follows the whole tutoring flow itself (see ai_tutor.SYSTEM_TEMPLATE)
                            if is_new_question(user_message, current):
                                st.session_state.current_question = user_message
                            response = tutor_reply(opening_question, st.session_state.conversation, user_name, user_age)
                        elif is_goodbye(user_message):
                            response = GOODBYE_REPLY
                        elif is_done(user_message):
                            response = LEARN_MORE_PROMPT
                            st.session_state.closing_stage = "learn_more"
                        elif is_dont_know(user_message) and not mentions_new_question(user_message, current):
                            response = step_by_step_help(current, user_age)
                        elif closing in ("sure", "learn_more"):
                            response, st.session_state.closing_stage = closing_step(closing, user_message)
                        elif closing == "need_help" or is_new_question(user_message, current, awaiting_explanation) \
                                or mentions_new_question(user_message, current):
                            st.session_state.closing_stage = None
                            st.session_state.current_question = user_message
                            response = start_learning_session(user_message, user_age)
                        else:
                            response = get_next_teaching_step(
                                current, user_message, user_age, st.session_state.step_count,
                                awaiting_explanation=awaiting_explanation,
                            )
                            if response == SURE_PROMPT:
                                st.session_state.closing_stage = "sure"
                    except Exception:
                        drop_last(student_msg)
                        report_error()
                    else:
                        add_reply(student_msg, response, user_email, is_guest)
                        st.rerun()

            with col2:
                if st.button("🏁 End", use_container_width=True, key="end_session_btn"):
                    # End session in database (if not guest)
                    if st.session_state.current_session_id and not is_guest:
                        end_session(st.session_state.current_session_id, user_email)

                    st.session_state.learning_active = False
                    st.session_state.learning_stage = "initial"
                    st.session_state.conversation = []
                    st.session_state.current_session_id = None
                    st.success("Great learning session! 🌊")
                    st.rerun()
