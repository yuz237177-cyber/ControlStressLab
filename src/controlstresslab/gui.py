"""Optional Windows desktop entry point. Importing this module does not require Qt."""


def main():
    try:
        from .gui_window import main as launch
    except ImportError as exc:
        raise SystemExit('桌面依赖未安装，请运行 python -m pip install ".[gui]"；'+str(exc)) from exc
    launch()


if __name__ == "__main__": main()
