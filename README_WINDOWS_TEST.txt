WINDOWS BUILD / TEST

1) На Windows запустите build_exe.bat.
2) Он соберет dist\LegalDesk.exe.
3) Для исходников: VERIFY_WINDOWS.bat.
4) Для самой frozen EXE: VERIFY_EXE.bat.

Полный Windows runtime test нельзя выполнить в текущем Linux-окружении, поэтому в проект добавлен готовый Windows smoke test и GitHub Actions workflow. В workflow реальный EXE собирается и запускается на windows-latest.
