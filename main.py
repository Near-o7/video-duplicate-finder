import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from comparador.selftest import run_selftest
        sys.exit(run_selftest(sys.argv[2]))
    from comparador.ui import run
    sys.exit(run())
