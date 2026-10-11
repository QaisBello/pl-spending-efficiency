"""Parse openfootball Football.TXT files (data/raw/results) into one match table."""
import glob, os, re
import pandas as pd

A = re.compile(r"^\s*(?:\d{1,2}[:.]\d{2})?\s*(?P<h>\S.*?\S)\s{2,}(?P<hg>\d+)-(?P<ag>\d+)(?:\s*\([^)]*\))?\s{2,}(?P<a>\S.*?)\s*$")
B = re.compile(r"^\s*(?:\d{1,2}[:.]\d{2})?\s*(?P<h>\S.*?\S)\s+v\s+(?P<a>\S.*?\S)\s+(?P<hg>\d+)-(?P<ag>\d+)(?:\s*\([^)]*\))?\s*$")


def parse(path):
    season = os.path.basename(path)[:7]
    rows = []
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith(("#", "=", "▪")) or "-" not in line:
            continue
        m = B.match(line) or A.match(line)
        if m:
            rows.append(dict(season=season, home=m["h"].strip(), away=m["a"].strip(), hg=int(m["hg"]), ag=int(m["ag"])))
    return rows


def matches(raw_dir):
    return pd.DataFrame([r for f in sorted(glob.glob(os.path.join(raw_dir, "*-premierleague.txt"))) for r in parse(f)])


if __name__ == "__main__":
    m = matches(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw", "results"))
    print(m.groupby("season").size().to_string())
