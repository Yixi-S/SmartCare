import tkinter as tk
from datetime import date
from functools import wraps
from tkinter import messagebox, ttk

from mysql.connector import Error

import core
from core import InputError


# --------------------------------------------------------------------------- #
# Error reporting
# --------------------------------------------------------------------------- #
def report_error(e, parent=None):
    if isinstance(e, ValueError):                       # InputError and other validation problems
        messagebox.showwarning("Please check your input", str(e), parent=parent)
    elif isinstance(e, Error):
        messagebox.showerror("Database problem", str(core.describe_db_error(e)), parent=parent)
    else:
        messagebox.showerror("Unexpected problem",
                             f"Something went wrong: {e}\n\nHow to fix: Try again. If it keeps "
                             "happening, tell the clinic administrator.", parent=parent)


def guarded(fn):
    """Turn any exception raised by a button handler into a clear dialog."""
    @wraps(fn)
    def wrapper(*a, **k):
        parent = a[0] if a and isinstance(a[0], tk.Misc) else None
        try:
            return fn(*a, **k)
        except Exception as e:
            report_error(e, parent)
    return wrapper


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
def make_tree(parent, cols):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
    for cid, head, width in cols:
        tree.heading(cid, text=head)
        tree.column(cid, width=width, anchor="w")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def fill(tree, rows):
    tree.delete(*tree.get_children())
    for iid, vals in rows:
        tree.insert("", "end", iid=None if iid is None else str(iid), values=vals)


def selected(tree):
    sel = tree.selection()
    if not sel:
        raise InputError("No row is selected.", "Click a row in the table first, then press the button again.")
    return int(sel[0])


def button_bar(parent, buttons):
    bar = ttk.Frame(parent)
    for text, cmd in buttons:
        ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=3)
    return bar


class TableWindow(tk.Toplevel):
    """Read-only popup table."""
    def __init__(self, parent, title, cols, rows, width=800):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x380")
        frame, tree = make_tree(self, cols)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        fill(tree, [(None, r) for r in rows])


class Form(tk.Toplevel):
    """Generic modal form of text fields."""
    def __init__(self, parent, title, fields, values, on_save):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.on_save, self.entries = on_save, {}
        for i, (key, label) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="e", padx=8, pady=4)
            e = ttk.Entry(self, width=38)
            e.grid(row=i, column=1, padx=8, pady=4)
            e.insert(0, "" if values.get(key) is None else str(values[key]))
            self.entries[key] = e
        button_bar(self, [("Save", self.save), ("Cancel", self.destroy)]).grid(
            row=len(fields), column=0, columnspan=2, pady=10)

    def save(self):
        data = {k: e.get() for k, e in self.entries.items()}
        try:
            self.on_save(data)
        except Exception as e:
            report_error(e, self)
            return
        self.destroy()


# --------------------------------------------------------------------------- #
# Booking / Rescheduling 
# --------------------------------------------------------------------------- #
class BookingDialog(tk.Toplevel):
    """
    Staff booking:       BookingDialog(parent, on_done, actor=...)                  (patient picker shown)
    Patient booking:     BookingDialog(parent, on_done, actor=..., patient_id=ID)
    Rescheduling:        BookingDialog(parent, on_done, actor=..., appt=row, owner_id=ID or None)
    """
    def __init__(self, parent, on_done, actor, patient_id=None, appt=None, owner_id=None):
        super().__init__(parent)
        self.on_done, self.actor, self.appt = on_done, actor, appt
        self.patient_id, self.owner_id = patient_id, owner_id
        self.title("Reschedule appointment" if appt else "Book appointment")
        self.transient(parent)
        self.grab_set()

        self.pracs = {p["full_name"]: p["practitioner_id"]
                      for p in core.run("SELECT practitioner_id, full_name FROM practitioners "
                                        "WHERE active=1 ORDER BY full_name")}
        r = 0
        self.patient = None
        if patient_id is None and appt is None:           # staff picks the patient
            self.patients = {f"#{p['patient_id']}  {p['first_name']} {p['last_name']} ({p['dob']:%d/%m/%Y})":
                             p["patient_id"] for p in core.run(
                                 "SELECT * FROM patients ORDER BY last_name, first_name")}
            ttk.Label(self, text="Patient").grid(row=r, column=0, sticky="e", padx=8, pady=5)
            self.patient = ttk.Combobox(self, values=list(self.patients), state="readonly", width=42)
            self.patient.grid(row=r, column=1, columnspan=2, padx=8)
            r += 1
        ttk.Label(self, text="Practitioner").grid(row=r, column=0, sticky="e", padx=8, pady=5)
        self.prac = ttk.Combobox(self, values=list(self.pracs), state="readonly", width=42)
        self.prac.grid(row=r, column=1, columnspan=2, padx=8)
        self.prac.bind("<<ComboboxSelected>>", lambda _: self.slot.set("") or self.slot.configure(values=[]))
        r += 1
        ttk.Label(self, text="Date").grid(row=r, column=0, sticky="e", padx=8, pady=5)
        self.date = ttk.Entry(self, width=16)
        self.date.grid(row=r, column=1, sticky="w", padx=8)
        ttk.Button(self, text="Find open slots", command=self.find).grid(row=r, column=2, sticky="w")
        r += 1
        ttk.Label(self, text=f"Format: {core.date_hint()}", foreground="gray").grid(
            row=r, column=1, columnspan=2, sticky="w", padx=8)
        r += 1
        ttk.Label(self, text="Time slot").grid(row=r, column=0, sticky="e", padx=8, pady=5)
        self.slot = ttk.Combobox(self, values=[], state="readonly", width=14)
        self.slot.grid(row=r, column=1, sticky="w", padx=8)
        r += 1
        self.reason = ttk.Entry(self, width=45)
        if not appt:
            ttk.Label(self, text="Reason (optional)").grid(row=r, column=0, sticky="e", padx=8, pady=5)
            self.reason.grid(row=r, column=1, columnspan=2, padx=8)
            r += 1
        button_bar(self, [("Confirm", self.confirm), ("Cancel", self.destroy)]).grid(
            row=r, column=0, columnspan=3, pady=10)

        if appt:
            for name, pid in self.pracs.items():
                if pid == appt["practitioner_id"]:
                    self.prac.set(name)
        self.date.insert(0, f"{appt['appt_date']:%d/%m/%Y}" if appt else f"{date.today():%d/%m/%Y}")

    @guarded
    def find(self):
        if not self.prac.get():
            raise InputError("No practitioner has been selected.", "Pick a practitioner from the list first.")
        d = core.parse_date(self.date.get())
        core.validate_booking_date(d)
        slots = core.free_slots(self.pracs[self.prac.get()], d)
        self.slot["values"] = slots
        self.slot.set("")
        if not slots:
            raise InputError(f"{self.prac.get()} has no open slots on {d:%d/%m/%Y}.",
                             "Try another date, or choose a different practitioner.")

    @guarded
    def confirm(self):
        if not self.prac.get():
            raise InputError("No practitioner has been selected.", "Pick a practitioner from the list.")
        d = core.parse_date(self.date.get())
        t, prac_id = self.slot.get(), self.pracs[self.prac.get()]
        if self.appt:
            core.reschedule_appointment(self.appt["appointment_id"], prac_id, d, t, self.actor, self.owner_id)
        else:
            pid = self.patient_id
            if self.patient is not None:
                if not self.patient.get():
                    raise InputError("No patient has been selected.", "Choose the patient from the list.")
                pid = self.patients[self.patient.get()]
            core.book_appointment(pid, prac_id, d, t, self.reason.get(), self.actor)
        self.on_done()
        self.destroy()
