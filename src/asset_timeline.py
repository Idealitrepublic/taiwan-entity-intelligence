"""Objective, bounded year-over-year comparisons for asset declarations."""
from collections import Counter, defaultdict
from decimal import Decimal
import unicodedata

MAX_TIMELINE_ROWS = 500
MAX_TIMELINE_YEARS = 20


def _normalized(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _identity_key(row):
    company = row.get("company_entity_id")
    company_key = f"entity:{company}" if company else f"text:{_normalized(row.get('company_name'))}"
    return (str(row.get("asset_type") or ""), _normalized(row.get("asset_name")), company_key)


def _metric_totals(rows, value_field, unit_field):
    totals = defaultdict(Decimal)
    for row in rows:
        value, unit = row.get(value_field), row.get(unit_field)
        if value is None or not unit:
            continue
        totals[str(unit)] += Decimal(str(value))
    return {unit: format(value, "f") for unit, value in sorted(totals.items())}


def _vector_status(previous, current):
    if set(previous) != set(current):
        return "CHANGED"
    keys = set(previous)
    if all(previous.get(key, Decimal(0)) == current.get(key, Decimal(0)) for key in keys):
        return "CONTINUED"
    less = any(current.get(key, Decimal(0)) < previous.get(key, Decimal(0)) for key in keys)
    greater = any(current.get(key, Decimal(0)) > previous.get(key, Decimal(0)) for key in keys)
    if less and not greater:
        return "DECREASED"
    if greater and not less:
        return "INCREASED"
    return "CHANGED"


def _group_metrics(rows):
    amounts = _metric_totals(rows, "amount", "currency")
    quantities = _metric_totals(rows, "quantity", "quantity_unit")
    return amounts, quantities


def _compare(previous_rows, current_rows):
    previous_groups, current_groups = defaultdict(list), defaultdict(list)
    for row in previous_rows:
        previous_groups[_identity_key(row)].append(row)
    for row in current_rows:
        current_groups[_identity_key(row)].append(row)
    changes = []
    for key in sorted(set(previous_groups) | set(current_groups)):
        previous, current = previous_groups.get(key, []), current_groups.get(key, [])
        sample = (current or previous)[0]
        previous_amounts, previous_quantities = _group_metrics(previous)
        current_amounts, current_quantities = _group_metrics(current)
        if not previous:
            status = "NEW"
        elif not current:
            status = "NO_LONGER_DECLARED"
        else:
            previous_vector = {
                **{f"amount:{unit}": Decimal(value) for unit, value in previous_amounts.items()},
                **{f"quantity:{unit}": Decimal(value) for unit, value in previous_quantities.items()},
            }
            current_vector = {
                **{f"amount:{unit}": Decimal(value) for unit, value in current_amounts.items()},
                **{f"quantity:{unit}": Decimal(value) for unit, value in current_quantities.items()},
            }
            status = _vector_status(previous_vector, current_vector)
        changes.append({
            "status": status,
            "asset_type": sample.get("asset_type"),
            "asset_name": sample.get("asset_name"),
            "company_name": sample.get("company_name"),
            "company_entity_id": sample.get("company_entity_id"),
            "previous_amounts": previous_amounts,
            "current_amounts": current_amounts,
            "previous_quantities": previous_quantities,
            "current_quantities": current_quantities,
            "previous_records": previous,
            "current_records": current,
        })
    return changes


def _type_summaries(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get("asset_type") or "OTHER")].append(row)
    return [{
        "asset_type": asset_type,
        "record_count": len(items),
        "amounts": _metric_totals(items, "amount", "currency"),
        "quantities": _metric_totals(items, "quantity", "quantity_unit"),
    } for asset_type, items in sorted(groups.items())]


def build_asset_timeline(rows, *, max_years=10, truncated=False):
    """Build adjacent-year comparisons without inferring identity or wrongdoing."""
    if not 2 <= int(max_years) <= MAX_TIMELINE_YEARS:
        raise ValueError("Timeline years must be between 2 and 20")
    published = [dict(row) for row in rows]
    years = sorted({int(row["declaration_year"]) for row in published})[-int(max_years):]
    fetched_years = {int(row["declaration_year"]) for row in published}
    partial_year = (min(years) if truncated and years and min(years) == min(fetched_years)
                    else None)
    by_year = {year: sorted(
        (row for row in published if int(row["declaration_year"]) == year),
        key=lambda row: (str(row.get("asset_type") or ""),
                         _normalized(row.get("asset_name")), str(row.get("id") or "")),
    ) for year in years}
    timeline = []
    for index, year in enumerate(years):
        records = by_year[year]
        previous_year = years[index - 1] if index else None
        changes = (_compare(by_year[previous_year], records) if previous_year is not None
                   else [{"status": "BASELINE", "asset_type": row.get("asset_type"),
                          "asset_name": row.get("asset_name"),
                          "company_name": row.get("company_name"),
                          "company_entity_id": row.get("company_entity_id"),
                          "previous_amounts": {},
                          "current_amounts": _metric_totals([row], "amount", "currency"),
                          "previous_quantities": {},
                          "current_quantities": _metric_totals(
                              [row], "quantity", "quantity_unit"),
                          "previous_records": [], "current_records": [row]}
                         for row in records])
        timeline.append({
            "year": year,
            "previous_year": previous_year,
            "partial": year == partial_year,
            "record_count": len(records),
            "asset_types": _type_summaries(records),
            "status_counts": dict(sorted(Counter(change["status"] for change in changes).items())),
            "changes": changes,
        })
    return {
        "years": timeline,
        "year_count": len(timeline),
        "row_count": sum(len(by_year[year]) for year in years),
        "truncated": bool(truncated),
        "partial_years": [partial_year] if partial_year is not None else [],
        "comparison_basis": "adjacent_declaration_years_exact_normalized_asset_identity",
        "disclaimer": (
            "Changes describe differences between published declarations only; they do not "
            "establish illegality, conflicts of interest, acquisition, or disposal."
        ),
    }
