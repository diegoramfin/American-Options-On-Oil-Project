"""Excel report laid out like a bank pricing model.

Sheets: Inputs, Quotes, Smile, Surface, Tree, Monte Carlo, Validation.
Colour code, applied automatically by _value: blue = hard-coded input or value computed in
Python, black = formula, green = formula that links to another sheet. Grey = comment.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series, SurfaceChart3D
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NAVY, BLUE, BLACK, GREEN, GREY = "1F3864", "0000FF", "000000", "008000", "595959"
EXERCISE_FILL = PatternFill("solid", fgColor="F8CBAD")
PRICE = '#,##0.00;(#,##0.00);"-"'
PRECISE = "0.0000"
DIFF = '0.0000;(0.0000);"-"'
PCT = "0.00%"
RATIO = "0.000"
DATE = "yyyy-mm-dd"
COUNT = "#,##0"

HEADER_ROW = 4
SMILE_EXPIRIES = 3


@dataclass
class PricingRun:
    """Everything the report shows. Computed by scripts/price_snapshot.py."""

    snapshot: str
    pulled_utc: pd.Timestamp
    val_date: pd.Timestamp
    spot: float
    rate: float
    vols: dict[str, tuple[float, float]]  # window -> (sigma, standard error)
    window_days: dict[str, int]
    base_window: str
    n_steps: int
    max_spread: float
    n_pulled: int
    # expiry, T, kind, strike, bid, ask, mid, lsm, lsm_se, tree_am, bs_eu, iv, otm
    quotes: pd.DataFrame
    smile_quotes: pd.DataFrame  # OTM quotes with an implied vol, sorted by expiry and strike
    surface_fit: pd.DataFrame  # implied vol, index K/S grid, columns expiries
    parity: pd.DataFrame  # expiry, pairs, passed
    validation: list  # sections of (title, rows of (label, reference, model), note)
    dividend_lattice: list  # dummy American call with a dividend, for the Validation sheet
    # Illustrative at-the-money put, shared by the Tree and Monte Carlo sheets.
    contract: str
    strike: float
    lattice: list  # per step: (stock prices, put values, early-exercise flags)
    convergence: pd.DataFrame  # n, tree_am_put, tree_eu_call, bs_call
    benchmarks: list[tuple[str, float]]  # (label, price) the Monte Carlo is compared with
    lsm: pd.DataFrame  # paths, price, stderr
    exercise_dates: int
    lsm_paths: int
    max_exercise_dates: int
    confirm_tolerance: float
    sample_paths: pd.DataFrame  # index time in years, one column per simulated path


def write_report(path: Path, run: PricingRun) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    refs = _inputs_sheet(wb, run)
    _quotes_sheet(wb, run, refs)
    _smile_sheet(wb, run, refs)
    _surface_sheet(wb, run, refs)
    _tree_sheet(wb, run)
    _monte_carlo_sheet(wb, run)
    _validation_sheet(wb, run)
    wb.save(path)


# ---------------------------------------------------------------- cell and chart helpers


def _sheet(wb, name, title, subtitle):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    _cell(ws, 1, 2, title).font = Font(bold=True, size=14)
    _cell(ws, 2, 2, subtitle).font = Font(italic=True, color=GREY)
    return ws


def _header(ws, row, col, labels):
    for i, label in enumerate(labels):
        cell = ws.cell(row, col + i, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="left" if i == 0 else "center", wrap_text=True)


def _cell(ws, row, col, value, fmt=None, color=BLACK, bold=False):
    cell = ws.cell(row, col, value)
    cell.font = Font(color=color, bold=bold)
    if fmt:
        cell.number_format = fmt
    return cell


def _value(ws, row, col, value, fmt=None, bold=False):
    """A data cell, coloured by the model convention."""
    if isinstance(value, str) and value.startswith("="):
        color = GREEN if "!" in value else BLACK
    else:
        color = BLUE
    return _cell(ws, row, col, value, fmt, color, bold)


def _note(ws, row, text):
    _cell(ws, row, 2, text, color=GREY)


def _widths(ws, widths):
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _scatter(title, x_title, y_title, x_format="General", y_format="General"):
    chart = ScatterChart()
    chart.title = title
    chart.x_axis.title, chart.y_axis.title = x_title, y_title
    chart.x_axis.number_format, chart.y_axis.number_format = x_format, y_format
    chart.x_axis.delete = chart.y_axis.delete = False
    chart.width, chart.height = 20, 11
    return chart


def _add_series(chart, ws, x_col, y_col, first, last, title, marker="circle", dash=None):
    x = Reference(ws, min_col=x_col, min_row=first, max_row=last)
    y = Reference(ws, min_col=y_col, min_row=first, max_row=last)
    series = Series(y, x, title=title)
    series.marker.symbol = marker
    if dash:
        series.graphicalProperties.line.dashStyle = dash
    chart.series.append(series)
    return series


# ---------------------------------------------------------------- sheets


def _inputs_sheet(wb, run) -> dict[str, str]:
    """Write the Inputs sheet. Return absolute references to the cells other sheets use."""
    ws = _sheet(
        wb,
        "Inputs",
        f"BNO American Option Pricing | Snapshot {run.snapshot}",
        "CRR binomial tree on a frozen Yahoo Finance snapshot | U.S. Dollars",
    )
    vols = [
        (f"vol_{w}", f"Volatility, {w} lookback", "σ", sigma, PCT,
         f"± {err:.2%}; {run.window_days[w]} daily log returns")
        for w, (sigma, err) in run.vols.items()
    ]  # fmt: skip
    last_quote = HEADER_ROW + len(run.quotes)
    # (key, label, symbol, value, format, comment); formulas may use {key} of earlier rows.
    sections = {
        "Market Inputs": [
            ("pulled", "Market data pulled", "", f"{run.pulled_utc:%Y-%m-%d %H:%M} UTC", None,
             "Spot, rate and option quotes were all taken at this moment"),
            ("val_date", "Valuation date", "t₀", run.val_date.to_pydatetime(), DATE,
             "Date of the last BNO price in the snapshot"),
            ("spot", "BNO price at pull", "S", run.spot, PRICE,
             "Last BNO price, Yahoo Finance; intraday if pulled while the market was open"),
            ("rate", "Risk-free rate", "r", run.rate, "0.000%",
             "13-week T-bill (^IRX) / 100, Yahoo Finance"),
            ("q", "Dividend yield", "q", 0.0, PCT, "BNO treated as non-dividend paying"),
        ],
        "Historical Volatility": vols + [
            ("sigma", "Volatility used in the models", "σ", f"={{vol_{run.base_window}}}", PCT,
             f"{run.base_window} lookback: balances estimation error against stale regimes"),
        ],
        "Model Settings": [
            ("lsm_paths", "LSM paths per expiry", "", run.lsm_paths, COUNT,
             "Main pricer; one path set shared by all strikes of an expiry"),
            ("max_dates", "LSM max exercise dates", "", run.max_exercise_dates, COUNT,
             "Daily exercise up to this cap; longer expiries are priced as Bermudan"),
            ("n_steps", "Tree time steps, minimum", "n", run.n_steps, COUNT,
             "Steps the tree splits T into (Δt = T / n): one per business day, at least this many"),
            ("tolerance", "Confirmation tolerance", "", run.confirm_tolerance, PRICE,
             "Tree confirms LSM when |LSM − tree| ≤ 2 s.e. + this (one tick; covers tree error)"),
            ("max_spread", "Max bid-ask spread kept", "", run.max_spread, "0%",
             "Quotes with (ask − bid) / mid above this are dropped"),
        ],
        "Data Summary": [
            ("n_pulled", "Option rows in snapshot", "", run.n_pulled, COUNT,
             f"data/snapshots/{run.snapshot}/chains.csv"),
            ("n_used", "Quotes priced", "", f"=COUNT(Quotes!E{HEADER_ROW + 1}:E{last_quote})",
             COUNT, "After cleaning; see Quotes sheet"),
        ],
    }  # fmt: skip

    refs: dict[str, str] = {}
    row = HEADER_ROW
    for section, items in sections.items():
        _header(ws, row, 2, [section, "Symbol", "Value", "Source / Comment"])
        for key, label, symbol, value, fmt, comment in items:
            row += 1
            if isinstance(value, str):
                value = value.format_map(refs)
            _cell(ws, row, 2, label)
            _cell(ws, row, 3, symbol).alignment = Alignment(horizontal="center")
            _value(ws, row, 4, value, fmt)
            _cell(ws, row, 5, comment, color=GREY)
            refs[key] = f"Inputs!$D${row}"
        row += 2
    _widths(ws, {"B": 32, "C": 8, "D": 14, "E": 58})
    return refs


QUOTE_COLUMNS = [
    "Expiry", "T (years)", "Type", "Strike", "K / S", "Bid", "Ask", "Mid", "LSM (American)",
    "LSM s.e.", "Tree (American)", "Black-Scholes (European)", "LSM − Mid", "LSM − Tree",
    "Tree confirms", "Implied Vol", "OTM",
]  # fmt: skip


def _quotes_sheet(wb, run, refs):
    ws = _sheet(
        wb,
        "Quotes",
        "Option Quotes and Model Prices",
        f"BNO options | σ = {run.base_window} historical | main price: LSM; confirmation: tree "
        f"(one time step per business day, at least {run.n_steps}), confirmed within 2 s.e. + "
        "tolerance | implied vol on the "
        "tree | "
        "OTM = used in Smile and Surface",
    )
    _header(ws, HEADER_ROW, 2, QUOTE_COLUMNS)
    spot = refs["spot"]
    for i, q in enumerate(run.quotes.itertuples(index=False)):
        r = HEADER_ROW + 1 + i
        row = [  # columns B..R, in QUOTE_COLUMNS order
            (q.expiry.to_pydatetime(), DATE),
            (q.T, RATIO),
            (q.kind.capitalize(), None),
            (q.strike, PRICE),
            (f"=E{r}/{spot}", RATIO),
            (q.bid, PRICE),
            (q.ask, PRICE),
            (f"=(G{r}+H{r})/2", PRICE),
            (q.lsm, PRICE),
            (q.lsm_se, PRECISE),
            (q.tree_am, PRICE),
            (q.bs_eu, PRICE),
            (f"=J{r}-I{r}", PRICE),
            (f"=J{r}-L{r}", PRICE),
            (f'=IF(ABS(O{r})<=2*K{r}+{refs["tolerance"]},"Yes","No")', None),
            (None if pd.isna(q.iv) else q.iv, PCT),
            (f'=IF(D{r}="Call",E{r}>={spot},E{r}<{spot})', None),
        ]
        for j, (value, fmt) in enumerate(row):
            _value(ws, r, 2 + j, value, fmt)
    ws.freeze_panes = f"C{HEADER_ROW + 1}"
    ws.auto_filter.ref = f"B{HEADER_ROW}:R{HEADER_ROW + len(run.quotes)}"
    ws.row_dimensions[HEADER_ROW].height = 30
    _widths(ws, {get_column_letter(c): 12 for c in range(2, 19)} | {"M": 16})


def _smile_sheet(wb, run, refs):
    ws = _sheet(
        wb,
        "Smile",
        "Implied Volatility Smile",
        "OTM options (puts below spot, calls above) | nearest expiries | "
        "dashed line = historical σ used in the models",
    )
    chart = _scatter(f"BNO implied vol smile, {run.snapshot}", "K / S", "Implied vol", "0.00", "0%")
    smile_quotes = run.smile_quotes
    expiries = sorted(smile_quotes["expiry"].unique())[:SMILE_EXPIRIES]
    col, first = 2, HEADER_ROW + 2
    for expiry in expiries:
        smile = smile_quotes[smile_quotes["expiry"] == expiry]
        label = f"{pd.Timestamp(expiry):%Y-%m-%d}"
        _cell(ws, HEADER_ROW, col, f"Expiry {label}", bold=True)
        _header(ws, HEADER_ROW + 1, col, ["Strike", "K / S", "Implied Vol"])
        for i, (strike, iv) in enumerate(zip(smile["strike"], smile["iv"])):
            r = first + i
            _value(ws, r, col, strike, PRICE)
            _value(ws, r, col + 1, f"={get_column_letter(col)}{r}/{refs['spot']}", RATIO)
            _value(ws, r, col + 2, iv, PCT)
        _add_series(chart, ws, col + 1, col + 2, first, first + len(smile) - 1, label)
        col += 4

    # Historical sigma as a flat reference line across the plotted moneyness range.
    moneyness = smile_quotes[smile_quotes["expiry"].isin(expiries)]["strike"] / run.spot
    _cell(ws, HEADER_ROW, col, "Reference", bold=True)
    _header(ws, HEADER_ROW + 1, col, ["K / S", "Historical σ"])
    for i, x in enumerate((moneyness.min(), moneyness.max())):
        _value(ws, first + i, col, x, RATIO)
        _value(ws, first + i, col + 1, f"={refs['sigma']}", PCT)
    sigma_title = f"Historical σ ({run.base_window})"
    _add_series(chart, ws, col, col + 1, first, first + 1, sigma_title, marker="none", dash="dash")

    ws.add_chart(chart, f"{get_column_letter(col + 3)}{HEADER_ROW}")
    _widths(ws, {get_column_letter(c): 11 for c in range(2, col + 2)})


def _surface_sheet(wb, run, refs):
    ws = _sheet(
        wb,
        "Surface",
        "Implied Volatility Surface",
        "Left: OTM implied vol by strike and expiry, blank = no clean quote, green = low, "
        "red = high | Right: the same vols interpolated on a common K/S grid for the 3D chart",
    )
    grid = run.smile_quotes.pivot_table(index="strike", columns="expiry", values="iv")
    maturities = run.quotes.groupby("expiry")["T"].first()
    _header(ws, HEADER_ROW, 2, ["Strike", "K / S"] + [f"{e:%Y-%m-%d}" for e in grid.columns])
    _cell(ws, HEADER_ROW + 1, 2, "T (years)", bold=True)
    for j, expiry in enumerate(grid.columns):
        _value(ws, HEADER_ROW + 1, 4 + j, maturities[expiry], RATIO)

    first = HEADER_ROW + 2
    for i, (strike, ivs) in enumerate(grid.iterrows()):
        r = first + i
        _value(ws, r, 2, strike, PRICE)
        _value(ws, r, 3, f"=B{r}/{refs['spot']}", RATIO)
        for j, iv in enumerate(ivs):
            if pd.notna(iv):
                _value(ws, r, 4 + j, iv, PCT)

    # Percentile anchors so one deep out-of-the-money outlier does not flatten the scale.
    last_col = get_column_letter(3 + len(grid.columns))
    scale = ColorScaleRule(
        start_type="percentile", start_value=5, start_color="63BE7B",
        mid_type="percentile", mid_value=50, mid_color="FFEB84",
        end_type="percentile", end_value=95, end_color="F8696B",
    )  # fmt: skip
    ws.conditional_formatting.add(f"D{first}:{last_col}{first + len(grid) - 1}", scale)
    ws.freeze_panes = f"D{first}"
    _widths(ws, {get_column_letter(c): 11 for c in range(2, 4 + len(grid.columns))})

    # Fitted grid and 3D chart, to the right of the raw grid.
    fit = run.surface_fit
    col = 6 + len(grid.columns)
    _header(ws, HEADER_ROW, col, ["K / S"] + [f"{e:%Y-%m-%d}" for e in fit.columns])
    for i, (moneyness, ivs) in enumerate(fit.iterrows()):
        _value(ws, first + i, col, moneyness, RATIO)
        for j, iv in enumerate(ivs):
            _value(ws, first + i, col + 1 + j, iv, PCT)
    last = first + len(fit) - 1
    chart = SurfaceChart3D()
    chart.title = f"BNO implied vol surface, {run.snapshot}"
    data = Reference(ws, min_col=col + 1, max_col=col + len(fit.columns), min_row=HEADER_ROW,
                     max_row=last)  # fmt: skip
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=col, min_row=first, max_row=last))
    chart.x_axis.title, chart.y_axis.title, chart.z_axis.title = "K / S", "Implied vol", "Expiry"
    chart.y_axis.number_format = "0%"
    chart.width, chart.height = 24, 14
    ws.add_chart(chart, f"{get_column_letter(col)}{last + 3}")
    _widths(ws, {get_column_letter(c): 11 for c in range(col, col + 1 + len(fit.columns))})


def _tree_sheet(wb, run):
    n = len(run.lattice) - 1
    ws = _sheet(
        wb,
        "Tree",
        "Binomial Tree (CRR), American Put",
        f"{run.contract} | lattice drawn with n = {n} time steps (Δt = T / n); shaded = early "
        "exercise is optimal | "
        f"quotes use one time step per business day, at least {run.n_steps}",
    )
    top = _lattice(ws, HEADER_ROW, run.lattice, "American put value")

    # Convergence in the number of steps.
    _header(
        ws,
        top,
        2,
        [
            "Time steps n (Δt = T / n)",
            "Tree American put",
            "Tree European call",
            "Black-Scholes call",
        ],
    )
    first = top + 1
    for i, (steps, am_put, eu_call, bs_call) in enumerate(run.convergence.itertuples(index=False)):
        _value(ws, first + i, 2, steps, COUNT).alignment = Alignment(horizontal="left")
        _value(ws, first + i, 3, am_put, PRECISE)
        _value(ws, first + i, 4, eu_call, PRECISE)
        _value(ws, first + i, 5, bs_call, PRECISE)
    last = first + len(run.convergence) - 1
    chart = _scatter("Tree price vs number of time steps n", "Time steps n", "Price", "0", "0.000")
    _add_series(chart, ws, 2, 3, first, last, "Tree American put", marker="none")
    _add_series(chart, ws, 2, 4, first, last, "Tree European call", marker="none")
    _add_series(chart, ws, 2, 5, first, last, "Black-Scholes call", marker="none", dash="dash")
    ws.add_chart(chart, f"G{top}")
    _widths(ws, {"B": 20} | {get_column_letter(c): 12 for c in range(3, 4 + n)})


def _monte_carlo_sheet(wb, run):
    ws = _sheet(
        wb,
        "Monte Carlo",
        "Longstaff-Schwartz Monte Carlo, American Put",
        f"{run.contract} | {run.exercise_dates} exercise dates | regression of discounted cash "
        "flow on 1, x, x², x³ with x = S / K, in-the-money paths only | Black-Scholes control "
        "variate",
    )
    best = run.lsm.iloc[-1]
    row = HEADER_ROW
    _header(ws, row, 2, ["Method", "Price", "Std error", "Comment"])
    lsm_row = row + 1
    _cell(ws, lsm_row, 2, "Longstaff-Schwartz")
    _value(ws, lsm_row, 3, best["price"], PRECISE)
    _value(ws, lsm_row, 4, best["stderr"], PRECISE)
    _cell(ws, lsm_row, 5, f"{int(best['paths']):,} paths", color=GREY)
    for i, (label, price) in enumerate(run.benchmarks):
        _cell(ws, lsm_row + 1 + i, 2, label)
        _value(ws, lsm_row + 1 + i, 3, price, PRECISE)
    tree_row, bs_row = lsm_row + 1, lsm_row + 2
    _cell(ws, bs_row + 1, 2, "LSM − tree")
    _value(ws, bs_row + 1, 3, f"=C{lsm_row}-C{tree_row}", DIFF)
    agree = f'=IF(ABS(C{bs_row + 1})<=2*D{lsm_row},"Agree (within 2 s.e.)","Check")'
    _value(ws, bs_row + 1, 5, agree)
    _cell(ws, bs_row + 2, 2, "Early-exercise premium (tree − BS)")
    _value(ws, bs_row + 2, 3, f"=C{tree_row}-C{bs_row}", DIFF)

    # Convergence in the number of paths, with a ±2 standard error band.
    top = bs_row + 5
    _header(ws, top, 2, ["Paths", "LSM price", "Std error", "−2 s.e.", "+2 s.e.", "Tree"])
    first = top + 1
    for i, (paths, price, stderr) in enumerate(run.lsm.itertuples(index=False)):
        r = first + i
        _value(ws, r, 2, paths, COUNT).alignment = Alignment(horizontal="left")
        _value(ws, r, 3, price, PRECISE)
        _value(ws, r, 4, stderr, PRECISE)
        _value(ws, r, 5, f"=C{r}-2*D{r}", PRECISE)
        _value(ws, r, 6, f"=C{r}+2*D{r}", PRECISE)
        _value(ws, r, 7, f"=$C${tree_row}", PRECISE)
    last = first + len(run.lsm) - 1
    chart = _scatter("LSM price vs number of paths", "Paths (log scale)", "Price", "#,##0", "0.000")
    chart.x_axis.scaling.logBase = 10
    _add_series(chart, ws, 2, 3, first, last, "LSM price")
    _add_series(chart, ws, 2, 5, first, last, "−2 s.e.", marker="none", dash="dash")
    _add_series(chart, ws, 2, 6, first, last, "+2 s.e.", marker="none", dash="dash")
    _add_series(chart, ws, 2, 7, first, last, "Tree", marker="none")
    ws.add_chart(chart, f"J{HEADER_ROW}")

    # Sample paths: chart first, data underneath.
    paths = run.sample_paths
    chart_row = last + 3
    data_top = chart_row + 24
    _header(ws, data_top, 2, ["Time (years)"] + [f"Path {c}" for c in paths.columns] + ["Strike"])
    for i, (t, values) in enumerate(paths.iterrows()):
        r = data_top + 1 + i
        _value(ws, r, 2, t, RATIO)
        for j, s in enumerate(values):
            _value(ws, r, 3 + j, s, PRICE)
        _value(ws, r, 3 + len(paths.columns), run.strike, PRICE)
    first, last = data_top + 1, data_top + len(paths)
    chart = _scatter(
        f"{len(paths.columns)} simulated BNO paths (risk-neutral GBM)",
        "Time (years)",
        "BNO",
        "0.00",
    )
    for j in range(len(paths.columns)):
        _add_series(chart, ws, 2, 3 + j, first, last, f"Path {j + 1}", marker="none")
    _add_series(chart, ws, 2, 3 + len(paths.columns), first, last, "Strike", "none", "dash")
    chart.legend = None
    ws.add_chart(chart, f"B{chart_row}")
    _widths(ws, {"B": 34, "C": 12, "D": 12, "E": 20, "F": 12, "G": 12})


def _validation_sheet(wb, run):
    ws = _sheet(
        wb,
        "Validation",
        "Model Validation",
        "Dummy data and textbook values (no market data), then LSM vs tree and market data "
        "checks on the snapshot | Difference = model − reference",
    )
    row = HEADER_ROW - 3
    for title, rows, note in run.validation:
        row += 3
        _header(ws, row, 2, [title, "Reference", "Model", "Difference"])
        for label, reference, model in rows:
            row += 1
            _cell(ws, row, 2, label)
            _value(ws, row, 3, reference, PRECISE)
            _value(ws, row, 4, model, PRECISE)
            _value(ws, row, 5, f"=D{row}-C{row}", DIFF)
        _note(ws, row + 1, note)

    row = _lattice(ws, row + 3, run.dividend_lattice, "American call value (dividend)")

    # LSM confirmed by the tree, counted live from the Quotes sheet.
    last = HEADER_ROW + len(run.quotes)
    dates = f"Quotes!$B${HEADER_ROW + 1}:$B${last}"
    confirms = f"Quotes!$P${HEADER_ROW + 1}:$P${last}"
    rows = [
        (expiry, f"=COUNTIF({dates},B{{row}})", f'=COUNTIFS({dates},B{{row}},{confirms},"Yes")')
        for expiry in sorted(run.quotes["expiry"].unique())
    ]
    row = _pass_rate_table(ws, row, "LSM confirmed by tree (2 s.e. + tolerance)", "Quotes", rows)
    _note(
        ws,
        row + 1,
        "Expect about 95% at 2 s.e. Strikes of one expiry share paths, so misses cluster "
        f"by expiry. Long expiries use at most {run.max_exercise_dates} exercise dates.",
    )

    rows = list(run.parity.itertuples(index=False))
    row = _pass_rate_table(ws, row + 3, "Put-call bounds on market mids", "Pairs", rows)
    _note(
        ws,
        row + 1,
        "Bounds: S − K < C − P < S − K·e^(−rT). Failures usually mean stale or "
        "non-synchronous quotes, not a model error.",
    )
    _widths(ws, {"B": 52, "C": 14, "D": 14, "E": 14, "F": 12, "G": 12, "H": 12, "I": 12})


def _lattice(ws, top, lattice, value_title):
    """Stock and option lattices, early-exercise nodes shaded. Return the row after them."""
    n = len(lattice) - 1
    for title, layer_index in (("Stock price", 0), (value_title, 1)):
        _header(ws, top, 2, [title] + [f"Step {i}" for i in range(n + 1)])
        for i, (_, _, exercised) in enumerate(lattice):
            for j, value in enumerate(lattice[i][layer_index]):
                # Up-moves go up the page: all-up node on the first row, all-down on the last.
                cell = _value(ws, top + 1 + n + i - 2 * j, 3 + i, value, PRICE)
                if layer_index == 1 and exercised[j]:
                    cell.fill = EXERCISE_FILL
        top += 2 * n + 3
    return top


def _pass_rate_table(ws, row, title, count_label, rows):
    """Rows of (expiry, count, passed) with a pass-rate formula and a total row.
    Count and passed may be formulas containing {row}. Return the total row."""
    _header(ws, row, 2, [title, count_label, "Passed", "Pass rate"])
    first = row + 1
    for expiry, count, passed in rows:
        row += 1
        _value(ws, row, 2, pd.Timestamp(expiry).to_pydatetime(), DATE).alignment = Alignment(
            horizontal="left"
        )
        for col, value in ((3, count), (4, passed)):
            _value(ws, row, col, value.format(row=row) if isinstance(value, str) else value, COUNT)
        _value(ws, row, 5, f"=IF(C{row}=0,0,D{row}/C{row})", PCT)
    row += 1
    _cell(ws, row, 2, "Total", bold=True)
    _value(ws, row, 3, f"=SUM(C{first}:C{row - 1})", COUNT, bold=True)
    _value(ws, row, 4, f"=SUM(D{first}:D{row - 1})", COUNT, bold=True)
    _value(ws, row, 5, f"=IF(C{row}=0,0,D{row}/C{row})", PCT, bold=True)
    return row
