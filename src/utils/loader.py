import importlib
from pathlib import Path


def load_routers(path: str):
    routers = []

    base_path = Path(path)

    for file in base_path.glob("*.py"):
        if file.name.startswith("_"):
            continue

        module_name = file.stem
        import_path = path.replace("/", ".") + f".{module_name}"

        module = importlib.import_module(import_path)

        if hasattr(module, "router"):
            routers.append(module.router)

    return routers

def load_loops(path: str):
    loops = []

    base_path = Path(path)

    for file in base_path.glob("*.py"):
        if file.name.startswith("_"):
            continue

        module_name = file.stem
        import_path = path.replace("/", ".") + f".{module_name}"

        module = importlib.import_module(import_path)

        if hasattr(module, "loop_handler"):
            loops.append(module.loop_handler)

    return loops