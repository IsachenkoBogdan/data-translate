import json
from html import escape
from typing import Any

from data_translate.domain.translation_quality_fields import field_position_note, normalized_field_path


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _bar(value: float | None) -> str:
    width = 0 if value is None else max(0, min(100, value * 100))
    return f'<span class="bar"><span style="width:{width:.2f}%"></span></span>'


def _options(values: list[str]) -> str:
    return '<option value="">All</option>' + "".join(f'<option value="{escape(value)}">{escape(value)}</option>' for value in values)


def _rule_label_map(metrics: dict[str, Any]) -> dict[str, str]:
    return {str(item.get("code", "")): str(item.get("rule", item.get("code", ""))) for item in metrics.get("issue_guide", [])}


def _rule_options(values: list[str], labels: dict[str, str]) -> str:
    return '<option value="">All</option>' + "".join(
        f'<option value="{escape(value)}">{escape(labels.get(value, value))}</option>' for value in values
    )


def _rule_list(codes: dict[str, int], labels: dict[str, str]) -> str:
    if not codes:
        return '<span class="muted">none</span>'
    return " ".join(f'<span class="pill">{escape(labels.get(code, code))} {count}</span>' for code, count in list(codes.items())[:5])


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _field_cell(field: str, detail: str = "") -> str:
    detail_html = f'<span class="field-meta">{escape(detail)}</span>' if detail else ""
    return f'<div class="field-name"><code>{escape(field)}</code>{detail_html}</div>'


def _field_row_detail(row: dict[str, Any]) -> str:
    if row.get("position_summary"):
        return str(row["position_summary"])
    if int(row.get("checked_pairs", 0)) == 0 and (int(row.get("errors", 0)) > 0 or int(row.get("warnings", 0)) > 0):
        return "aggregate issue only"
    return ""


def _sample_text(issue: dict[str, Any], key: str) -> str:
    sample = issue.get("sample", {})
    value = sample.get(key, "")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _group_text(value: str) -> str:
    return " ".join(value.split())


def _issue_group_key(issue: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(issue.get("severity", "")),
        str(issue.get("code", "")),
        str(issue.get("message", "")),
        _group_text(_sample_text(issue, "source")),
        _group_text(_sample_text(issue, "translation")),
    )


def _issue_location(issue: dict[str, Any]) -> dict[str, str]:
    raw_field = str(issue.get("field", ""))
    return {
        "split": str(issue.get("split", "")),
        "row_idx": str(issue.get("row_idx", "")),
        "field": normalized_field_path(raw_field),
        "exact_field": raw_field,
        "position": field_position_note(raw_field),
    }


def _issue_records(issues: list[dict[str, Any]], rule_labels: dict[str, str]) -> list[dict[str, Any]]:
    records = []
    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for idx, issue in enumerate(issues, start=1):
        severity = str(issue.get("severity", ""))
        code = str(issue.get("code", ""))
        split = str(issue.get("split", ""))
        raw_field = str(issue.get("field", ""))
        field = normalized_field_path(raw_field)
        position = field_position_note(raw_field)
        message = str(issue.get("message", ""))
        row_idx = str(issue.get("row_idx", ""))
        rule = rule_labels.get(str(issue.get("code", "")), str(issue.get("code", "")))
        source_text = _sample_text(issue, "source")
        translation_text = _sample_text(issue, "translation")
        search = " ".join([severity, code, rule, split, normalized_field_path(raw_field), raw_field, position, message, source_text, translation_text]).lower()
        occurrence_count = max(1, int(issue.get("diagnostics", {}).get("duplicate_count", 1)))
        key = _issue_group_key(issue)
        existing = by_key.get(key)
        if existing is None:
            record = {
                "index": idx,
                "severity": severity,
                "code": code,
                "split": split,
                "row_idx": row_idx,
                "field": field,
                "exact_field": raw_field,
                "position": position,
                "rule": rule,
                "message": message,
                "source": source_text,
                "translation": translation_text,
                "diagnostics": issue.get("diagnostics", {}),
                "search": search,
                "occurrence_count": occurrence_count,
                "locations": [_issue_location(issue)],
                "fields": [field] if field else [],
                "exact_fields": [raw_field] if raw_field else [],
            }
            by_key[key] = record
            records.append(record)
            continue
        existing["occurrence_count"] += occurrence_count
        existing["locations"].append(_issue_location(issue))
        existing["search"] = f"{existing['search']} {search}"
        if field and field not in existing["fields"]:
            existing["fields"].append(field)
        if raw_field and raw_field not in existing["exact_fields"]:
            existing["exact_fields"].append(raw_field)
    return records


def _issue_guide_table(metrics: dict[str, Any]) -> str:
    rows = []
    for item in metrics.get("issue_guide", []):
        priority = escape(str(item.get("priority", "")))
        rows.append(
            f"""
            <tr>
              <td><span class="rule-name">{escape(str(item.get('rule', item.get('code', ''))))}</span><br><code>{escape(str(item.get('code', '')))}</code></td>
              <td class="num">{int(item.get('count', 0))}</td>
              <td><span class="priority priority-{priority}">{escape(str(item.get('label', 'Review')))}</span></td>
              <td>{escape(str(item.get('meaning', '')))}</td>
              <td>{escape(str(item.get('action', '')))}</td>
            </tr>
            """
        )
    if not rows:
        return '<tr><td colspan="5" class="muted">No issue guidance needed.</td></tr>'
    return "\n".join(rows)


def _base_css() -> str:
    return """
    :root {
      --bg: #f5f6f2;
      --panel: #ffffff;
      --panel-soft: #eef1ea;
      --text: #1d211f;
      --muted: #657069;
      --line: #d9ded5;
      --green: #237348;
      --green-bg: #e4f3ea;
      --yellow: #9a6500;
      --yellow-bg: #fff0cc;
      --red: #a7342f;
      --red-bg: #ffe1de;
      --blue: #285f8f;
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 var(--sans); }
    main { max-width: 1320px; margin: 0 auto; padding: 28px; }
    h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: 0; overflow-wrap: anywhere; }
    h2 { margin: 28px 0 10px; font-size: 18px; }
    code, pre { font-family: var(--mono); }
    .topline { border-bottom: 1px solid var(--line); padding-bottom: 18px; }
    .subtitle, .muted, .empty { color: var(--muted); }
    .cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
    .card, .note, .decision { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px; }
    .card b { display: block; font-size: 24px; line-height: 1.1; }
    .card span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .decision { border-left: 5px solid var(--blue); margin-bottom: 10px; }
    .decision b { display: block; font-size: 16px; margin-bottom: 3px; }
    .decision-pass { border-left-color: var(--green); background: var(--green-bg); }
    .decision-block { border-left-color: var(--red); background: var(--red-bg); }
    .decision-review, .decision-sample { border-left-color: var(--yellow); background: var(--yellow-bg); }
    table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
    th, td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }
    th { background: var(--panel-soft); font-size: 12px; text-transform: uppercase; color: #4f5a54; letter-spacing: .04em; }
    tr:last-child td { border-bottom: 0; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .error-text { color: var(--red); font-weight: 700; }
    .warning-text { color: var(--yellow); font-weight: 700; }
    .pill { display: inline-flex; gap: 4px; padding: 2px 6px; border: 1px solid var(--line); border-radius: 999px; background: #f8faf6; margin: 1px; font-size: 12px; }
    .muted-pill { color: #4f5a54; }
    .priority { display: inline-flex; padding: 2px 7px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }
    .priority-fix { color: var(--red); background: var(--red-bg); }
    .priority-review { color: var(--yellow); background: var(--yellow-bg); }
    .priority-sample { color: var(--blue); background: #e3edf7; }
    .bar { display: block; height: 6px; background: #e7ebe2; border-radius: 999px; overflow: hidden; margin-top: 4px; }
    .bar span { display: block; height: 100%; background: var(--blue); }
    .filters { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; background: var(--panel); border: 1px solid var(--line); border-radius: 6px 6px 0 0; padding: 12px; position: sticky; top: 0; z-index: 2; }
    .filters label { display: grid; gap: 4px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    select, input { width: 100%; box-sizing: border-box; border: 1px solid var(--line); border-radius: 4px; padding: 8px; background: #fff; color: var(--text); font: inherit; min-width: 0; }
    .issue-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; background: var(--panel); border: 1px solid var(--line); border-top: 0; border-radius: 0 0 6px 6px; padding: 10px 12px; margin-bottom: 12px; }
    .issue-toolbar b { display: block; }
    .pager { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .pager button { border: 1px solid var(--line); background: #fff; color: var(--text); border-radius: 4px; padding: 6px 9px; font: inherit; cursor: pointer; }
    .pager button:disabled { color: var(--muted); opacity: .55; cursor: default; }
    .page-status { color: var(--muted); min-width: 92px; text-align: center; }
    .issue-card { background: var(--panel); border: 1px solid var(--line); border-left-width: 5px; border-radius: 6px; margin: 10px 0; padding: 12px; }
    .issue-card.severity-error { border-left-color: var(--red); }
    .issue-card.severity-warning { border-left-color: var(--yellow); }
    .issue-card header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .issue-index { color: var(--muted); }
    .badge { border-radius: 4px; padding: 2px 6px; font-weight: 700; font-size: 12px; }
    .badge.error { color: var(--red); background: var(--red-bg); }
    .badge.warning { color: var(--yellow); background: var(--yellow-bg); }
    .code { font-family: var(--mono); color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .rule-name { font-weight: 700; }
    .loc { color: var(--muted); }
    .field-name { display: grid; gap: 3px; }
    .field-meta { color: var(--muted); font-size: 12px; }
    .field-chip, .position-chip { display: inline-flex; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
    .field-chip { font-family: var(--mono); background: #eef1ea; color: #39423d; overflow-wrap: anywhere; }
    .position-chip { background: #e3edf7; color: var(--blue); font-weight: 700; }
    .exact-field { opacity: .72; }
    .message { margin: 8px 0; color: #39423d; }
    .sample-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .sample-grid h4 { margin: 0 0 4px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
    pre { white-space: pre-wrap; word-break: break-word; background: #f2f4ef; border: 1px solid var(--line); border-radius: 4px; padding: 10px; margin: 0; max-height: 260px; overflow: auto; }
    details { margin-top: 8px; }
    summary { cursor: pointer; color: var(--blue); }
    .locations { margin: 8px 0 0; padding-left: 18px; color: #39423d; }
    .locations li { margin: 3px 0; }
    @media (max-width: 900px) {
      main { padding: 16px; }
      .cards, .filters, .sample-grid { grid-template-columns: 1fr; }
      .issue-toolbar { display: block; }
      .pager { justify-content: flex-start; margin-top: 8px; }
    }
    """


def render_quality_html(payload: dict[str, Any], metrics: dict[str, Any]) -> str:
    issues = [dict(issue) for issue in payload.get("issues", [])]
    dataset_name = str(payload.get("dataset_id") or payload.get("translated_path") or "translation")
    rule_labels = _rule_label_map(metrics)
    issue_records = _safe_json(_issue_records(issues, rule_labels))
    field_rows = "\n".join(
        f"""
        <tr>
          <td>{_field_cell(str(row['field']), _field_row_detail(row))}</td>
          <td>{row['checked_pairs']}</td>
          <td class="num error-text">{row['errors']}</td>
          <td class="num warning-text">{row['warnings']}</td>
          <td>{_pct(row['issue_rate'])} {_bar(row['issue_rate'])}</td>
          <td>{_rule_list(row['top_codes'], rule_labels)}</td>
        </tr>
        """
        for row in metrics["fields"]
    )
    split_rows = "\n".join(
        f"""
        <tr>
          <td><code>{escape(row['split'])}</code></td>
          <td>{row['rows']}</td>
          <td>{row['checked_rows']}</td>
          <td>{row['checked_pairs']}</td>
          <td class="num error-text">{row['errors']}</td>
          <td class="num warning-text">{row['warnings']}</td>
          <td>{_pct(row['issue_rate'])} {_bar(row['issue_rate'])}</td>
          <td>{_rule_list(row['top_codes'], rule_labels)}</td>
        </tr>
        """
        for row in metrics["splits"]
    )
    codes = sorted({str(issue.get("code", "")) for issue in issues if issue.get("code")})
    severities = sorted({str(issue.get("severity", "")) for issue in issues if issue.get("severity")})
    splits = sorted({str(issue.get("split", "")) for issue in issues if issue.get("split")})
    fields = sorted({normalized_field_path(str(issue.get("field", ""))) for issue in issues if issue.get("field")})
    recommendation = metrics.get("recommendation", {})
    recommendation_level = escape(str(recommendation.get("level", "sample")))
    issue_rate = metrics.get("rates", {}).get("issue_rate")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>check-translation · {escape(dataset_name)}</title>
  <link rel="icon" href="data:,">
  <style>{_base_css()}</style>
</head>
<body>
<main>
  <section class="topline">
    <div>
      <h1>check-translation · {escape(dataset_name)}</h1>
      <div class="subtitle">Static quality report generated by data-translate.</div>
    </div>
  </section>

  <section class="cards">
    <div class="card"><b>{metrics['checked_rows']}</b><span>checked rows</span></div>
    <div class="card"><b>{metrics['checked_pairs']}</b><span>checked pairs</span></div>
    <div class="card"><b>{metrics['error_count']}</b><span>errors</span></div>
    <div class="card"><b>{metrics['warning_count']}</b><span>warnings</span></div>
    <div class="card"><b>{_pct(issue_rate)}</b><span>issue rate</span></div>
  </section>

  <section class="decision decision-{recommendation_level}">
    <b>{escape(str(recommendation.get('summary', 'Review report.')))}</b>
    <span>{escape(str(recommendation.get('detail', 'Inspect the issue guide and examples below.')))}</span>
  </section>

  <h2>Field Coverage</h2>
  <table>
    <thead><tr><th>Field</th><th>Checked pairs</th><th>Errors</th><th>Warnings</th><th>Issue rate</th><th>Top rules</th></tr></thead>
    <tbody>{field_rows}</tbody>
  </table>

  <h2>Split Coverage</h2>
  <table>
    <thead><tr><th>Split</th><th>Rows</th><th>Checked rows</th><th>Checked pairs</th><th>Errors</th><th>Warnings</th><th>Issue rate</th><th>Top rules</th></tr></thead>
    <tbody>{split_rows}</tbody>
  </table>

  <h2>Issue Guide</h2>
  <table>
    <thead><tr><th>Check rule</th><th>Count</th><th>Priority</th><th>Triggered when</th><th>Suggested action</th></tr></thead>
    <tbody>{_issue_guide_table(metrics)}</tbody>
  </table>

  <h2>Issue Cases</h2>
  <section class="filters">
    <label>Severity<select id="severityFilter">{_options(severities)}</select></label>
    <label>Rule<select id="codeFilter">{_rule_options(codes, rule_labels)}</select></label>
    <label>Split<select id="splitFilter">{_options(splits)}</select></label>
    <label>Field<select id="fieldFilter">{_options(fields)}</select></label>
    <label>Search<input id="searchFilter" type="search" placeholder="source, translation, rule"></label>
  </section>
  <section class="issue-toolbar">
    <div>
      <b id="issueRange">0 cases</b>
      <span class="muted">Duplicate rows with the same source and translation are grouped. Showing 50 cases per page.</span>
    </div>
    <div class="pager">
      <button type="button" id="firstPage">First</button>
      <button type="button" id="prevPage">Prev</button>
      <span class="page-status" id="pageStatus">Page 0 / 0</span>
      <button type="button" id="nextPage">Next</button>
      <button type="button" id="lastPage">Last</button>
    </div>
  </section>
  <section id="issues"><div class="empty">Loading issues...</div></section>

</main>
<script>
const issueData = {issue_records};
const pageSize = 50;
let currentPage = 1;
const filters = {{
  severity: document.getElementById('severityFilter'),
  code: document.getElementById('codeFilter'),
  split: document.getElementById('splitFilter'),
  field: document.getElementById('fieldFilter'),
  search: document.getElementById('searchFilter')
}};
const issuesRoot = document.getElementById('issues');
const issueRange = document.getElementById('issueRange');
const pageStatus = document.getElementById('pageStatus');
const pager = {{
  first: document.getElementById('firstPage'),
  prev: document.getElementById('prevPage'),
  next: document.getElementById('nextPage'),
  last: document.getElementById('lastPage')
}};

function escapeHtml(value) {{
  return String(value ?? '').replace(/[&<>"']/g, char => ({{
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }}[char]));
}}

function diagnosticsText(value) {{
  try {{
    return JSON.stringify(value ?? {{}}, null, 2);
  }} catch (_error) {{
    return String(value ?? '');
  }}
}}

function locationsHtml(locations) {{
  const items = (locations || []).slice(0, 12).map(location => {{
    const position = location.position ? ` · ${{escapeHtml(location.position)}}` : '';
    const exact = location.exact_field && location.exact_field !== location.field ? ` · ${{escapeHtml(location.exact_field)}}` : '';
    return `<li><code>${{escapeHtml(location.split)}}[${{escapeHtml(location.row_idx)}}]</code> · <code>${{escapeHtml(location.field)}}</code>${{position}}${{exact}}</li>`;
  }}).join('');
  const omitted = (locations || []).length > 12 ? `<li class="muted">and ${{(locations || []).length - 12}} more listed occurrences</li>` : '';
  return `<ul class="locations">${{items}}${{omitted}}</ul>`;
}}

function issueCard(issue) {{
  const fields = issue.fields && issue.fields.length ? issue.fields : [issue.field];
  const fieldLabel = fields.length > 1 ? `${{fields[0]}} +${{fields.length - 1}}` : fields[0];
  const exactField = issue.exact_field && issue.exact_field !== issue.field
    ? `<span class="code exact-field">${{escapeHtml(issue.exact_field)}}</span>`
    : '';
  const position = issue.position
    ? `<span class="position-chip">${{escapeHtml(issue.position)}}</span>`
    : '';
  const occurrenceCount = Number(issue.occurrence_count || 1);
  const occurrenceChip = occurrenceCount > 1
    ? `<span class="pill">${{occurrenceCount}} occurrences</span>`
    : '';
  const locationDetails = (issue.locations || []).length > 1
    ? `<details><summary>Locations</summary>${{locationsHtml(issue.locations)}}</details>`
    : '';
  return `
    <article class="issue-card severity-${{escapeHtml(issue.severity)}}">
      <header>
        <span class="issue-index">#${{escapeHtml(issue.index)}}</span>
        <span class="badge ${{escapeHtml(issue.severity)}}">${{escapeHtml(issue.severity)}}</span>
        <span class="rule-name">${{escapeHtml(issue.rule)}}</span>
        <span class="code">${{escapeHtml(issue.code)}}</span>
        <span class="loc">${{escapeHtml(issue.split)}}[${{escapeHtml(issue.row_idx)}}]</span>
        <span class="field-chip">${{escapeHtml(fieldLabel)}}</span>
        ${{position}}
        ${{exactField}}
        ${{occurrenceChip}}
      </header>
      <p class="message">${{escapeHtml(issue.message)}}</p>
      <div class="sample-grid">
        <div><h4>Source</h4><pre>${{escapeHtml(issue.source)}}</pre></div>
        <div><h4>Translation</h4><pre>${{escapeHtml(issue.translation)}}</pre></div>
      </div>
      ${{locationDetails}}
      <details>
        <summary>Diagnostics</summary>
        <pre class="diagnostics">${{escapeHtml(diagnosticsText(issue.diagnostics))}}</pre>
      </details>
    </article>
  `;
}}

function matchesFilters(issue) {{
  const query = filters.search.value.trim().toLowerCase();
  return (!filters.severity.value || issue.severity === filters.severity.value)
    && (!filters.code.value || issue.code === filters.code.value)
    && (!filters.split.value || issue.split === filters.split.value)
    && (!filters.field.value || (issue.fields || [issue.field]).includes(filters.field.value))
    && (!query || issue.search.includes(query));
}}

function renderIssues(page = currentPage) {{
  const filtered = issueData.filter(matchesFilters);
  const total = filtered.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  currentPage = Math.min(Math.max(1, page), pageCount);
  const start = (currentPage - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  issuesRoot.innerHTML = visible.length
    ? visible.map(issueCard).join('')
    : '<div class="empty">No cases match the current filters.</div>';

  if (total) {{
    const end = start + visible.length;
    issueRange.textContent = `Showing ${{start + 1}}-${{end}} of ${{total}} cases`;
    pageStatus.textContent = `Page ${{currentPage}} / ${{pageCount}}`;
  }} else {{
    issueRange.textContent = '0 cases';
    pageStatus.textContent = 'Page 0 / 0';
  }}
  pager.first.disabled = currentPage <= 1 || total === 0;
  pager.prev.disabled = currentPage <= 1 || total === 0;
  pager.next.disabled = currentPage >= pageCount || total === 0;
  pager.last.disabled = currentPage >= pageCount || total === 0;
}}

Object.values(filters).forEach(el => el.addEventListener('input', () => renderIssues(1)));
pager.first.addEventListener('click', () => renderIssues(1));
pager.prev.addEventListener('click', () => renderIssues(currentPage - 1));
pager.next.addEventListener('click', () => renderIssues(currentPage + 1));
pager.last.addEventListener('click', () => renderIssues(Math.ceil(issueData.filter(matchesFilters).length / pageSize)));
renderIssues(1);
</script>
</body>
</html>
"""


def render_fix_suggestions_html(payload: dict[str, Any]) -> str:
    rows = payload.get("suggestions", [])
    cards = []
    for idx, row in enumerate(rows, start=1):
        status = escape(str(row.get("status", "")))
        issue = row.get("issue", {})
        source = escape(str(row.get("source", "")))
        current = escape(str(row.get("current_translation", "")))
        suggestion = escape(str(row.get("suggested_translation", "")))
        rationale = escape(str(row.get("rationale", "")))
        confidence = escape(str(row.get("confidence", "")))
        occurrence_count = int(issue.get("occurrence_count", 1))
        occurrence_html = f'<span class="pill">{occurrence_count} occurrences</span>' if occurrence_count > 1 else ""
        location_rows = []
        for location in issue.get("locations", [])[:20]:
            location_rows.append(
                f"<li><code>{escape(str(location.get('split', '')))}[{escape(str(location.get('row_idx', '')))}]</code> · "
                f"<code>{escape(str(location.get('field', '')))}</code></li>"
            )
        if len(issue.get("locations", [])) > 20:
            location_rows.append(f'<li class="muted">and {len(issue.get("locations", [])) - 20} more listed occurrences</li>')
        locations_html = f"<details><summary>Locations</summary><ul class=\"locations\">{''.join(location_rows)}</ul></details>" if location_rows else ""
        cards.append(
            f"""
            <article class="issue-card">
              <header><span class="issue-index">#{idx}</span><span class="badge warning">{status}</span><span class="code">{escape(str(issue.get('code', '')))}</span><span class="loc">{escape(str(issue.get('split', '')))}[{escape(str(issue.get('row_idx', '')))}] · {escape(str(issue.get('field', '')))}</span>{occurrence_html}</header>
              <div class="sample-grid">
                <div><h4>Source</h4><pre>{source}</pre></div>
                <div><h4>Current</h4><pre>{current}</pre></div>
              </div>
              {locations_html}
              <h4>Suggested translation · confidence {confidence}</h4>
              <pre>{suggestion}</pre>
              <p class="message">{rationale}</p>
            </article>
            """
        )
    body = "\n".join(cards) if cards else '<div class="empty">No suggestions generated.</div>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>check-translation fixes</title>
  <link rel="icon" href="data:,">
  <style>{_base_css()}</style>
</head>
<body>
<main>
  <section class="topline">
    <div>
      <h1>GPT fix suggestions</h1>
      <div class="subtitle">Suggestions only. No dataset artifact was modified.</div>
    </div>
  </section>
  {body}
</main>
</body>
</html>
"""
