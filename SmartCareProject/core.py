import hashlib
import hmac
import os
import re
from datetime import date, datetime, timedelta

import mysql.connector
from mysql.connector import Error, IntegrityError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DB_CONFIG = dict(host="localhost", user="root", password="", database="smartcare")
SLOT_MINUTES = 30
MAX_ADVANCE_DAYS = 90        # how far ahead appointments may be booked
MAX_AGE_YEARS = 120          # oldest believable date of birth
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATUSES = ["Scheduled", "Completed", "Cancelled", "No-Show"]


class InputError(ValueError):
    """A user-facing error that always says what went wrong AND how to fix it."""
    def __init__(self, problem, fix):
        super().__init__(f"{problem}\n\nHow to fix: {fix}")
        self.problem, self.fix = problem, fix


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def connect():
    return mysql.connector.connect(**DB_CONFIG)


def run(sql, params=(), write=False):
    """Run one statement. Returns rows for SELECT, lastrowid for writes."""
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        if write:
            conn.commit()
            return cur.lastrowid
        return cur.fetchall()
    finally:
        conn.close()


def transaction(work):
    """Run work(cursor) as one all-or-nothing transaction."""
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        result = work(cur)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def describe_db_error(e):
    code = getattr(e, "errno", None)
    if code in (2002, 2003, 2006, 2013):
        return InputError("The system could not reach the database.",
                          "Make sure MySQL/MariaDB is running (start it from XAMPP/WAMP), then try again.")
    if code == 1045:
        return InputError("The database refused the username or password in DB_CONFIG.",
                          "Open core.py and correct the user/password in DB_CONFIG.")
    if code in (1049, 1146):
        return InputError("The SmartCare database or one of its tables is missing.",
                          "Import schema.sql using phpMyAdmin (Import tab), then restart the program.")
    return InputError(f"A database error occurred: {getattr(e, 'msg', e)}",
                      "Try the action again. If it keeps happening, tell the clinic administrator.")


# --------------------------------------------------------------------------- #
# Parsing & validation
# --------------------------------------------------------------------------- #
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")
TIME_FORMATS = ("%H:%M", "%I:%M%p", "%I:%M %p", "%I%p", "%I %p")


def date_hint():
    return f"DD/MM/YYYY or YYYY-MM-DD, for example {date.today():%d/%m/%Y}"


def parse_date(text, label="Date"):
    t = (text or "").strip()
    if not t:
        raise InputError(f"{label} is empty.", f"Enter the date as {date_hint()}.")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise InputError(f"'{t}' is not a valid {label.lower()}.",
                     f"Use {date_hint()}. Check that the day and month really exist "
                     "(months 1-12, no 31 April, no 30 February).")


def parse_time(text, label="Time"):
    t = (text or "").strip().upper()
    if not t:
        raise InputError(f"{label} is empty.", "Enter a time such as 09:30, 14:00 or 2:15pm.")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(t, fmt).time()
        except ValueError:
            pass
    raise InputError(f"'{text.strip()}' is not a valid {label.lower()}.",
                     "Use 24-hour HH:MM (e.g. 14:30) or 12-hour with am/pm (e.g. 2:30pm).")


def require(data, fields):
    """fields: list of (key, label). Reports ALL empty required fields at once."""
    missing = [label.replace(" *", "") for key, label in fields if not (data.get(key) or "").strip()]
    if missing:
        raise InputError("These required fields are empty: " + ", ".join(missing) + ".",
                         "Fill in every field marked with * and try again.")


def validate_booking_date(d):
    today = date.today()
    latest = today + timedelta(days=MAX_ADVANCE_DAYS)
    if d < today:
        raise InputError(f"{d:%d/%m/%Y} is in the past.",
                         f"Choose today ({today:%d/%m/%Y}) or a later date.")
    if d > latest:
        raise InputError(f"{d:%d/%m/%Y} is too far in the future - bookings open up to "
                         f"{MAX_ADVANCE_DAYS} days ahead.",
                         f"Choose a date on or before {latest:%d/%m/%Y}.")


def normalise_phone(text):
    digits = re.sub(r"\D", "", text or "")
    if digits.startswith("61") and len(digits) == 11:   # +61 4xx -> 04xx
        digits = "0" + digits[2:]
    return digits


NAME_RE = re.compile(r"[A-Za-z\u00C0-\u024F'\u2019 .\-]+")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

PATIENT_REQUIRED = [("first_name", "First name *"), ("last_name", "Last name *"),
                    ("dob", "Date of birth *"), ("phone", "Phone *")]


def validate_patient(d, patient_id=None):
    for k in d:
        d[k] = re.sub(r"\s+", " ", d[k] or "").strip()
    require(d, PATIENT_REQUIRED)
    for key, label in (("first_name", "First name"), ("last_name", "Last name")):
        if not NAME_RE.fullmatch(d[key]):
            raise InputError(f"{label} '{d[key]}' contains characters that are not allowed.",
                             "Use letters, spaces, hyphens and apostrophes only (e.g. Mary-Anne O'Brien).")
    dob = parse_date(d["dob"], "Date of birth")
    if dob > date.today():
        raise InputError(f"Date of birth {dob:%d/%m/%Y} is in the future.",
                         "Enter the patient's real date of birth.")
    if dob < date.today() - timedelta(days=365 * MAX_AGE_YEARS):
        raise InputError(f"Date of birth {dob:%d/%m/%Y} is more than {MAX_AGE_YEARS} years ago.",
                         "Check the year was typed correctly (4 digits, e.g. 1985).")
    n = len(normalise_phone(d["phone"]))
    if not 8 <= n <= 15:
        raise InputError(f"Phone number '{d['phone']}' has {n} digits.",
                         "Enter 8-15 digits, e.g. 0412 345 678 or +61 412 345 678.")
    if d["email"] and not EMAIL_RE.fullmatch(d["email"]):
        raise InputError(f"Email '{d['email']}' is not a valid address.",
                         "Use the form name@example.com, or leave the field blank.")
    dup = run("SELECT patient_id FROM patients WHERE first_name=%s AND last_name=%s "
              "AND dob=%s AND patient_id<>%s", (d["first_name"], d["last_name"], dob, patient_id or 0))
    if dup:
        raise InputError(f"A patient with this name and date of birth already exists "
                         f"(Patient ID {dup[0]['patient_id']}).",
                         "Search for the existing record instead of creating a new one.")
    return dob


# --------------------------------------------------------------------------- #
# Staff Authentication
# --------------------------------------------------------------------------- #
def hash_password(password, iterations=200_000):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password, stored):
    try:
        _, iters, salt, expected = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, AttributeError):
        return False


def authenticate_staff(username, password):
    username = (username or "").strip()
    if not username:
        raise InputError("The username is empty.", "Type the username issued to you by the clinic administrator.")
    if not password:
        raise InputError("The password is empty.", "Type your password, then press Log in.")
    bad = ("Incorrect username or password.",
           "Check that Caps Lock is off - the password is case-sensitive (the username is not). "
           "If you have forgotten your details, ask the clinic administrator to reset them.")
    rows = run("SELECT *, (locked_until IS NOT NULL AND locked_until > NOW()) AS is_locked "
               "FROM staff_accounts WHERE username=%s", (username,))   # case-insensitive collation
    if not rows:
        raise InputError(*bad)
    acct = rows[0]
    if not acct["active"]:
        raise InputError("This account has been disabled.", "Ask the clinic administrator to re-enable it.")
    if acct["is_locked"]:
        raise InputError("This account is temporarily locked after too many failed log-in attempts.",
                         f"Wait {LOCK_MINUTES} minutes and try again, or ask the administrator to unlock it.")
    if verify_password(password, acct["password_hash"]):
        run("UPDATE staff_accounts SET failed_attempts=0, locked_until=NULL, last_login=NOW() "
            "WHERE staff_id=%s", (acct["staff_id"],), write=True)
        return acct
    fails = acct["failed_attempts"] + 1
    if fails >= MAX_FAILED_LOGINS:
        run("UPDATE staff_accounts SET failed_attempts=0, locked_until=DATE_ADD(NOW(), INTERVAL %s MINUTE) "
            "WHERE staff_id=%s", (LOCK_MINUTES, acct["staff_id"]), write=True)
        raise InputError("Incorrect password. This account is now locked for "
                         f"{LOCK_MINUTES} minutes.", "Wait, then try again with the correct password.")
    run("UPDATE staff_accounts SET failed_attempts=%s WHERE staff_id=%s", (fails, acct["staff_id"]), write=True)
    raise InputError(bad[0], bad[1] + f" ({MAX_FAILED_LOGINS - fails} attempt(s) left before the account locks.)")


# --------------------------------------------------------------------------- #
# Patient Identity Check (Patient App)
# --------------------------------------------------------------------------- #
def authenticate_patient(first, last, dob_text, phone):
    data = dict(first=first, last=last, dob=dob_text, phone=phone)
    require(data, [("first", "First name *"), ("last", "Last name *"),
                   ("dob", "Date of birth *"), ("phone", "Phone number *")])
    dob = parse_date(dob_text, "Date of birth")
    rows = run("SELECT patient_id, first_name, last_name, phone FROM patients "
               "WHERE first_name=%s AND last_name=%s AND dob=%s", (first.strip(), last.strip(), dob))
    for r in rows:
        if normalise_phone(r["phone"]) == normalise_phone(phone):
            return r
    raise InputError("We could not find a patient matching those details.",
                     "Check the spelling of your name (capital letters do not matter), your date of birth, "
                     "and the phone number the clinic has on file. New patients must register at the clinic "
                     "reception first - registration is not available online.")


# --------------------------------------------------------------------------- #
# Practitioners & Availability
# --------------------------------------------------------------------------- #
def save_practitioner(d, prac_id=None):
    d = {k: re.sub(r"\s+", " ", v or "").strip() for k, v in d.items()}
    require(d, [("full_name", "Full name *")])
    if d["email"] and not EMAIL_RE.fullmatch(d["email"]):
        raise InputError(f"Email '{d['email']}' is not a valid address.",
                         "Use the form name@example.com, or leave the field blank.")
    vals = (d["full_name"], d["specialty"] or "General Practice", d["phone"] or None, d["email"] or None)
    if prac_id:
        run("UPDATE practitioners SET full_name=%s,specialty=%s,phone=%s,email=%s "
            "WHERE practitioner_id=%s", vals + (prac_id,), write=True)
    else:
        run("INSERT INTO practitioners (full_name,specialty,phone,email) VALUES (%s,%s,%s,%s)",
            vals, write=True)


def minutes(v):
    if isinstance(v, timedelta):
        return int(v.total_seconds() // 60)
    return v.hour * 60 + v.minute


def to_hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt_time(v):
    return to_hhmm(minutes(v)) if v is not None and v != "" else ""


def fmt_dt(v):
    return v.strftime("%Y-%m-%d %H:%M") if v else ""


def add_availability(prac_id, dow, start_txt, end_txt):
    start, end = parse_time(start_txt, "Start time"), parse_time(end_txt, "End time")
    s, e = minutes(start), minutes(end)
    if s >= e:
        raise InputError(f"The start time {to_hhmm(s)} is not before the end time {to_hhmm(e)}.",
                         "Make the end time later than the start time.")
    if e - s < SLOT_MINUTES:
        raise InputError(f"A window must be at least {SLOT_MINUTES} minutes long.",
                         "Choose a later end time.")
    for r in run("SELECT start_time,end_time FROM practitioner_availability "
                 "WHERE practitioner_id=%s AND day_of_week=%s", (prac_id, dow)):
        if s < minutes(r["end_time"]) and e > minutes(r["start_time"]):
            raise InputError(f"This overlaps the existing {DAYS[dow]} window "
                             f"{fmt_time(r['start_time'])}-{fmt_time(r['end_time'])}.",
                             "Remove the existing window first, or pick times that do not overlap it.")
    run("INSERT INTO practitioner_availability (practitioner_id,day_of_week,start_time,end_time) "
        "VALUES (%s,%s,%s,%s)", (prac_id, dow, start, end), write=True)


def free_slots(prac_id, d):
    """Open 30-minute slots for a practitioner on a date."""
    prac = run("SELECT active FROM practitioners WHERE practitioner_id=%s", (prac_id,))
    if not prac or not prac[0]["active"]:
        return []
    slots = set()
    for w in run("SELECT start_time,end_time FROM practitioner_availability "
                 "WHERE practitioner_id=%s AND day_of_week=%s", (prac_id, d.weekday())):
        t, end = minutes(w["start_time"]), minutes(w["end_time"])
        while t + SLOT_MINUTES <= end:
            slots.add(t)
            t += SLOT_MINUTES
    for b in run("SELECT appt_time FROM appointments WHERE practitioner_id=%s "
                 "AND appt_date=%s AND status<>'Cancelled'", (prac_id, d)):
        slots.discard(minutes(b["appt_time"]))
    if d == date.today():
        now = datetime.now()
        slots = {s for s in slots if s > now.hour * 60 + now.minute}
    return [to_hhmm(s) for s in sorted(slots)]


# --------------------------------------------------------------------------- #
# Appointments
# --------------------------------------------------------------------------- #
def log_history(cur, appt_id, action, actor, old_status=None, new_status=None,
                old_dt=None, new_dt=None, notes=None):
    cur.execute("INSERT INTO appointment_history (appointment_id,action,old_status,new_status,"
                "old_datetime,new_datetime,notes,changed_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (appt_id, action, old_status, new_status, old_dt, new_dt, notes, actor))


def _check_slot(patient_id, prac_id, d, tstr, ignore_appt=None):
    if not tstr:
        raise InputError("No time slot has been chosen.",
                         "Press 'Find open slots', then pick a time from the Time slot list.")
    validate_booking_date(d)
    if tstr not in free_slots(prac_id, d):
        raise InputError(f"{tstr} on {d:%d/%m/%Y} is not available with this practitioner "
                         "(outside their working hours, or already booked).",
                         "Press 'Find open slots' and choose one of the listed times, "
                         "or try a different date or practitioner.")
    clash = run("SELECT appointment_id FROM appointments WHERE patient_id=%s AND appt_date=%s "
                "AND appt_time=%s AND status<>'Cancelled' AND appointment_id<>%s",
                (patient_id, d, tstr, ignore_appt or 0))
    if clash:
        raise InputError("This patient already has another appointment at that date and time.",
                         "Choose a different time.")


def _taken():
    return InputError("That slot was booked by someone else a moment ago.",
                      "Press 'Find open slots' to refresh the list and choose another time.")


def book_appointment(patient_id, prac_id, d, tstr, reason, actor):
    _check_slot(patient_id, prac_id, d, tstr)
    reason = (reason or "").strip() or None

    def work(cur):
        cur.execute("INSERT INTO appointments (patient_id,practitioner_id,appt_date,appt_time,reason) "
                    "VALUES (%s,%s,%s,%s,%s)", (patient_id, prac_id, d, tstr, reason))
        appt_id = cur.lastrowid
        log_history(cur, appt_id, "Booked", actor, None, "Scheduled", None, f"{d} {tstr}", reason)
        return appt_id
    try:
        return transaction(work)
    except IntegrityError:           
        raise _taken()


def get_appt(appt_id, owner_id=None):
    rows = run("SELECT * FROM appointments WHERE appointment_id=%s", (appt_id,))
    if not rows or (owner_id and rows[0]["patient_id"] != owner_id):
        raise InputError("That appointment could not be found.",
                         "Refresh the list and select one of your appointments.")
    return rows[0]


def _require_scheduled(a, verb, owner_id):
    if a["status"] != "Scheduled":
        raise InputError(f"This appointment is {a['status']}, so it cannot be {verb}.",
                         "Only Scheduled appointments can be changed.")
    if owner_id and datetime.combine(a["appt_date"], datetime.min.time()) + a["appt_time"] < datetime.now():
        raise InputError("This appointment time has already passed.",
                         "Please contact the clinic reception for help.")


def cancel_appointment(appt_id, reason, actor, owner_id=None):
    a = get_appt(appt_id, owner_id)
    _require_scheduled(a, "cancelled", owner_id)
    reason = (reason or "").strip() or None

    def work(cur):
        cur.execute("UPDATE appointments SET status='Cancelled', cancellation_reason=%s "
                    "WHERE appointment_id=%s", (reason, appt_id))
        log_history(cur, appt_id, "Cancelled", actor, "Scheduled", "Cancelled", notes=reason)
    transaction(work)


def reschedule_appointment(appt_id, prac_id, d, tstr, actor, owner_id=None):
    a = get_appt(appt_id, owner_id)
    _require_scheduled(a, "rescheduled", owner_id)
    old_t = fmt_time(a["appt_time"])
    if (a["practitioner_id"], a["appt_date"], old_t) == (prac_id, d, tstr):
        raise InputError("The new time is the same as the current booking.", "Choose a different time slot.")
    _check_slot(a["patient_id"], prac_id, d, tstr, ignore_appt=appt_id)

    def work(cur):
        cur.execute("UPDATE appointments SET practitioner_id=%s, appt_date=%s, appt_time=%s "
                    "WHERE appointment_id=%s", (prac_id, d, tstr, appt_id))
        note = "Practitioner changed" if prac_id != a["practitioner_id"] else None
        log_history(cur, appt_id, "Rescheduled", actor, "Scheduled", "Scheduled",
                    f"{a['appt_date']} {old_t}", f"{d} {tstr}", note)
    try:
        transaction(work)
    except IntegrityError:
        raise _taken()


def set_status(appt_id, new_status, actor):
    a = get_appt(appt_id)
    _require_scheduled(a, "updated", None)
    if a["appt_date"] > date.today():
        raise InputError(f"This appointment is on {a['appt_date']:%d/%m/%Y}, in the future.",
                         f"It can only be marked {new_status} on or after the appointment day. "
                         "Use Cancel if the patient will not attend.")

    def work(cur):
        cur.execute("UPDATE appointments SET status=%s WHERE appointment_id=%s", (new_status, appt_id))
        log_history(cur, appt_id, "Status change", actor, "Scheduled", new_status)
    transaction(work)


def list_appointments(d=None, prac_id=None, status=None, patient_id=None, from_date=None):
    sql = ("SELECT a.appointment_id, a.appt_date, a.appt_time, a.status, a.reason, "
           "CONCAT(p.first_name,' ',p.last_name) AS patient, pr.full_name AS practitioner "
           "FROM appointments a JOIN patients p ON p.patient_id=a.patient_id "
           "JOIN practitioners pr ON pr.practitioner_id=a.practitioner_id WHERE 1=1")
    params = []
    for cond, val in (("a.appt_date=%s", d), ("a.practitioner_id=%s", prac_id), ("a.status=%s", status),
                      ("a.patient_id=%s", patient_id), ("a.appt_date>=%s", from_date)):
        if val:
            sql += " AND " + cond
            params.append(val)
    return run(sql + " ORDER BY a.appt_date, a.appt_time", params)


def search_patients(term=""):
    term = (term or "").strip()
    like = f"%{term}%"
    return run("SELECT * FROM patients WHERE CONCAT(first_name,' ',last_name) LIKE %s "
               "OR phone LIKE %s OR CAST(patient_id AS CHAR)=%s ORDER BY last_name, first_name",
               (like, like, term))


def save_patient(d, patient_id=None):
    dob = validate_patient(d, patient_id)
    vals = (d["first_name"], d["last_name"], dob, d["phone"], d["email"] or None,
            d["address"] or None, d["notes"] or None)
    if patient_id:
        run("UPDATE patients SET first_name=%s,last_name=%s,dob=%s,phone=%s,email=%s,"
            "address=%s,notes=%s WHERE patient_id=%s", vals + (patient_id,), write=True)
    else:
        run("INSERT INTO patients (first_name,last_name,dob,phone,email,address,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)", vals, write=True)


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
REPORTS = {
    "Appointments by status": (
        ["Status", "Appointments"],
        "SELECT status, COUNT(*) FROM appointments WHERE appt_date BETWEEN %s AND %s "
        "GROUP BY status ORDER BY COUNT(*) DESC"),
    "Practitioner workload": (
        ["Practitioner", "Total", "Scheduled", "Completed", "Cancelled", "No-Show", "Cancel rate %"],
        "SELECT pr.full_name, COUNT(*), SUM(a.status='Scheduled'), SUM(a.status='Completed'), "
        "SUM(a.status='Cancelled'), SUM(a.status='No-Show'), "
        "ROUND(100*SUM(a.status='Cancelled')/COUNT(*),1) "
        "FROM appointments a JOIN practitioners pr ON pr.practitioner_id=a.practitioner_id "
        "WHERE a.appt_date BETWEEN %s AND %s GROUP BY pr.practitioner_id, pr.full_name"),
    "Daily appointment volume": (
        ["Date", "Total booked (excl. cancelled)"],
        "SELECT appt_date, COUNT(*) FROM appointments WHERE status<>'Cancelled' "
        "AND appt_date BETWEEN %s AND %s GROUP BY appt_date ORDER BY appt_date"),
    "Cancellations": (
        ["Date", "Time", "Patient", "Practitioner", "Reason"],
        "SELECT a.appt_date, TIME_FORMAT(a.appt_time,'%H:%i'), CONCAT(p.first_name,' ',p.last_name), "
        "pr.full_name, a.cancellation_reason FROM appointments a "
        "JOIN patients p ON p.patient_id=a.patient_id "
        "JOIN practitioners pr ON pr.practitioner_id=a.practitioner_id "
        "WHERE a.status='Cancelled' AND a.appt_date BETWEEN %s AND %s ORDER BY a.appt_date"),
    "New patient registrations": (
        ["Date registered", "New patients"],
        "SELECT DATE(created_at), COUNT(*) FROM patients "
        "WHERE DATE(created_at) BETWEEN %s AND %s GROUP BY DATE(created_at) ORDER BY 1"),
}


def run_report(name, start_text, end_text):
    start, end = parse_date(start_text, "'From' date"), parse_date(end_text, "'To' date")
    if start > end:
        raise InputError(f"The 'From' date ({start:%d/%m/%Y}) is after the 'To' date ({end:%d/%m/%Y}).",
                         "Swap the dates so 'From' is the earlier one.")
    cols, sql = REPORTS[name]
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, (start, end))
        rows = [tuple("" if v is None else v for v in r) for r in cur.fetchall()]
    finally:
        conn.close()
    return cols, rows
