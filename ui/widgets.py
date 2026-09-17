import tkinter as tk
class ToolTip:
    def __init__(self,widget,text):
        self.widget=widget; self.text=text; self.tip=None
        widget.bind('<Enter>',self.show,add='+'); widget.bind('<Leave>',self.hide,add='+')
    def show(self,event=None):
        if self.tip or not self.text:return
        try:
            x=self.widget.winfo_rootx()+self.widget.winfo_width()+8; y=self.widget.winfo_rooty()+4
            self.tip=tk.Toplevel(self.widget); self.tip.wm_overrideredirect(True); self.tip.configure(bg='#0b1018')
            tk.Label(self.tip,text=self.text,bg='#0b1018',fg='#eef4fa',font=('Segoe UI',8),padx=8,pady=4).pack()
            self.tip.geometry(f'+{x}+{y}')
        except Exception: self.tip=None
    def hide(self,event=None):
        if self.tip:
            try:self.tip.destroy()
            except Exception:pass
            self.tip=None
