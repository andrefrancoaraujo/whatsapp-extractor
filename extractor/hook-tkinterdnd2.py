"""PyInstaller hook for tkinterdnd2 — bundles native TkDnD DLLs."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('tkinterdnd2')
