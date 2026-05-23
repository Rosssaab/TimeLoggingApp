import os
import time
import tkinter as tk
import json
import ctypes
import html
from datetime import datetime, timedelta
from tkinter import messagebox


STATE_FILE = "timer_state.txt"
WEEKLY_HOURS_TARGET = 37.5
WEEKLY_SECONDS_TARGET = int(WEEKLY_HOURS_TARGET * 3600)


class TimeKeeperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("The Networker Time Logger")
        self.expanded_geometry = "380x300"
        self.running_geometry = "320x150"
        self.root.geometry(self.expanded_geometry)
        self.root.resizable(False, False)

        self.running = False
        self.elapsed_seconds = 0.0
        self.started_at = None
        self.resume_elapsed_base = 0.0
        self.all_time_total_seconds = 0.0
        self.today_total_seconds = 0.0
        self.today_date = datetime.now().strftime("%Y-%m-%d")
        self.session_entries = []
        self.last_description = "General Work"
        self.current_session_description = self.last_description
        self.current_session_started_at_ts = None
        self.sessions_window = None
        self.archived_weeks = []

        self.time_label = tk.Label(
            self.root,
            text="00:00:00",
            font=("Segoe UI", 28, "bold"),
            pady=20,
        )
        self.time_label.pack()

        self.desc_frame = tk.Frame(self.root)
        self.desc_frame.pack(pady=(0, 8))
        tk.Label(self.desc_frame, text="Session Description:", font=("Segoe UI", 10)).grid(row=0, column=0, padx=(0, 6))
        self.session_desc_var = tk.StringVar(value=self.last_description)
        self.session_desc_entry = tk.Entry(self.desc_frame, width=30, textvariable=self.session_desc_var)
        self.session_desc_entry.grid(row=0, column=1)

        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(pady=10)

        self.start_button = tk.Button(
            self.button_frame,
            text="Start",
            width=12,
            command=self.start_timer,
            bg="#2E7D32",
            fg="white",
        )
        self.start_button.grid(row=0, column=0, padx=8)

        self.pause_button = tk.Button(
            self.button_frame,
            text="Pause",
            width=12,
            command=self.pause_timer,
            bg="#C62828",
            fg="white",
        )
        self.pause_button.grid(row=0, column=1, padx=8)

        self.sessions_button = tk.Button(
            self.root,
            text="View Sessions",
            width=26,
            command=self.open_sessions_window,
            bg="#1565C0",
            fg="white",
        )
        self.sessions_button.pack(pady=(0, 8))

        self.new_week_button = tk.Button(
            self.root,
            text="Start New Week",
            width=26,
            command=self.start_new_week,
            bg="#6A1B9A",
            fg="white",
        )

        self.status_label = tk.Label(self.root, text="Paused", font=("Segoe UI", 10))
        self.status_label.pack(pady=(6, 0))

        self.datetime_label = tk.Label(
            self.root,
            text="Current Date/Time: --",
            font=("Segoe UI", 10),
        )
        self.datetime_label.pack(pady=(8, 0))

        self.load_state()
        self.update_buttons()
        self.update_clock()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def save_state(self) -> None:
        # Store state as key=value lines in a plain text file.
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(f"running={self.running}\n")
            f.write(f"elapsed_seconds={self.elapsed_seconds}\n")
            f.write(f"started_at={self.started_at if self.started_at is not None else ''}\n")
            f.write(f"all_time_total_seconds={self.all_time_total_seconds}\n")
            f.write(f"today_total_seconds={self.today_total_seconds}\n")
            f.write(f"today_date={self.today_date}\n")
            f.write(f"last_description={self.last_description}\n")
            f.write(f"session_entries_json={json.dumps(self.session_entries)}\n")
            f.write(f"archived_weeks_json={json.dumps(self.archived_weeks)}\n")

    def load_state(self) -> None:
        if not os.path.exists(STATE_FILE):
            return

        data = {}
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key] = value

        self.running = data.get("running", "False") == "True"
        self.elapsed_seconds = float(data.get("elapsed_seconds", "0") or "0")
        started_at_value = data.get("started_at", "")
        self.started_at = float(started_at_value) if started_at_value else None
        self.all_time_total_seconds = float(data.get("all_time_total_seconds", "0") or "0")
        self.today_total_seconds = float(data.get("today_total_seconds", "0") or "0")
        self.today_date = data.get("today_date", datetime.now().strftime("%Y-%m-%d"))
        self.last_description = data.get("last_description", self.last_description) or self.last_description
        self.current_session_description = self.last_description

        raw_json_entries = data.get("session_entries_json", "")
        if raw_json_entries:
            try:
                loaded_entries = json.loads(raw_json_entries)
                self.session_entries = []
                for entry in loaded_entries:
                    clean_entry = self.normalize_session_entry(entry)
                    if clean_entry:
                        self.session_entries.append(clean_entry)
            except (ValueError, TypeError):
                self.session_entries = self.parse_session_entries(data.get("session_entries", ""))
        else:
            self.session_entries = self.parse_session_entries(data.get("session_entries", ""))
        self.normalize_all_entries()
        self.load_archived_weeks(data.get("archived_weeks_json", ""))

        # If the timer was left running (e.g. PC shutdown), stop it and do not count downtime.
        if self.running:
            self.running = False
            self.started_at = None
            self.current_session_started_at_ts = None
            self.resume_elapsed_base = float(self.elapsed_seconds)
            self.save_state()

        current_date = datetime.now().strftime("%Y-%m-%d")
        if self.today_date != current_date:
            self.today_date = current_date
            self.today_total_seconds = 0.0
        self.recalculate_totals()
        self.session_desc_var.set(self.last_description)

    def parse_session_entries(self, raw_entries: str) -> list:
        entries = []
        if not raw_entries:
            return entries

        for part in raw_entries.split(";"):
            part = part.strip()
            if not part or "," not in part:
                continue
            date_text, seconds_text = part.split(",", 1)
            try:
                seconds = max(0, int(float(seconds_text)))
            except ValueError:
                continue
            if date_text:
                entries.append({"date": date_text, "seconds": seconds, "description": "No Description"})
        return entries

    def normalize_session_entry(self, entry: dict) -> dict | None:
        date_text = str(entry.get("date", "")).strip()
        description = str(entry.get("description", "")).strip() or "No Description"
        try:
            seconds = max(0, int(float(entry.get("seconds", 0) or 0)))
        except (ValueError, TypeError):
            seconds = 0
        if not date_text:
            return None

        start_text = str(entry.get("start", "")).strip()
        end_text = str(entry.get("end", "")).strip()
        if start_text and end_text:
            try:
                start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
                if end_dt > start_dt:
                    seconds = int((end_dt - start_dt).total_seconds())
                else:
                    start_text = ""
                    end_text = ""
            except ValueError:
                start_text = ""
                end_text = ""

        if not start_text or not end_text:
            start_text = f"{date_text} 09:00:00"
            end_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=seconds)
            end_text = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "date": date_text,
            "seconds": seconds,
            "description": description,
            "start": start_text,
            "end": end_text,
        }

    def normalize_all_entries(self) -> None:
        normalized = []
        for entry in self.session_entries:
            clean_entry = self.normalize_session_entry(entry)
            if clean_entry:
                normalized.append(clean_entry)
        self.session_entries = normalized

    def load_archived_weeks(self, raw_archived_weeks: str) -> None:
        self.archived_weeks = []
        if not raw_archived_weeks:
            return
        try:
            loaded_weeks = json.loads(raw_archived_weeks)
        except (ValueError, TypeError):
            return

        if not isinstance(loaded_weeks, list):
            return

        for week in loaded_weeks:
            if not isinstance(week, dict):
                continue
            week_id = str(week.get("week_id", "")).strip()
            closed_at = str(week.get("closed_at", "")).strip()
            try:
                total_seconds = max(0, int(float(week.get("total_seconds", 0) or 0)))
            except (ValueError, TypeError):
                total_seconds = 0

            normalized_entries = []
            for entry in week.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                clean_entry = self.normalize_session_entry(entry)
                if clean_entry:
                    normalized_entries.append(clean_entry)

            if not normalized_entries:
                continue

            self.archived_weeks.append(
                {
                    "week_id": week_id or normalized_entries[0]["date"],
                    "closed_at": closed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_seconds": total_seconds or sum(e.get("seconds", 0) for e in normalized_entries),
                    "entries": normalized_entries,
                }
            )

    def recalculate_totals(self) -> None:
        self.today_date = datetime.now().strftime("%Y-%m-%d")
        self.all_time_total_seconds = sum(entry.get("seconds", 0) for entry in self.session_entries)
        self.today_total_seconds = sum(
            entry.get("seconds", 0) for entry in self.session_entries if entry.get("date") == self.today_date
        )

    def sync_main_timer_from_sessions(self) -> None:
        self.recalculate_totals()
        if self.running:
            self.resume_elapsed_base = float(self.all_time_total_seconds)
        else:
            self.elapsed_seconds = float(self.all_time_total_seconds)
        self.update_buttons()

    def seed_test_sessions_if_empty(self) -> None:
        if self.session_entries:
            return

        now = datetime.now()
        for days_back in range(1, 6):
            sample_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
            self.session_entries.append(
                {"date": sample_date, "seconds": 4 * 60 * 60, "description": "Sample 4-hour session"}
            )

        self.normalize_all_entries()
        self.recalculate_totals()
        self.save_state()

    def append_completed_session(self, seconds: float) -> None:
        session_seconds = max(0, int(seconds))
        if session_seconds <= 0:
            return
        description = (self.current_session_description or self.last_description or "No Description").strip()
        end_ts = time.time()
        start_ts = self.current_session_started_at_ts if self.current_session_started_at_ts is not None else end_ts - session_seconds
        self.session_entries.append(
            {
                "date": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
                "seconds": session_seconds,
                "description": description,
                "start": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"),
                "end": datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    def build_invoice_text(self) -> str:
        rows, total_amount, hourly_rate = self.build_invoice_rows()
        lines = []
        for desc_cell, hours_logged, amount in rows:
            lines.append(f"{desc_cell}\t{hours_logged:.2f}\t£{hourly_rate:.2f}\t£{amount:.2f}")
        lines.append(f"\t\tTOTAL\t£{total_amount:.2f}")
        return "\n".join(lines)

    def build_invoice_rows(self) -> tuple[list[tuple[str, float, float]], float, float]:
        hourly_rate = 6.25
        grouped_seconds: dict[tuple[str, str], int] = {}

        for entry in self.session_entries:
            date_text = entry.get("date", "")
            description = entry.get("description", "No Description")
            key = (date_text, description)
            grouped_seconds[key] = grouped_seconds.get(key, 0) + int(entry.get("seconds", 0))

        running_segment = int(self.running_segment_seconds())
        if self.running and running_segment > 0 and self.current_session_started_at_ts is not None:
            start_dt = datetime.fromtimestamp(self.current_session_started_at_ts)
            running_date = start_dt.strftime("%Y-%m-%d")
            running_desc = self.current_session_description or self.last_description or "No Description"
            running_key = (running_date, running_desc)
            grouped_seconds[running_key] = grouped_seconds.get(running_key, 0) + running_segment

        rows: list[tuple[str, float, float]] = []
        total_amount = 0.0
        for (date_text, description), seconds in sorted(grouped_seconds.items()):
            hours_logged = seconds / 3600
            amount = hours_logged * hourly_rate
            total_amount += amount
            try:
                formatted_date = datetime.strptime(date_text, "%Y-%m-%d").strftime("%d-%m-%Y")
            except ValueError:
                formatted_date = date_text
            desc_cell = f"{description} ({formatted_date})"
            rows.append((desc_cell, hours_logged, amount))

        return rows, total_amount, hourly_rate

    def build_invoice_html(self) -> str:
        rows, total_amount, hourly_rate = self.build_invoice_rows()
        body_rows = []
        for desc_cell, hours_logged, amount in rows:
            body_rows.append(
                "<tr>"
                f"<td>{html.escape(desc_cell)}</td>"
                f"<td>{hours_logged:.2f}</td>"
                f"<td>&pound;{hourly_rate:.2f}</td>"
                f"<td>&pound;{amount:.2f}</td>"
                "</tr>"
            )

        body_rows.append(
            "<tr>"
            "<td></td>"
            "<td></td>"
            "<td><strong>TOTAL</strong></td>"
            f"<td><strong>&pound;{total_amount:.2f}</strong></td>"
            "</tr>"
        )

        return (
            "<table style='width:100%; border-collapse:collapse; table-layout:fixed;'>"
            "<thead>"
            "<tr>"
            "<th style='border:1px solid #000; padding:6px;'>DESCRIPTION</th>"
            "<th style='border:1px solid #000; padding:6px; width:14%;'>HOURS</th>"
            "<th style='border:1px solid #000; padding:6px; width:14%;'>RATE</th>"
            "<th style='border:1px solid #000; padding:6px; width:14%;'>AMOUNT</th>"
            "</tr>"
            "</thead>"
            "<tbody>"
            + "".join(row.replace("<td>", "<td style='border:1px solid #000; padding:6px;'>") for row in body_rows)
            + "</tbody></table>"
        )

    def copy_invoice_html_to_clipboard(self, html_content: str, plain_text: str) -> bool:
        if os.name != "nt":
            return False

        prefix_template = (
            "Version:0.9\r\n"
            "StartHTML:{start_html:010d}\r\n"
            "EndHTML:{end_html:010d}\r\n"
            "StartFragment:{start_fragment:010d}\r\n"
            "EndFragment:{end_fragment:010d}\r\n"
        )
        fragment_start_tag = "<!--StartFragment-->"
        fragment_end_tag = "<!--EndFragment-->"
        wrapped_html = (
            "<html><body>"
            f"{fragment_start_tag}{html_content}{fragment_end_tag}"
            "</body></html>"
        )
        wrapped_bytes = wrapped_html.encode("utf-8")
        prefix = prefix_template.format(start_html=0, end_html=0, start_fragment=0, end_fragment=0)
        start_html = len(prefix.encode("utf-8"))
        start_fragment = start_html + wrapped_bytes.index(fragment_start_tag.encode("utf-8")) + len(
            fragment_start_tag.encode("utf-8")
        )
        end_fragment = start_html + wrapped_bytes.index(fragment_end_tag.encode("utf-8"))
        end_html = start_html + len(wrapped_bytes)
        final_prefix = prefix_template.format(
            start_html=start_html,
            end_html=end_html,
            start_fragment=start_fragment,
            end_fragment=end_fragment,
        )
        cf_html_payload = final_prefix.encode("utf-8") + wrapped_bytes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        GHND = GMEM_MOVEABLE

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cf_html = user32.RegisterClipboardFormatW("HTML Format")
        if cf_html == 0:
            return False

        def allocate_global(data: bytes) -> int:
            handle = kernel32.GlobalAlloc(GHND, len(data))
            if not handle:
                return 0
            locked = kernel32.GlobalLock(handle)
            if not locked:
                kernel32.GlobalFree(handle)
                return 0
            ctypes.memmove(locked, data, len(data))
            kernel32.GlobalUnlock(handle)
            return handle

        text_data = plain_text.encode("utf-16-le") + b"\x00\x00"
        html_handle = allocate_global(cf_html_payload)
        text_handle = allocate_global(text_data)
        if not html_handle or not text_handle:
            if html_handle:
                kernel32.GlobalFree(html_handle)
            if text_handle:
                kernel32.GlobalFree(text_handle)
            return False

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(html_handle)
            kernel32.GlobalFree(text_handle)
            return False

        user32.EmptyClipboard()
        user32.SetClipboardData(cf_html, html_handle)
        user32.SetClipboardData(CF_UNICODETEXT, text_handle)
        user32.CloseClipboard()
        return True

    def open_sessions_window(self) -> None:
        if self.sessions_window and self.sessions_window.winfo_exists():
            self.sessions_window.lift()
            self.sessions_window.focus_force()
            return

        sessions_window = tk.Toplevel(self.root)
        self.sessions_window = sessions_window
        sessions_window.title("Session Log")
        sessions_window.geometry("720x470")
        sessions_window.resizable(False, False)
        sessions_window.transient(self.root)
        sessions_window.grab_set()
        try:
            self.root.attributes("-disabled", True)
        except tk.TclError:
            pass

        def on_sessions_close() -> None:
            try:
                self.root.attributes("-disabled", False)
            except tk.TclError:
                pass
            self.sessions_window = None
            sessions_window.destroy()

        sessions_window.protocol("WM_DELETE_WINDOW", on_sessions_close)

        title = tk.Label(sessions_window, text="Session History", font=("Segoe UI", 12, "bold"))
        title.pack(pady=(10, 6))

        view_mode = tk.StringVar(value="current")
        mode_row = tk.Frame(sessions_window)
        mode_row.pack(pady=(0, 6))
        tk.Button(
            mode_row,
            text="Current Week",
            width=16,
            command=lambda: set_view_mode("current"),
            bg="#1565C0",
            fg="white",
        ).grid(row=0, column=0, padx=4)
        tk.Button(
            mode_row,
            text="Archived Weeks",
            width=16,
            command=lambda: set_view_mode("archived"),
            bg="#6A1B9A",
            fg="white",
        ).grid(row=0, column=1, padx=4)

        sessions_list = tk.Listbox(
            sessions_window,
            width=92,
            height=9,
            font=("Consolas", 10),
            selectmode=tk.SINGLE,
            activestyle="dotbox",
        )
        sessions_list.pack(padx=12, pady=(4, 4))

        footer = tk.Label(
            sessions_window,
            text="Total Logged Time: 00:00:00",
            font=("Segoe UI", 10, "bold"),
        )
        footer.pack(pady=(4, 4))

        adjust_frame = tk.Frame(sessions_window)
        adjust_frame.pack(fill="x", padx=12, pady=(0, 4))

        adjust_label = tk.Label(
            adjust_frame,
            text="Select a session, then slide to adjust the end time (left = shorter, right = longer).",
            font=("Segoe UI", 9),
            anchor="w",
        )
        adjust_label.pack(fill="x")

        end_slider = tk.Scale(
            adjust_frame,
            from_=0,
            to=1,
            orient=tk.HORIZONTAL,
            length=680,
            resolution=60,
            showvalue=0,
            state="disabled",
        )
        end_slider.pack(fill="x", pady=(2, 0))

        end_preview = tk.Label(adjust_frame, text="", font=("Segoe UI", 9), anchor="w")
        end_preview.pack(fill="x", pady=(2, 0))

        slider_context: dict = {"index": None, "start_ts": None, "original_end_ts": None}
        slider_updating = {"active": False}

        def session_line_text(index: int, entry: dict) -> str:
            duration = self.format_time(entry.get("seconds", 0))
            return (
                f"{index:02}. {entry['start']} -> {entry['end']}  ({duration})  |  "
                f"{entry.get('description', 'No Description')}"
            )

        def reset_end_slider() -> None:
            slider_context["index"] = None
            slider_context["start_ts"] = None
            slider_context["original_end_ts"] = None
            end_slider.config(state="disabled")
            end_preview.config(text="")
            revert_end_button.config(state="disabled")

        def update_week_total_footer() -> None:
            running_segment = self.running_segment_seconds()
            total_seconds = self.all_time_total_seconds + running_segment
            footer.config(text=f"Current Week Total: {self.format_time(total_seconds)}")

        def update_end_slider_preview(end_ts: float) -> None:
            start_ts = slider_context.get("start_ts")
            original_end_ts = slider_context.get("original_end_ts")
            if start_ts is None or original_end_ts is None:
                return
            duration = max(0, int(end_ts - start_ts))
            delta = int(end_ts - original_end_ts)
            end_text = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S")
            preview = f"End: {end_text}  |  Duration: {self.format_time(duration)}"
            if delta < 0:
                preview += f"  |  Reduced by: {self.format_time(-delta)}"
            elif delta > 0:
                preview += f"  |  Increased by: {self.format_time(delta)}"
            end_preview.config(text=preview)

        def commit_slider_end_time(end_ts: float, *, save: bool = False) -> None:
            selected_index = slider_context.get("index")
            start_ts = slider_context.get("start_ts")
            if selected_index is None or start_ts is None:
                return
            if end_ts <= start_ts:
                return

            entry = self.session_entries[selected_index]
            start_dt = datetime.fromtimestamp(start_ts)
            new_end_dt = datetime.fromtimestamp(end_ts)
            entry["end"] = new_end_dt.strftime("%Y-%m-%d %H:%M:%S")
            entry["date"] = start_dt.strftime("%Y-%m-%d")
            entry["seconds"] = int(end_ts - start_ts)
            self.sync_main_timer_from_sessions()

            slider_updating["active"] = True
            try:
                if selected_index < sessions_list.size():
                    sessions_list.delete(selected_index)
                    sessions_list.insert(selected_index, session_line_text(selected_index + 1, entry))
                    sessions_list.selection_set(selected_index)
                    sessions_list.see(selected_index)
            finally:
                slider_updating["active"] = False

            update_week_total_footer()
            update_end_slider_preview(end_ts)
            if save:
                self.save_state()

        def on_end_slider_change(value: str) -> None:
            if slider_context["index"] is None:
                return
            commit_slider_end_time(float(value), save=False)

        def on_end_slider_release(_event: tk.Event) -> None:
            if slider_context["index"] is None:
                return
            commit_slider_end_time(float(end_slider.get()), save=True)

        def load_end_slider_for_selection() -> None:
            if slider_updating["active"]:
                return
            if view_mode.get() != "current":
                reset_end_slider()
                return
            selection = sessions_list.curselection()
            if not selection or selection[0] >= len(self.session_entries):
                reset_end_slider()
                return

            selected_index = selection[0]
            entry = self.session_entries[selected_index]
            try:
                start_dt = datetime.strptime(entry["start"], "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(entry["end"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                reset_end_slider()
                return
            if end_dt <= start_dt:
                reset_end_slider()
                return

            start_ts = start_dt.timestamp()
            end_ts = end_dt.timestamp()
            min_end_ts = start_ts + 60
            max_end_ts = max(end_ts, datetime.now().timestamp())

            slider_context["index"] = selected_index
            slider_context["start_ts"] = start_ts
            slider_context["original_end_ts"] = end_ts
            end_slider.config(from_=min_end_ts, to=max_end_ts, state="normal")
            end_slider.set(end_ts)
            revert_end_button.config(state="normal")
            update_end_slider_preview(end_ts)

        def revert_end_time() -> None:
            original_end_ts = slider_context.get("original_end_ts")
            if original_end_ts is None:
                return
            end_slider.set(original_end_ts)
            commit_slider_end_time(original_end_ts, save=True)

        end_slider.config(command=on_end_slider_change)
        end_slider.bind("<ButtonRelease-1>", on_end_slider_release)

        def refresh_sessions_list() -> None:
            sessions_list.delete(0, tk.END)
            if view_mode.get() == "current":
                for index, entry in enumerate(self.session_entries, start=1):
                    sessions_list.insert(tk.END, session_line_text(index, entry))

                running_segment = self.running_segment_seconds()
                if running_segment > 0:
                    sessions_list.insert(
                        tk.END,
                        f"-- {datetime.now().strftime('%Y-%m-%d')}   Current Running: {self.format_time(running_segment)}",
                    )

                total_seconds = self.all_time_total_seconds + running_segment
                footer.config(text=f"Current Week Total: {self.format_time(total_seconds)}")
                delete_button.config(state="normal")
                copy_button.config(state="normal")
                revert_end_button.config(state="disabled" if slider_context["index"] is None else "normal")
                if slider_context["index"] is not None:
                    update_week_total_footer()
            else:
                if not self.archived_weeks:
                    sessions_list.insert(tk.END, "-- No archived weeks yet --")
                for week_index, week in enumerate(self.archived_weeks, start=1):
                    week_total = int(week.get("total_seconds", 0))
                    week_id = week.get("week_id", "Unknown")
                    closed_at = week.get("closed_at", "Unknown")
                    sessions_list.insert(
                        tk.END,
                        f"Week {week_index:02} | Start: {week_id} | Closed: {closed_at} | Total: {self.format_time(week_total)}",
                    )
                    for entry in week.get("entries", []):
                        duration = self.format_time(entry.get("seconds", 0))
                        sessions_list.insert(
                            tk.END,
                            f"   - {entry['start']} -> {entry['end']}  ({duration})  |  "
                            f"{entry.get('description', 'No Description')}",
                        )
                    sessions_list.insert(tk.END, "")

                archived_total = sum(int(week.get("total_seconds", 0)) for week in self.archived_weeks)
                footer.config(text=f"Archived Total: {self.format_time(archived_total)}")
                delete_button.config(state="disabled")
                copy_button.config(state="disabled")
                reset_end_slider()

        def set_view_mode(mode: str) -> None:
            if mode not in ("current", "archived"):
                return
            view_mode.set(mode)
            reset_end_slider()
            refresh_sessions_list()

        def delete_selected_session() -> None:
            selection = sessions_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a session to delete.")
                return

            selected_index = selection[0]
            if selected_index >= len(self.session_entries):
                messagebox.showinfo(
                    "Cannot Delete",
                    "Current running line cannot be deleted. Select a saved session.",
                )
                return

            confirm = messagebox.askyesno("Delete Session", "Delete selected session?", parent=sessions_window)
            if not confirm:
                return
            self.session_entries.pop(selected_index)
            self.sync_main_timer_from_sessions()
            self.save_state()
            reset_end_slider()
            refresh_sessions_list()

        def copy_sessions_for_invoice() -> None:
            invoice_text = self.build_invoice_text()
            invoice_html = self.build_invoice_html()
            copied_html = self.copy_invoice_html_to_clipboard(invoice_html, invoice_text)
            if not copied_html:
                self.root.clipboard_clear()
                self.root.clipboard_append(invoice_text)
                self.root.update()
            messagebox.showinfo(
                "Copied",
                (
                    "Invoice table copied with formatting."
                    if copied_html
                    else "Invoice rows copied as text (HTML clipboard unavailable)."
                ),
                parent=sessions_window,
            )

        def edit_session_at_index(selected_index: int) -> None:
            if selected_index < 0 or selected_index >= len(self.session_entries):
                return
            entry = self.session_entries[selected_index]

            editor = tk.Toplevel(sessions_window)
            editor.title("Edit Session")
            editor.geometry("460x230")
            editor.resizable(False, False)
            editor.transient(sessions_window)
            editor.grab_set()

            tk.Label(editor, text="Start Time (YYYY-MM-DD HH:MM:SS)").pack(pady=(10, 2))
            start_var = tk.StringVar(value=entry.get("start", ""))
            tk.Entry(editor, textvariable=start_var, width=42).pack()

            tk.Label(editor, text="End Time (YYYY-MM-DD HH:MM:SS)").pack(pady=(10, 2))
            end_var = tk.StringVar(value=entry.get("end", ""))
            tk.Entry(editor, textvariable=end_var, width=42).pack()

            tk.Label(editor, text="Description").pack(pady=(10, 2))
            desc_var = tk.StringVar(value=entry.get("description", "No Description"))
            tk.Entry(editor, textvariable=desc_var, width=42).pack()

            button_row = tk.Frame(editor)
            button_row.pack(pady=14)

            def save_edit() -> None:
                start_text = start_var.get().strip()
                end_text = end_var.get().strip()
                description = desc_var.get().strip() or "No Description"
                try:
                    start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    messagebox.showerror("Invalid Date/Time", "Use format: YYYY-MM-DD HH:MM:SS", parent=editor)
                    return
                if end_dt <= start_dt:
                    messagebox.showerror("Invalid Range", "End time must be after start time.", parent=editor)
                    return

                entry["start"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                entry["end"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                entry["date"] = start_dt.strftime("%Y-%m-%d")
                entry["seconds"] = int((end_dt - start_dt).total_seconds())
                entry["description"] = description
                self.sync_main_timer_from_sessions()
                self.save_state()
                refresh_sessions_list()
                editor.destroy()

            def delete_from_editor() -> None:
                confirm = messagebox.askyesno("Delete Session", "Delete this session?", parent=editor)
                if not confirm:
                    return
                self.session_entries.pop(selected_index)
                self.sync_main_timer_from_sessions()
                self.save_state()
                refresh_sessions_list()
                editor.destroy()

            tk.Button(button_row, text="Save", width=10, command=save_edit, bg="#2E7D32", fg="white").grid(
                row=0, column=0, padx=6
            )
            tk.Button(button_row, text="Delete", width=10, command=delete_from_editor, bg="#8E0000", fg="white").grid(
                row=0, column=1, padx=6
            )
            tk.Button(button_row, text="Cancel", width=10, command=editor.destroy).grid(row=0, column=2, padx=6)

        def on_double_click(_event: tk.Event) -> None:
            if view_mode.get() != "current":
                return
            selection = sessions_list.curselection()
            if not selection:
                return
            selected_index = selection[0]
            if selected_index >= len(self.session_entries):
                return
            edit_session_at_index(selected_index)

        button_row = tk.Frame(sessions_window)
        button_row.pack(pady=(4, 10))

        delete_button = tk.Button(
            button_row,
            text="Delete Session",
            width=20,
            command=delete_selected_session,
            bg="#8E0000",
            fg="white",
        )
        delete_button.grid(row=0, column=0, padx=4)

        revert_end_button = tk.Button(
            button_row,
            text="Revert End Time",
            width=20,
            command=revert_end_time,
            bg="#E65100",
            fg="white",
            state="disabled",
        )
        revert_end_button.grid(row=0, column=1, padx=4)

        copy_button = tk.Button(
            button_row,
            text="Copy for Invoice",
            width=20,
            command=copy_sessions_for_invoice,
            bg="#2E7D32",
            fg="white",
        )
        copy_button.grid(row=0, column=2, padx=4)

        sessions_list.bind("<Delete>", lambda _event: delete_selected_session())
        sessions_list.bind("<Double-Button-1>", on_double_click)
        sessions_list.bind("<<ListboxSelect>>", lambda _event: load_end_slider_for_selection())
        refresh_sessions_list()

    def running_segment_seconds(self) -> float:
        if self.running:
            return max(0.0, self.current_elapsed() - self.resume_elapsed_base)
        return 0.0

    def format_time(self, total_seconds: float) -> str:
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def current_elapsed(self) -> float:
        if self.running and self.started_at is not None:
            return time.time() - self.started_at
        return self.elapsed_seconds

    def start_timer(self) -> None:
        if self.running:
            return

        entered_description = self.session_desc_var.get().strip()
        if entered_description:
            self.current_session_description = entered_description
        else:
            self.current_session_description = self.last_description
        self.last_description = self.current_session_description
        self.session_desc_var.set(self.last_description)

        self.running = True
        # Resume from the paused elapsed value.
        self.resume_elapsed_base = self.elapsed_seconds
        self.current_session_started_at_ts = time.time()
        self.started_at = self.current_session_started_at_ts - self.elapsed_seconds
        self.status_label.config(text="Running")
        self.update_buttons()
        self.save_state()

    def pause_timer(self) -> None:
        if not self.running:
            return

        segment_seconds = self.running_segment_seconds()
        self.elapsed_seconds = self.current_elapsed()
        self.all_time_total_seconds += segment_seconds
        self.today_total_seconds += segment_seconds
        self.append_completed_session(segment_seconds)
        self.recalculate_totals()
        self.running = False
        self.started_at = None
        self.current_session_started_at_ts = None
        self.status_label.config(text="Paused")
        self.update_buttons()
        self.save_state()

    def update_buttons(self) -> None:
        self.start_button.config(state=("disabled" if self.running else "normal"))
        self.pause_button.config(state=("normal" if self.running else "disabled"))
        self.update_layout_for_state()

    def should_show_new_week_button(self) -> bool:
        current_total = int(self.current_elapsed())
        return (not self.running) and bool(self.session_entries) and current_total >= WEEKLY_SECONDS_TARGET

    def start_new_week(self) -> None:
        if self.running:
            messagebox.showinfo("Timer Running", "Pause the timer before starting a new week.")
            return
        if not self.session_entries:
            messagebox.showinfo("No Sessions", "There are no sessions to archive for the previous week.")
            return

        confirm = messagebox.askyesno(
            "Start New Week",
            "Archive the current week and reset the timer for a new week?",
            parent=self.root,
        )
        if not confirm:
            return

        total_seconds = sum(entry.get("seconds", 0) for entry in self.session_entries)
        week_id = self.session_entries[0].get("date", datetime.now().strftime("%Y-%m-%d"))
        self.archived_weeks.append(
            {
                "week_id": week_id,
                "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_seconds": total_seconds,
                "entries": list(self.session_entries),
            }
        )

        self.session_entries = []
        self.elapsed_seconds = 0.0
        self.started_at = None
        self.resume_elapsed_base = 0.0
        self.all_time_total_seconds = 0.0
        self.today_total_seconds = 0.0
        self.today_date = datetime.now().strftime("%Y-%m-%d")
        self.current_session_started_at_ts = None
        self.recalculate_totals()
        self.update_buttons()
        self.save_state()
        messagebox.showinfo("New Week Started", "Previous week saved. Timer reset for a new week.", parent=self.root)

    def show_widget(self, widget: tk.Widget, pack_options: dict) -> None:
        if not widget.winfo_manager():
            widget.pack(**pack_options)

    def update_layout_for_state(self) -> None:
        if self.running:
            self.root.geometry(self.running_geometry)
            if self.desc_frame.winfo_manager():
                self.desc_frame.pack_forget()
            if self.sessions_button.winfo_manager():
                self.sessions_button.pack_forget()
            if self.new_week_button.winfo_manager():
                self.new_week_button.pack_forget()
            if self.status_label.winfo_manager():
                self.status_label.pack_forget()
            if self.datetime_label.winfo_manager():
                self.datetime_label.pack_forget()

            self.start_button.grid_remove()
            self.pause_button.grid_configure(column=0, padx=0)
            if not self.button_frame.winfo_manager():
                self.button_frame.pack(pady=(0, 8))
        else:
            self.root.geometry(self.expanded_geometry)
            self.show_widget(self.desc_frame, {"pady": (0, 8)})
            self.show_widget(self.button_frame, {"pady": 10})
            self.show_widget(self.sessions_button, {"pady": (0, 8)})
            if self.should_show_new_week_button():
                self.show_widget(self.new_week_button, {"pady": (0, 8)})
            elif self.new_week_button.winfo_manager():
                self.new_week_button.pack_forget()
            self.show_widget(self.status_label, {"pady": (6, 0)})
            self.show_widget(self.datetime_label, {"pady": (8, 0)})

            self.start_button.grid()
            self.pause_button.grid_configure(column=1, padx=8)

    def update_clock(self) -> None:
        elapsed = self.current_elapsed()
        self.time_label.config(text=self.format_time(elapsed))
        self.datetime_label.config(
            text=f"Current Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.root.after(200, self.update_clock)

    def on_close(self) -> None:
        if self.running:
            self.running = False
            self.started_at = None
            self.current_session_started_at_ts = None
            self.elapsed_seconds = self.resume_elapsed_base
        self.save_state()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = TimeKeeperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
