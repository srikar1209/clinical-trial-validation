"""
Figures for the README, drawn from trial.db.

Run from the repo root (after run_all):   python -m clinical_trial_validation.figures
Output: images/routing.png, images/site_signal.png, images/submission.png
"""
import sqlite3

import pandas as pd

from clinical_trial_validation.config import DB, IMAGES, Z_THRESHOLD

INK, INK2, GRID_C, AXIS_C, SURF = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, AQUA, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#b9b8b0"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _style(ax, title):
    ax.set_facecolor(SURF)
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.grid(True, axis="x", color=GRID_C, lw=0.6)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(AXIS_C)
    ax.tick_params(colors=INK2)


def _label_bars(ax, bars, fmt):
    for b in bars:
        w = b.get_width()
        ax.annotate(fmt(w), (w, b.get_y() + b.get_height() / 2), xytext=(4, 0),
                    textcoords="offset points", va="center", color=INK2, fontsize=9)


def _save(plt, fig, name):
    IMAGES.mkdir(exist_ok=True)
    out = IMAGES / name
    plt.tight_layout()
    fig.savefig(out, facecolor=SURF)
    plt.close(fig)
    print(f"Saved {out.relative_to(DB.parent)}")


def routing(con):
    """Where the records went, and why records went to human review."""
    plt = _plt()
    rec = pd.read_sql_query("SELECT decision, reason FROM records", con)
    counts = rec.decision.value_counts().reindex(["QUERY_SITE", "HUMAN_REVIEW", "AUTO_CLEAR"]).fillna(0)
    hr = rec[rec.decision == "HUMAN_REVIEW"].reason.str.split(":").str[0] \
        .str.replace(r"AE grade \d \(severe\)", "AE grade 3+ (severe)", regex=True).value_counts().sort_values()

    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), dpi=150, facecolor=SURF)
    bars = axes[0].barh(counts.index, counts.values, color=[ORANGE, BLUE, AQUA], height=0.6)
    _label_bars(axes[0], bars, lambda v: f"{v:,.0f} ({100 * v / counts.sum():.1f}%)")
    axes[0].set_xlim(0, counts.max() * 1.3)
    axes[0].set_xlabel("Records", color=INK2)
    _style(axes[0], "A. Routing decision")
    bars = axes[1].barh(hr.index, hr.values, color=BLUE, height=0.6)
    _label_bars(axes[1], bars, lambda v: f"{v:,.0f}")
    axes[1].set_xlim(0, hr.max() * 1.2)
    axes[1].set_xlabel("Records", color=INK2)
    _style(axes[1], "B. Why records went to human review")
    _save(plt, fig, "routing.png")


def site_signal(con):
    """Share of XR-17 visits with an ALT outlier, per site. The signal site stands out."""
    plt = _plt()
    s = pd.read_sql_query("SELECT * FROM site_signals ORDER BY site_id DESC", con)
    top = s.site_z.idxmax()
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150, facecolor=SURF)
    bars = ax.barh(s.site_id, s.pct_alt_outliers, height=0.6,
                   color=[ORANGE if i == top else MUTED for i in s.index])
    _label_bars(ax, bars, lambda v: f"{v:.1f}%")
    ax.set_xlim(0, s.pct_alt_outliers.max() * 1.25)
    ax.set_xlabel(f"XR-17 visits with ALT z ≥ {Z_THRESHOLD:g} (%)", color=INK2)
    _style(ax, "Site safety signal (valid records only)")
    _save(plt, fig, "site_signal.png")


def submission(con):
    """Failed submissions for each client against the same flaky outside system."""
    plt = _plt()
    g = pd.read_sql_query("SELECT client, failed FROM gateway_results", con)
    g = g[~g.client.str.contains("first pass")].iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 3), dpi=150, facecolor=SURF)
    bars = ax.barh(g.client, g.failed, height=0.6,
                   color=[AQUA if "Gateway" in c else ORANGE for c in g.client])
    _label_bars(ax, bars, lambda v: f"{v:,.0f}")
    ax.set_xlim(0, max(g.failed.max(), 1) * 1.2)
    ax.set_xlabel("Failed submissions", color=INK2)
    _style(ax, "Sending cleared records to a flaky outside system")
    _save(plt, fig, "submission.png")


def main():
    if not DB.exists():
        raise SystemExit("trial.db not found. Run first:  python -m clinical_trial_validation.run_all")
    con = sqlite3.connect(DB)
    try:
        routing(con)
        site_signal(con)
        submission(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
