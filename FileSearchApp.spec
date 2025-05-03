# -*- mode: python ; coding: utf-8 -*-

import pymorphy2_dicts_ru
pymorph_data = pymorphy2_dicts_ru.get_path()

import ru_synonyms
import os
ru_synonyms_path = os.path.dirname(ru_synonyms.__file__)
ru_synonyms_data = os.path.join(ru_synonyms_path, '_data')

a = Analysis(
    ['FileSearchApp.py'],
    pathex=[],
    binaries=[],
    datas=[
            (pymorph_data, 'pymorphy2_dicts_ru/data'),
            (ru_synonyms_data, 'ru_synonyms/_data'),
            ('C:\\Users\\delev\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\natasha\\data\\emb', 'natasha/data/emb'),
            ('C:\\Users\\delev\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\natasha\\data\\model', 'natasha/data/model')
            ],
    hiddenimports=['natasha', 'pymorphy2', 'PyQt6', 'whoosh', 'ru_synonyms'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Поисковик',
    icon='D:\\Projects\\FileSearchProject\\search.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
