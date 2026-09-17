import sys


# The frozen Windows build can run its own end-to-end smoke suite with
# ``LegalDesk.exe --smoke-test``. This lets GitHub Actions test the actual
# bundled executable instead of merely launching a GUI process.
if '--smoke-test' in sys.argv:
    from windows_smoke_test import main as _smoke_main
    raise SystemExit(_smoke_main())

from ui.app import App


def main():
    app=App()
    app.bind_all('<Control-f>',lambda e:(app.search.focus_force(),'break')[1])
    app.bind_all('<Control-k>',lambda e:(app.open_command_palette(),'break')[1])
    app.bind_all('<Control-b>',lambda e:(app.toggle_bookmark(),'break')[1])
    app.bind_all('<Control-c>',lambda e:(app.copy(),'break')[1])
    app.bind_all('<Alt-Left>',lambda e:(app.go_back(),'break')[1])
    app.bind_all('<Alt-Right>',lambda e:(app.go_forward(),'break')[1])
    app.bind_all('<Control-comma>',lambda e:(app.open_settings(),'break')[1])
    app.bind_all('<Escape>',lambda e:(app.reset(),'break')[1])
    app.bind_all('<F1>',lambda e:(app.show_detention(),'break')[1])
    app.bind_all('<F2>',lambda e:(app.show_uk(),'break')[1])
    app.bind_all('<F3>',lambda e:(app.show_koap(),'break')[1])
    app.bind_all('<F4>',lambda e:(app.open_by_title('процессуальный кодекс'),'break')[1])
    app.bind_all('<F5>',lambda e:(app.open_by_title('уголовно-процессуальный кодекс'),'break')[1])
    app.bind_all('<F6>',lambda e:(app.show_fsb(),'break')[1])
    app.mainloop()

if __name__=='__main__':
    main()
