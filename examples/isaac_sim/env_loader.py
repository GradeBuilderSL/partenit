"""
Load .env from project paths. Reusable across robots and environments.
Call before importing modules that need LLM_PROVIDER, *_API_KEY, etc.
"""

import os


def load_project_env(
    script_dir: str | None = None,
    extra_paths: list[str] | None = None,
) -> str | None:
    """
    Load .env from standard project locations and optional extra paths.
    Returns path that was loaded, or None if none found.
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    paths = [
        os.path.join(script_dir, "..", ".env"),
        os.path.join(script_dir, "..", "ontorobotic", ".env"),
    ]
    if extra_paths:
        paths.extend(extra_paths)
    for path in paths:
        p = os.path.normpath(path)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and v:
                            os.environ.setdefault(k, v)
            print(f"[ENV] Loaded from {p}")
            return p
    return None
