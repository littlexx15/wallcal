"""Synthetic date-selection benchmark, isolated from user data."""
import os, sys, time, statistics
from pathlib import Path
from copy import deepcopy
from datetime import date
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['WALLCAL_DATA_DIR']=str(Path('build/perf-data').resolve())
from wallcal.storage import DEFAULT_STATE,new_memo,save
state=deepcopy(DEFAULT_STATE);state['settings'].update(first_run=False,wallpaper_enabled=False)
for d in range(1,29):
    for i in range(3):
        state['memos'].append(new_memo(title=f'测试事项{i}',day=date(2026,9,d)))
save(state)
from wallcal.ui import WallCalWindow
with patch('wallcal.ui.cloudsync.logged_in',return_value=False),patch('wallcal.ui.autostart.is_enabled',return_value=False):
    app=WallCalWindow();app.geometry('874x690+20+20');app.update()
    timings=[]
    for d in range(1,21):
        t=time.perf_counter();app._select_day(date(2026,9,d));app.update_idletasks();timings.append((time.perf_counter()-t)*1000)
    print('SELECTION_MS median=',round(statistics.median(timings),1),'max=',round(max(timings),1))
    app.quit_app()
