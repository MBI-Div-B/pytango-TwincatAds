from .TwincatAds import TwincatAds


def main():
    import sys
    import tango.server

    args = ["TwincatAds"] + sys.argv[1:]
    tango.server.run((TwincatAds,), args=args)