"""Web Scraper desktop interface. Start with: python main.py"""

# import sys

# # Keep this project limited to its four source files.
# sys.dont_write_bytecode = True

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk

from exporter import COLUMNS, export_csv, export_excel
from scraper import ScrapeError, scrape_website


GREEN = "#166534"
BRIGHT_GREEN = "#22C55E"
LIGHT_GREEN = "#F0FDF4"
WHITE = "#FFFFFF"
TEXT = "#1F2937"
SECONDARY = "#6B7280"
RED = "#DC2626"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")


class WebScraperApp(ctk.CTk):
    """One small class keeps the GUI state and widgets together."""

    def __init__(self):
        super().__init__()
        self.title("Web Scraper")
        self.geometry("1180x790")
        self.minsize(860, 660)
        self.configure(fg_color=LIGHT_GREEN)

        self.records = []
        self.busy = False
        self.messages = queue.Queue()
        self.input_widgets = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.build_header()
        self.build_setup()
        self.build_buttons()
        self.build_results()
        self.build_status()

        self.set_busy(False)
        self.poll_id = self.after(100, self.poll_messages)
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.bind("<Configure>", self.resize_status)

    def build_header(self):
        header = ctk.CTkFrame(self, fg_color=GREEN, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text="Web Scraper",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=WHITE,
        ).pack(anchor="w", padx=28, pady=(19, 2))
        ctk.CTkLabel(
            header,
            text="Turn public web pages into clean, ready-to-use data.",
            text_color="#DCFCE7",
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=28, pady=(0, 18))

    def build_setup(self):
        setup = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=12)
        setup.grid(row=1, column=0, sticky="ew", padx=24, pady=(18, 12))
        setup.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            setup, text="Website URL", text_color=TEXT,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, padx=(18, 12), pady=(18, 12), sticky="w")

        self.url_entry = ctk.CTkEntry(
            setup, placeholder_text="https://example.com",
            height=38, border_color="#D1D5DB",
        )
        self.url_entry.grid(
            row=0, column=1, sticky="ew", padx=(0, 12), pady=(18, 12)
        )
        self.url_entry.insert(0, "https://books.toscrape.com/")

        self.practice_button = ctk.CTkButton(
            setup, text="Use practice URL", width=140,
            fg_color=LIGHT_GREEN, text_color=GREEN,
            hover_color="#DCFCE7", command=self.load_practice,
        )
        self.practice_button.grid(
            row=0, column=2, padx=(0, 18), pady=(18, 12)
        )

        ctk.CTkLabel(
            setup, text="Scraping mode", text_color=TEXT,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=1, column=0, padx=(18, 12), sticky="w")

        mode_row = ctk.CTkFrame(setup, fg_color="transparent")
        mode_row.grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 18)
        )
        self.mode_menu = ctk.CTkOptionMenu(
            mode_row,
            values=["Product Prices", "News Headlines", "Custom Data"],
            width=190, height=35,
            fg_color=GREEN, button_color=GREEN,
            button_hover_color="#14532D",
        )
        self.mode_menu.pack(side="left")
        ctk.CTkLabel(
            mode_row, text="One public page per scrape. Static HTML only.",
            text_color=SECONDARY, font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=14)

        selector_frame = ctk.CTkFrame(setup, fg_color="transparent")
        selector_frame.grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(18, 5)
        )
        selectors = [
            ("Item / container selector", "article.product_pod"),
            ("Text selector (relative)", "h3 a"),
            ("Price / value (relative)", ".price_color"),
            ("Link selector (relative)", "h3 a"),
        ]
        self.selector_entries = []
        for index, (label, placeholder) in enumerate(selectors):
            selector_frame.grid_columnconfigure(index, weight=1)
            field = ctk.CTkFrame(selector_frame, fg_color="transparent")
            field.grid(
                row=0, column=index, sticky="ew",
                padx=(0 if index == 0 else 8, 0),
            )
            ctk.CTkLabel(
                field, text=label, text_color=TEXT,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w")
            entry = ctk.CTkEntry(
                field, placeholder_text=placeholder,
                border_color="#D1D5DB", height=34,
            )
            entry.pack(fill="x", pady=(3, 0))
            self.selector_entries.append(entry)

        ctk.CTkLabel(
            setup,
            text=(
                "Selectors are optional for automatic modes. Custom Data "
                "requires an item selector. Other selectors are relative to each item."
            ),
            text_color=SECONDARY, font=ctk.CTkFont(size=10),
            wraplength=1000, justify="left",
        ).grid(
            row=3, column=0, columnspan=3, sticky="w",
            padx=18, pady=(4, 16),
        )

        self.input_widgets = [
            self.url_entry, self.practice_button, self.mode_menu,
            *self.selector_entries,
        ]

    def build_buttons(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))
        bar.grid_columnconfigure(2, weight=1)

        self.start_button = ctk.CTkButton(
            bar, text="Start Scraping", height=38, width=150,
            fg_color=GREEN, hover_color="#14532D", command=self.start_scraping,
        )
        self.start_button.grid(row=0, column=0, padx=(0, 9))

        self.clear_button = ctk.CTkButton(
            bar, text="Clear Results", height=38, width=120,
            fg_color=WHITE, text_color=GREEN,
            border_width=1, border_color="#D1D5DB",
            hover_color="#DCFCE7", command=self.clear_results,
        )
        self.clear_button.grid(row=0, column=1)

        self.excel_button = ctk.CTkButton(
            bar, text="Export to Excel", height=38, width=130,
            fg_color=GREEN, hover_color="#14532D",
            command=lambda: self.save_results("excel"),
        )
        self.excel_button.grid(row=0, column=3, padx=(9, 0))

        self.csv_button = ctk.CTkButton(
            bar, text="Export to CSV", height=38, width=125,
            fg_color=GREEN, hover_color="#14532D",
            command=lambda: self.save_results("csv"),
        )
        self.csv_button.grid(row=0, column=4, padx=(9, 0))

    def build_results(self):
        panel = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=12)
        panel.grid(row=3, column=0, sticky="nsew", padx=24)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=10)
        ctk.CTkLabel(
            heading, text="Results preview", text_color=TEXT,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        self.count_label = ctk.CTkLabel(
            heading, text="0 records", text_color=GREEN
        )
        self.count_label.pack(side="right")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Scraper.Treeview", background=WHITE, foreground=TEXT,
            fieldbackground=WHITE, rowheight=30, font=("Arial", 10),
            borderwidth=0,
        )
        style.configure(
            "Scraper.Treeview.Heading", background=GREEN,
            foreground=WHITE, font=("Arial", 10, "bold"),
            padding=(10, 9), relief="flat",
        )
        style.map(
            "Scraper.Treeview",
            background=[("selected", "#BBF7D0")],
            foreground=[("selected", TEXT)],
        )
        style.map("Scraper.Treeview.Heading", background=[("active", GREEN)])

        keys = [key for key, label in COLUMNS]
        self.tree = ttk.Treeview(
            panel, columns=keys, show="headings",
            style="Scraper.Treeview", height=7,
        )
        widths = [300, 125, 350, 220]
        for (key, label), width in zip(COLUMNS, widths):
            self.tree.heading(key, text=label, anchor="w")
            self.tree.column(key, width=width, minwidth=100, anchor="w")

        self.tree.tag_configure("alternate", background=LIGHT_GREEN)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(12, 0))
        vertical = ttk.Scrollbar(panel, orient="vertical", command=self.tree.yview)
        vertical.grid(row=1, column=1, sticky="ns", padx=(0, 10))
        horizontal = ttk.Scrollbar(
            panel, orient="horizontal", command=self.tree.xview
        )
        horizontal.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.tree.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )

    def build_status(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=26, pady=(10, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(
            footer, mode="indeterminate", height=3,
            progress_color=BRIGHT_GREEN, fg_color="#DCFCE7",
        )
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.progress.grid_remove()

        self.status_label = ctk.CTkLabel(
            footer,
            text="Ready. Use the practice URL, choose a mode, and start scraping.",
            text_color=SECONDARY, anchor="w", justify="left",
            wraplength=1100, font=ctk.CTkFont(size=11),
        )
        self.status_label.grid(row=1, column=0, sticky="ew")

    def resize_status(self, event):
        if event.widget is self and hasattr(self, "status_label"):
            self.status_label.configure(wraplength=max(300, event.width - 60))

    def show_status(self, text, error=False):
        self.status_label.configure(
            text=text, text_color=RED if error else SECONDARY
        )

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in self.input_widgets:
            widget.configure(state=state)
        self.start_button.configure(
            state=state, text="Working..." if busy else "Start Scraping"
        )
        result_state = "normal" if self.records and not busy else "disabled"
        for button in (self.clear_button, self.excel_button, self.csv_button):
            button.configure(state=result_state)
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def load_practice(self):
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, "https://books.toscrape.com/")
        self.mode_menu.set("Product Prices")
        for entry in self.selector_entries:
            entry.delete(0, "end")
        self.show_status("Practice URL loaded. Click Start Scraping to collect book prices.")

    def clear_results(self):
        if self.busy:
            return
        self.records = []
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.count_label.configure(text="0 records")
        self.set_busy(False)
        self.show_status("Results cleared. Ready for your next scrape.")

    def start_scraping(self):
        if self.busy:
            return

        # Read widget values ONLY on the GUI thread.
        settings = {
            "url": self.url_entry.get().strip(),
            "mode": self.mode_menu.get(),
        }
        names = ("item_selector", "text_selector", "value_selector", "link_selector")
        for name, entry in zip(names, self.selector_entries):
            settings[name] = entry.get().strip()

        self.clear_results()
        self.set_busy(True)
        self.show_status("Connecting to the website and reading its HTML...")
        threading.Thread(
            target=self.scrape_worker, args=(settings,), daemon=True
        ).start()

    def scrape_worker(self, settings):
        # Background workers never call Tkinter widgets.
        try:
            records = scrape_website(**settings)
            self.messages.put(("scraped", records))
        except ScrapeError as exc:
            self.messages.put(("error", str(exc)))
        except Exception as exc:
            self.messages.put(("error", f"Unable to scrape this page: {exc}"))

    def save_results(self, kind):
        if self.busy:
            return
        if not self.records:
            messagebox.showinfo(
                "No results", "Scrape a page before exporting.", parent=self
            )
            return

        extension = ".xlsx" if kind == "excel" else ".csv"
        label = "Excel workbook" if kind == "excel" else "CSV file"
        filename = filedialog.asksaveasfilename(
            parent=self, title=f"Export to {kind.upper()}",
            defaultextension=extension,
            initialfile=f"scraped_data{extension}",
            filetypes=[(label, f"*{extension}")],
        )
        if not filename:
            return

        records = [record.copy() for record in self.records]
        self.set_busy(True)
        self.show_status("Formatting and saving your export...")
        threading.Thread(
            target=self.export_worker,
            args=(kind, records, filename),
            daemon=True,
        ).start()

    def export_worker(self, kind, records, filename):
        try:
            if kind == "excel":
                export_excel(records, filename)
            else:
                export_csv(records, filename)
            self.messages.put(("exported", filename))
        except PermissionError:
            self.messages.put((
                "error",
                "Cannot save this file. Close it in Excel if it is open, "
                "or choose a folder where you have write permission.",
            ))
        except Exception as exc:
            self.messages.put(("error", f"Export failed: {exc}"))

    def poll_messages(self):
        # after() schedules this function safely on Tkinter's main thread.
        try:
            while True:
                event, payload = self.messages.get_nowait()
                if event == "scraped":
                    self.records = payload
                    for index, record in enumerate(self.records):
                        self.tree.insert(
                            "", "end",
                            values=[record.get(key, "") for key, label in COLUMNS],
                            tags=("alternate",) if index % 2 else (),
                        )
                    self.count_label.configure(text=f"{len(self.records)} records")
                    self.set_busy(False)
                    self.show_status(
                        f"Collected {len(self.records)} records. "
                        "Review the table, then export to Excel or CSV. "
                        "Blank values mean that no value was found."
                    )
                elif event == "exported":
                    self.set_busy(False)
                    self.show_status(f"Export saved successfully: {payload}")
                    messagebox.showinfo(
                        "Export complete", f"Your file was saved:\n{payload}", parent=self
                    )
                elif event == "error":
                    self.set_busy(False)
                    self.show_status(payload, error=True)
                    messagebox.showerror("Web Scraper", payload, parent=self)
        except queue.Empty:
            pass

        self.poll_id = self.after(100, self.poll_messages)

    def close_app(self):
        # Daemon workers may finish without touching the closed window.
        self.after_cancel(self.poll_id)
        self.destroy()


if __name__ == "__main__":
    app = WebScraperApp()
    app.mainloop()
