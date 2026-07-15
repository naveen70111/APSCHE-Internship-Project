"""
main.py  —  Chronicle Intelligence  Entry Point  v9-BUGFIX
"""
import tkinter as tk
import database
import rss_manager
import ui_components
import config


class NewsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(config.APP_TITLE)
        self.geometry(f"{config.APP_WIDTH}x{config.APP_HEIGHT}")
        self.minsize(960, 660)

        try:
            self.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        database.init_db()
        self.session = rss_manager.SessionManager()

        self.container = tk.Frame(self, bg="#080E1C")
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames: dict = {}
        for FrameClass in (ui_components.LoginFrame, ui_components.RegisterFrame):
            name  = FrameClass.__name__
            frame = FrameClass(parent=self.container, controller=self)
            self.frames[name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginFrame")

    def show_frame(self, page_name: str):
        self.frames[page_name].tkraise()

    def launch_dashboard(self):
        frame = ui_components.DashboardFrame(
            parent=self.container, controller=self)
        self.frames["DashboardFrame"] = frame
        frame.grid(row=0, column=0, sticky="nsew")
        self.show_frame("DashboardFrame")


if __name__ == "__main__":
    app = NewsApp()
    app.mainloop()
