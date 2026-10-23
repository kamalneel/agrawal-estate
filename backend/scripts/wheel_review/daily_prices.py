"""Daily closes (daily.json from daily.py) — the only price source for the
wheel review. Weekly DB bars are dated Monday but hold Friday's close, which
leaks the week's move into anything priced on a Monday (see the session-2
correction). No weekly fallback: a symbol without daily data is reported
missing, not guessed."""
import bisect, json, math
from datetime import date, timedelta

class Daily:
    def __init__(self, path):
        raw = json.load(open(path))
        self.days = {s: [r[0] for r in rows] for s, rows in raw.items()}
        self.close = {s: [r[2] for r in rows] for s, rows in raw.items()}

    def on(self, sym, d, max_gap=7):
        """Close on day d, else the last close before it (holidays)."""
        d = str(d)
        if sym not in self.days: return None
        i = bisect.bisect_right(self.days[sym], d) - 1
        if i < 0: return None
        gap = (date.fromisoformat(d) - date.fromisoformat(self.days[sym][i])).days
        return self.close[sym][i] if gap <= max_gap else None

    def before(self, sym, d):
        """Last close strictly before day d — what was known before a trade."""
        d = str(d)
        if sym not in self.days: return None
        i = bisect.bisect_left(self.days[sym], d) - 1
        return self.close[sym][i] if i >= 0 else None

    def ret(self, sym, d, weeks):
        a = self.before(sym, date.fromisoformat(str(d)) - timedelta(weeks=weeks))
        b = self.before(sym, d)
        return b / a - 1 if a and b else None

    def vol(self, sym, d, weeks=26):
        """Annualized realized vol from daily closes over the weeks before d."""
        d = str(d)
        if sym not in self.days: return None
        lo = str(date.fromisoformat(d) - timedelta(weeks=weeks))
        i0 = bisect.bisect_left(self.days[sym], lo); i1 = bisect.bisect_left(self.days[sym], d)
        c = self.close[sym][i0:i1]
        if len(c) < 30: return None
        r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        m = sum(r) / len(r)
        return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
