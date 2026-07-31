PHASE 20D2A3 REPOSITORY OVERLAY

Extract this ZIP directly into the QMeet1 repository root and allow it to replace existing files.
The archive uses the actual repository paths and filenames.

After extraction, from the repository root run:

  powershell -ExecutionPolicy Bypass -File .\VERIFY_PHASE20D2A3.ps1
  cd backend
  python -m unittest discover -s tests -p "test_focus_update_install_contract_phase20d2a3.py" -v
  python -m unittest discover -s tests -p "test_focus_update_route_parity_phase20d2a3.py" -v
  python -m unittest discover -s tests -p "test_focus_native_update_phase20d2a3.py" -v
  cd ..
  npm run build

Then commit and push the actual target files. Fully restart backend and frontend.
