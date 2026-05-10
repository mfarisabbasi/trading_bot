import os
import runpy


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(base_dir, "main.py")
    runpy.run_path(main_path, run_name="__main__")