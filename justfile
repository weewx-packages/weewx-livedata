default: fast

fast:
    PYTHONPATH="bin${PYTHONPATH:+:$PYTHONPATH}" python3 -m pytest -q tests
