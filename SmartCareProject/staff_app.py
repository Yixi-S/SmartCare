import csv
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk

from mysql.connector import Error

import core
from core import DAYS, STATUSES, InputError, fmt_dt, fmt_time
from gui_common import (BookingDialog, Form, TableWindow, button_bar, fill, guarded,
                        make_tree, report_error, selected)


# --------------------------------------------------------------------------- #
# Login Page 
# --------------------------------------------------------------------------- #
class LoginFrame(ttk.Frame):
    def __init__(self, parent, on_success):
        super().__init__(parent, padding=24)
        self.on_success = on_success
        ttk.Label(self, text="SmartCare", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2)
        ttk.Label(self, text="Staff log-in", font=("Segoe UI", 11)).grid(row=1, column=0, columnspan=2, pady=(0, 14))
        ttk.Label(self, text="Username").grid(row=2, column=0, sticky="e", padx=6, pady=5)
        self.user = ttk.Entry(self, width=26)
        self.user.grid(row=2, column=1)
        ttk.Label(self, text="Password").grid(row=3, column=0, sticky="e", padx=6, pady=5)
        self.pw = ttk.Entry(self, width=26, show="\u2022")
        self.pw.grid(row=3, column=1)
        self.show = tk.BooleanVar()
        ttk.Checkbutton(self, text="Show password", variable=self.show,
                        command=lambda: self.pw.configure(show="" if self.show.get() else "\u2022")
                        ).grid(row=4, column=1, sticky="w")
        ttk.Button(self, text="Log in", command=self.login).grid(row=5, column=0, columnspan=2, pady=14)
        ttk.Label(self, text="Authorised clinic staff only.", foreground="gray").grid(row=6, column=0, columnspan=2)
        for w in (self.user, self.pw):
            w.bind("<Return>", lambda _: self.login())
        self.user.focus_set()

    def login(self):
        try:
            acct = core.authenticate_staff(self.user.get(), self.pw.get())
        except Exception as e:
            report_error(e, self.winfo_toplevel())
            return
        finally:
            self.pw.delete(0, "end")
        self.on_success(acct)


# --------------------------------------------------------------------------- #
# Patients Page 
# --------------------------------------------------------------------------- #
PATIENT_FIELDS = [("first_name", "First name *"), ("last_name", "Last name *"),
                  ("dob", "Date of birth * (DD/MM/YYYY)"), ("phone", "Phone *"),
                  ("email", "Email"), ("address", "Address"), ("notes", "Notes")]


class PatientsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Search (name / phone / ID):").pack(side="left")
        self.term = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.term, width=30)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _: self.refresh())
        ttk.Button(top, text="Search", command=self.refresh).pack(side="left")
        ttk.Button(top, text="Show all", command=lambda: (self.term.set(""), self.refresh())).pack(side="left", padx=4)
        cols = [("id", "ID", 50), ("first", "First name", 110), ("last", "Last name", 110), ("dob", "DOB", 90),
                ("phone", "Phone", 100), ("email", "Email", 170), ("address", "Address", 200)]
        frame, self.tree = make_tree(self, cols)
        frame.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<Double-1>", lambda _: self.view())
        button_bar(self, [("New patient", self.new), ("View details", self.view), ("Edit", self.edit),
                          ("Appointment history", self.history)]).pack(pady=8)

    @guarded
    def refresh(self):
        rows = core.search_patients(self.term.get())
        fill(self.tree, [(r["patient_id"], (r["patient_id"], r["first_name"], r["last_name"], r["dob"],
                                            r["phone"], r["email"] or "", r["address"] or "")) for r in rows])

    def new(self):
        Form(self, "New patient", PATIENT_FIELDS, {}, lambda d: (core.save_patient(d), self.refresh()))

    @guarded
    def edit(self):
        pid = selected(self.tree)
        rec = core.run("SELECT * FROM patients WHERE patient_id=%s", (pid,))[0]
        rec["dob"] = f"{rec['dob']:%d/%m/%Y}"
        Form(self, f"Edit patient #{pid}", PATIENT_FIELDS, rec,
             lambda d: (core.save_patient(d, pid), self.refresh()))

    @guarded
    def view(self):
        rec = core.run("SELECT * FROM patients WHERE patient_id=%s", (selected(self.tree),))[0]
        messagebox.showinfo("Patient record", "\n".join([
            f"Patient ID:  {rec['patient_id']}", f"Name:  {rec['first_name']} {rec['last_name']}",
            f"Date of birth:  {rec['dob']:%d/%m/%Y}", f"Phone:  {rec['phone']}", f"Email:  {rec['email'] or '-'}",
            f"Address:  {rec['address'] or '-'}", f"Notes:  {rec['notes'] or '-'}",
            f"Registered:  {fmt_dt(rec['created_at'])}", f"Last updated:  {fmt_dt(rec['updated_at'])}"]))

    @guarded
    def history(self):
        pid = selected(self.tree)
        rows = core.list_appointments(patient_id=pid)
        TableWindow(self, f"Appointment history - patient #{pid}",
                    [("d", "Date", 90), ("t", "Time", 60), ("pr", "Practitioner", 160),
                     ("s", "Status", 90), ("r", "Reason", 250)],
                    [(r["appt_date"], fmt_time(r["appt_time"]), r["practitioner"], r["status"],
                      r["reason"] or "") for r in rows])


# --------------------------------------------------------------------------- #
# Practitioners Page 
# --------------------------------------------------------------------------- #
class AvailabilityDialog(tk.Toplevel):
    def __init__(self, parent, prac_id, name):
        super().__init__(parent)
        self.title(f"Availability - {name}")
        self.prac_id = prac_id
        self.geometry("470x430")
        self.grab_set()
        frame, self.tree = make_tree(self, [("day", "Day", 120), ("start", "Start", 80), ("end", "End", 80)])
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        row = ttk.Frame(self)
        row.pack(pady=4)
        self.day = ttk.Combobox(row, values=DAYS, state="readonly", width=12)
        self.day.current(0)
        self.start, self.end = ttk.Entry(row, width=7), ttk.Entry(row, width=7)
        self.start.insert(0, "09:00")
        self.end.insert(0, "17:00")
        for w in (self.day, self.start, self.end):
            w.pack(side="left", padx=3)
        button_bar(self, [("Add window", self.add), ("Remove selected", self.remove)]).pack(pady=6)
        ttk.Label(self, text="Times: HH:MM (e.g. 09:00) or with am/pm. Appointments are 30-minute slots.").pack()
        self.load()

    @guarded
    def load(self):
        rows = core.run("SELECT * FROM practitioner_availability WHERE practitioner_id=%s "
                        "ORDER BY day_of_week, start_time", (self.prac_id,))
        fill(self.tree, [(r["availability_id"], (DAYS[r["day_of_week"]], fmt_time(r["start_time"]),
                                                 fmt_time(r["end_time"]))) for r in rows])

    @guarded
    def add(self):
        core.add_availability(self.prac_id, self.day.current(), self.start.get(), self.end.get())
        self.load()

    @guarded
    def remove(self):
        aid = selected(self.tree)
        core.run("DELETE FROM practitioner_availability WHERE availability_id=%s", (aid,), write=True)
        self.load()


PRAC_FIELDS = [("full_name", "Full name *"), ("specialty", "Specialty"), ("phone", "Phone"), ("email", "Email")]


class PractitionersTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        cols = [("id", "ID", 50), ("name", "Name", 180), ("spec", "Specialty", 140),
                ("phone", "Phone", 110), ("email", "Email", 200), ("active", "Active", 60)]
        frame, self.tree = make_tree(self, cols)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        button_bar(self, [("New practitioner", self.new), ("Edit", self.edit),
                          ("Manage availability", self.availability),
                          ("Activate / Deactivate", self.toggle),
                          ("View open slots", self.slots)]).pack(pady=8)

    @guarded
    def refresh(self):
        rows = core.run("SELECT * FROM practitioners ORDER BY full_name")
        fill(self.tree, [(r["practitioner_id"], (r["practitioner_id"], r["full_name"], r["specialty"],
                                                 r["phone"] or "", r["email"] or "",
                                                 "Yes" if r["active"] else "No")) for r in rows])

    def new(self):
        Form(self, "New practitioner", PRAC_FIELDS, {}, lambda d: (core.save_practitioner(d), self.refresh()))

    @guarded
    def edit(self):
        pid = selected(self.tree)
        rec = core.run("SELECT * FROM practitioners WHERE practitioner_id=%s", (pid,))[0]
        Form(self, "Edit practitioner", PRAC_FIELDS, rec, lambda d: (core.save_practitioner(d, pid), self.refresh()))

    @guarded
    def availability(self):
        pid = selected(self.tree)
        AvailabilityDialog(self, pid, self.tree.item(str(pid), "values")[1])

    @guarded
    def toggle(self):
        pid = selected(self.tree)
        core.run("UPDATE practitioners SET active = 1 - active WHERE practitioner_id=%s", (pid,), write=True)
        self.refresh()

    @guarded
    def slots(self):
        pid = selected(self.tree)
        lines = []
        for i in range(7):
            d = date.today() + timedelta(days=i)
            s = core.free_slots(pid, d)
            if s:
                lines.append(f"{DAYS[d.weekday()][:3]} {d:%d/%m/%Y}:  {', '.join(s)}")
        messagebox.showinfo("Open slots - next 7 days", "\n\n".join(lines) or "No open slots in the next 7 days.")


# --------------------------------------------------------------------------- #
# Appointments Page 
# --------------------------------------------------------------------------- #
class AppointmentsTab(ttk.Frame):
    def __init__(self, parent, actor):
        super().__init__(parent)
        self.actor, self.prac_map = actor, {}
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8, pady=6)
        ttk.Label(f, text="Date:").pack(side="left")
        self.date = ttk.Entry(f, width=12)
        self.date.pack(side="left", padx=4)
        ttk.Label(f, text="Practitioner:").pack(side="left")
        self.prac = ttk.Combobox(f, state="readonly", width=20)
        self.prac.pack(side="left", padx=4)
        ttk.Label(f, text="Status:").pack(side="left")
        self.status = ttk.Combobox(f, values=["All"] + STATUSES, state="readonly", width=11)
        self.status.current(0)
        self.status.pack(side="left", padx=4)
        ttk.Button(f, text="Search", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(f, text="Today", command=self.today).pack(side="left")
        ttk.Button(f, text="Clear", command=self.clear).pack(side="left", padx=3)
        cols = [("id", "ID", 45), ("date", "Date", 90), ("time", "Time", 55), ("patient", "Patient", 160),
                ("prac", "Practitioner", 150), ("status", "Status", 90), ("reason", "Reason", 250)]
        frame, self.tree = make_tree(self, cols)
        frame.pack(fill="both", expand=True, padx=8)
        button_bar(self, [("Book", self.book), ("Reschedule", self.reschedule), ("Cancel appointment", self.cancel),
                          ("Mark Completed", lambda: self.mark("Completed")),
                          ("Mark No-Show", lambda: self.mark("No-Show")),
                          ("Change log", self.log)]).pack(pady=8)

    @guarded
    def refresh(self):
        rows = core.run("SELECT practitioner_id, full_name FROM practitioners ORDER BY full_name")
        self.prac_map = {r["full_name"]: r["practitioner_id"] for r in rows}
        self.prac["values"] = ["All"] + list(self.prac_map)
        if not self.prac.get():
            self.prac.current(0)
        d = core.parse_date(self.date.get(), "Search date") if self.date.get().strip() else None
        status = None if self.status.get() == "All" else self.status.get()
        rows = core.list_appointments(d, self.prac_map.get(self.prac.get()), status)
        fill(self.tree, [(r["appointment_id"], (r["appointment_id"], r["appt_date"], fmt_time(r["appt_time"]),
                                                r["patient"], r["practitioner"], r["status"], r["reason"] or ""))
                         for r in rows])

    def today(self):
        self.date.delete(0, "end")
        self.date.insert(0, f"{date.today():%d/%m/%Y}")
        self.refresh()

    def clear(self):
        self.date.delete(0, "end")
        self.prac.set("All")
        self.status.current(0)
        self.refresh()

    def book(self):
        BookingDialog(self, self.refresh, self.actor)

    @guarded
    def reschedule(self):
        BookingDialog(self, self.refresh, self.actor, appt=core.get_appt(selected(self.tree)))

    @guarded
    def cancel(self):
        aid = selected(self.tree)
        if self.tree.item(str(aid), "values")[5] != "Scheduled":
            raise InputError("Only Scheduled appointments can be cancelled.",
                             "Select an appointment whose Status is 'Scheduled'.")
        win = tk.Toplevel(self)
        win.title("Cancel appointment")
        win.grab_set()
        ttk.Label(win, text="Cancellation reason (optional):").pack(padx=10, pady=(10, 2))
        reason = ttk.Entry(win, width=45)
        reason.pack(padx=10)

        @guarded
        def go():
            core.cancel_appointment(aid, reason.get(), self.actor)
            win.destroy()
            self.refresh()
        button_bar(win, [("Confirm cancellation", go), ("Back", win.destroy)]).pack(pady=10)

    @guarded
    def mark(self, status):
        core.set_status(selected(self.tree), status, self.actor)
        self.refresh()

    @guarded
    def log(self):
        aid = selected(self.tree)
        rows = core.run("SELECT * FROM appointment_history WHERE appointment_id=%s ORDER BY history_id", (aid,))
        TableWindow(self, f"Change log - appointment #{aid}",
                    [("w", "When", 120), ("a", "Action", 85), ("os", "From", 75), ("ns", "To", 75),
                     ("od", "Old date/time", 115), ("nd", "New date/time", 115), ("by", "By", 100),
                     ("n", "Notes", 160)],
                    [(fmt_dt(r["changed_at"]), r["action"], r["old_status"] or "", r["new_status"] or "",
                      fmt_dt(r["old_datetime"]), fmt_dt(r["new_datetime"]), r["changed_by"] or "",
                      r["notes"] or "") for r in rows], 950)


# --------------------------------------------------------------------------- #
# Reports Page 
# --------------------------------------------------------------------------- #
class ReportsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Report:").pack(side="left")
        self.kind = ttk.Combobox(f, values=list(core.REPORTS), state="readonly", width=28)
        self.kind.current(0)
        self.kind.pack(side="left", padx=6)
        ttk.Label(f, text="From:").pack(side="left")
        self.start = ttk.Entry(f, width=11)
        self.start.insert(0, f"{date.today() - timedelta(days=30):%d/%m/%Y}")
        self.start.pack(side="left", padx=4)
        ttk.Label(f, text="To:").pack(side="left")
        self.end = ttk.Entry(f, width=11)
        self.end.insert(0, f"{date.today() + timedelta(days=30):%d/%m/%Y}")
        self.end.pack(side="left", padx=4)
        ttk.Button(f, text="Run report", command=self.run).pack(side="left", padx=6)
        ttk.Button(f, text="Export CSV", command=self.export).pack(side="left")
        self.holder = ttk.Frame(self)
        self.holder.pack(fill="both", expand=True, padx=8, pady=4)
        self.cols, self.rows = [], []

    def refresh(self):
        pass

    @guarded
    def run(self):
        self.cols, self.rows = core.run_report(self.kind.get(), self.start.get(), self.end.get())
        for w in self.holder.winfo_children():
            w.destroy()
        frame, tree = make_tree(self.holder, [(f"c{i}", c, 130) for i, c in enumerate(self.cols)])
        frame.pack(fill="both", expand=True)
        fill(tree, [(None, r) for r in self.rows])
        if not self.rows:
            messagebox.showinfo("Report", "No data for that period. Try widening the date range.")

    @guarded
    def export(self):
        if not self.rows:
            raise InputError("There is nothing to export.", "Press 'Run report' first and make sure it returns rows.")
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=self.kind.get().replace(" ", "_") + ".csv")
        if path:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(self.cols)
                w.writerows(self.rows)
            messagebox.showinfo("Exported", f"Saved to {path}")


# --------------------------------------------------------------------------- #
# Main Window Page 
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartCare - Staff")
        self.show_login()

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    def show_login(self):
        self.clear()
        self.geometry("400x340")
        LoginFrame(self, self.start).pack(expand=True)

    def start(self, acct):
        self.clear()
        self.geometry("1050x640")
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, text=f"Signed in as {acct['full_name']} ({acct['username']})").pack(side="left")
        ttk.Button(bar, text="Log out", command=self.logout).pack(side="right")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        actor = f"Staff: {acct['username']}"
        for label, tab in (("Patients", PatientsTab(nb)), ("Appointments", AppointmentsTab(nb, actor)),
                           ("Practitioners", PractitionersTab(nb)), ("Reports", ReportsTab(nb))):
            nb.add(tab, text=label)
        nb.bind("<<NotebookTabChanged>>", lambda _: nb.nametowidget(nb.select()).refresh())
        self.after(100, lambda: nb.nametowidget(nb.select()).refresh())

    def logout(self):
        if messagebox.askyesno("Log out", "Do you want to log out?"):
            self.show_login()


if __name__ == "__main__":
    try:
        core.connect().close()
    except Error as err:
        root = tk.Tk()
        root.withdraw()
        report_error(err)
        raise SystemExit(1)
    App().mainloop()
