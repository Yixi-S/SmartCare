import time
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from mysql.connector import Error

import core
from core import InputError, fmt_time
from gui_common import BookingDialog, button_bar, fill, guarded, make_tree, report_error, selected


PORTAL_DB = None
if PORTAL_DB:
    core.DB_CONFIG.update(PORTAL_DB)

MAX_TRIES, PAUSE_SECONDS = 5, 60


class LoginFrame(ttk.Frame):
    def __init__(self, parent, on_success):
        super().__init__(parent, padding=24)
        self.on_success, self.fails, self.blocked_until = on_success, 0, 0
        ttk.Label(self, text="SmartCare", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2)
        ttk.Label(self, text="Patient appointments", font=("Segoe UI", 11)).grid(row=1, column=0, columnspan=2)
        ttk.Label(self, text="Please confirm who you are using the details the clinic has on file.",
                  wraplength=330, foreground="gray").grid(row=2, column=0, columnspan=2, pady=(4, 12))
        self.entries = {}
        for i, (key, label) in enumerate([("first", "First name"), ("last", "Last name"),
                                          ("dob", "Date of birth"), ("phone", "Phone number")]):
            ttk.Label(self, text=label).grid(row=3 + i, column=0, sticky="e", padx=6, pady=4)
            e = ttk.Entry(self, width=26)
            e.grid(row=3 + i, column=1)
            e.bind("<Return>", lambda _: self.login())
            self.entries[key] = e
        ttk.Label(self, text=f"Date format: {core.date_hint()}", foreground="gray",
                  wraplength=330).grid(row=7, column=1, sticky="w")
        ttk.Button(self, text="Continue", command=self.login).grid(row=8, column=0, columnspan=2, pady=12)
        self.entries["first"].focus_set()

    def login(self):
        wait = int(self.blocked_until - time.time())
        if wait > 0:
            report_error(InputError("Too many unsuccessful attempts.", f"Please wait {wait} seconds and try again."),
                         self.winfo_toplevel())
            return
        try:
            patient = core.authenticate_patient(*(self.entries[k].get() for k in ("first", "last", "dob", "phone")))
        except InputError as e:
            if "could not find" in e.problem:
                self.fails += 1
                if self.fails >= MAX_TRIES:
                    self.fails, self.blocked_until = 0, time.time() + PAUSE_SECONDS
            report_error(e, self.winfo_toplevel())
            return
        except Exception as e:
            report_error(e, self.winfo_toplevel())
            return
        self.on_success(patient)


class Portal(ttk.Frame):
    def __init__(self, parent, patient, on_logout):
        super().__init__(parent, padding=10)
        self.patient = patient
        self.actor = "Patient portal"
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=f"Hello, {patient['first_name']}", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top, text="Log out", command=on_logout).pack(side="right")
        ttk.Label(self, text="Your upcoming appointments", font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 2))
        frame, self.tree = make_tree(self, [("date", "Date", 95), ("day", "Day", 90), ("time", "Time", 60),
                                            ("prac", "Practitioner", 170), ("reason", "Reason", 200)])
        frame.pack(fill="both", expand=True)
        button_bar(self, [("Book new appointment", self.book), ("Reschedule selected", self.reschedule),
                          ("Cancel selected", self.cancel)]).pack(pady=10)
        ttk.Label(self, text="For anything else, please contact clinic reception.",
                  foreground="gray").pack()
        self.refresh()

    @guarded
    def refresh(self):
        rows = core.list_appointments(patient_id=self.patient["patient_id"], status="Scheduled",
                                      from_date=date.today())
        fill(self.tree, [(r["appointment_id"], (f"{r['appt_date']:%d/%m/%Y}", f"{r['appt_date']:%A}",
                                                fmt_time(r["appt_time"]), r["practitioner"], r["reason"] or ""))
                         for r in rows])

    def book(self):
        BookingDialog(self, self.refresh, self.actor, patient_id=self.patient["patient_id"])

    @guarded
    def reschedule(self):
        pid = self.patient["patient_id"]
        appt = core.get_appt(selected(self.tree), owner_id=pid)
        BookingDialog(self, self.refresh, self.actor, appt=appt, owner_id=pid)

    @guarded
    def cancel(self):
        aid = selected(self.tree)
        vals = self.tree.item(str(aid), "values")
        if messagebox.askyesno("Cancel appointment",
                               f"Cancel your appointment on {vals[0]} at {vals[2]} with {vals[3]}?",
                               parent=self):
            core.cancel_appointment(aid, "Cancelled by patient", self.actor, owner_id=self.patient["patient_id"])
            self.refresh()
            messagebox.showinfo("Cancelled", "Your appointment has been cancelled.", parent=self)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartCare - Patient Appointments")
        self.show_login()

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    def show_login(self):
        self.clear()
        self.geometry("420x420")
        LoginFrame(self, self.start).pack(expand=True)

    def start(self, patient):
        self.clear()
        self.geometry("720x460")
        Portal(self, patient, self.show_login).pack(fill="both", expand=True)


if __name__ == "__main__":
    try:
        core.connect().close()
    except Error as err:
        root = tk.Tk()
        root.withdraw()
        report_error(err)
        raise SystemExit(1)
    App().mainloop()
